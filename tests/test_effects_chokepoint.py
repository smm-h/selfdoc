"""The effects chokepoint is the only authorized effect surface.

``selfdoc_core.effects`` is the single module in which selfdoc production code
may call ``subprocess``, ``open(path, "w")``, ``os.makedirs``,
``shutil.rmtree`` and their siblings.  Everything else routes through it, so
strictcli's ``--dry-run`` regime is adapted in one file rather than at ~150
call sites -- and so no future call site can quietly reintroduce a bare
subprocess launch that a preview would execute for real.

This is an AST scan, not a grep: it sees the call target rather than the
spelling, so ``os . makedirs(...)`` and a multi-line ``subprocess.run(`` are
both caught.

Two exemption mechanisms, both deliberately narrow:

* ``_EXEMPT_MODULES`` -- the chokepoint itself, which holds the primitives.
* an inline ``# effects: exempt -- <reason>`` comment on the offending line,
  for the handful of self-owned scratch files a call creates, reads back and
  deletes within the same call.  A reason is mandatory; the marker without one
  does not count.
"""

import ast
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

PRODUCTION_PACKAGES = ("selfdoc", "selfblog", "selfdoc_core")

# The chokepoint holds the primitives; nothing else is exempt wholesale.
_EXEMPT_MODULES = {
    "selfdoc_core/effects.py",
}

# Dotted call targets that mutate the world.
_BANNED_CALLS = {
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "os.makedirs",
    "os.mkdir",
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "os.removedirs",
    "os.rename",
    "os.replace",
    "os.chmod",
    "shutil.rmtree",
    "shutil.copy",
    "shutil.copy2",
    "shutil.copyfile",
    "shutil.copytree",
    "shutil.move",
}

_EXEMPT_MARKER = "# effects: exempt --"


def _production_files():
    files = []
    for pkg in PRODUCTION_PACKAGES:
        for path in sorted((REPO_ROOT / pkg).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel in _EXEMPT_MODULES:
                continue
            if "/dist/" in rel or "/__pycache__/" in rel:
                continue
            files.append((rel, path))
    return files


def _dotted(node):
    """Return the dotted spelling of a call target, or None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _write_mode(call):
    """True when an ``open(...)`` call opens the path for writing."""
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        mode = call.args[1].value
    else:
        mode = None
        for kw in call.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                mode = kw.value.value
    if not isinstance(mode, str):
        return False
    return any(ch in mode for ch in "wax")


def _violations(rel, path):
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = _dotted(node.func)
        if target is None:
            continue
        banned = target in _BANNED_CALLS or (
            target == "open" and _write_mode(node)
        )
        if not banned:
            continue
        line = lines[node.lineno - 1]
        if _EXEMPT_MARKER in line and line.split(_EXEMPT_MARKER, 1)[1].strip():
            continue
        found.append(f"{rel}:{node.lineno}: {target}")
    return found


@pytest.mark.parametrize(
    "rel,path", _production_files(), ids=lambda v: v if isinstance(v, str) else "",
)
def test_no_effect_bypass(rel, path):
    """No production module calls an effectful primitive outside the chokepoint."""
    violations = _violations(rel, path)
    assert not violations, (
        "effectful call outside selfdoc_core.effects:\n  "
        + "\n  ".join(violations)
        + "\n\nRoute it through selfdoc_core.effects, or mark a self-owned "
        "scratch operation with '# effects: exempt -- <reason>'."
    )


def test_chokepoint_module_is_the_only_wholesale_exemption():
    """The exemption list stays a list of one -- a widening must be deliberate."""
    assert _EXEMPT_MODULES == {"selfdoc_core/effects.py"}

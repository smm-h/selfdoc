"""Documentation quality scoring -- computes maturity tiers (0-5) and content grades (A-F) based on feature adoption and doc-to-source ratio.

Two independent axes describe a project's documentation:

* the **tier** (0-5, see :data:`TIERS`) is a ladder of selfdoc feature
  adoption -- markdown exists, selfdoc.json exists, root files are generated
  from templates, directives connect docs to source, custom directives or
  blog posts are in use.  Each rung requires every rung below it, so the tier
  is the first unmet requirement minus one, and :data:`NEXT_STEPS` names the
  action that reaches the next rung.
* the **content grade** (A-F, see :func:`content_grade`) measures volume:
  documentation lines divided by non-test source lines.

Source lines come from the external ``dirstat`` binary (a hard requirement,
see :func:`check_dirstat`); documentation lines, test lines, and directive
usage are counted by walking the tree here.  Git submodules are excluded from
every count, so a project is scored on the code it actually owns.

:func:`run_quality` is the entry point behind ``selfdoc quality``.
"""

import json
import os
import re
import sys
from pathlib import Path

from selfdoc_core import effects


CODE_EXTENSIONS = {
    "py", "go", "rs", "c", "cpp", "h", "hpp", "java", "rb", "kt",
    "js", "ts", "jsx", "tsx", "mjs", "cjs",
    "html", "css", "scss", "sass", "less", "svelte", "vue",
    "sh", "bash", "zsh", "fish",
    "makefile", "cmake", "dockerfile",
    "sql", "swift",
    "hcl", "tf", "nix", "proto", "graphql",
    "gd", "gdshader",
}

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "__pycache__", "vendor",
    "dist", "build", ".next", "out", ".cache", ".tox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}

SKIP_MD_FILES = {"CHANGELOG.md"}

TIERS = {
    0: ("None", "No markdown documentation"),
    1: ("Basic", "Has markdown documentation"),
    2: ("Selfdoc", "selfdoc.json configured"),
    3: ("Templates", "Auto-generated root files (README/CLAUDE)"),
    4: ("Directives", "Directives connect docs to source code"),
    5: ("Advanced", "Custom directives or blog posts"),
}

NEXT_STEPS = {
    0: "Create a README.md with project description and usage",
    1: "Run `selfdoc init` to create selfdoc.json",
    2: "Add docs/_README.md to root_files in selfdoc.json",
    3: "Use :-: directives in docs/ to connect docs to source code",
    4: "Define custom directives or configure blog posts",
}


def check_dirstat():
    """Exit with an install hint unless the ``dirstat`` binary is runnable.

    Source-line counting has no in-tree fallback, so a missing ``dirstat``
    would silently report every project as 0 source LOC.  This probes it once
    up front (``dirstat scan --help``) and, when the binary is absent, prints
    the ``go install`` command to stderr and terminates the process with exit
    status 1.  Only absence is fatal: a non-zero exit from the probe itself is
    ignored, since it still proves the binary exists.
    """
    try:
        effects.run(
            ["dirstat", "scan", "--help"],
            capture_output=True,
            read=True,
        )
    except FileNotFoundError:
        print("error: dirstat is not installed", file=sys.stderr)
        print(
            "install: go install github.com/smm-h/dirstat/cmd/dirstat@latest",
            file=sys.stderr,
        )
        sys.exit(1)


def get_submodule_paths(project_path):
    """Return the ``path`` entries declared in the project's ``.gitmodules``.

    The paths are returned exactly as written (repository-relative, e.g.
    ``vendor/theme``) and are used by every counter in this module to keep
    submodule content out of a project's own totals.  Returns an empty list
    when there is no ``.gitmodules`` file or it cannot be read.
    """
    try:
        gitmodules = Path(project_path) / ".gitmodules"
        if not gitmodules.is_file():
            return []
        text = gitmodules.read_text()
        return re.findall(r"^\s*path\s*=\s*(.+)$", text, re.MULTILINE)
    except Exception:
        return []


def get_code_loc(project_path, submodule_paths=None):
    """Return ``(code_loc, code_files)`` for the project, submodules excluded.

    Runs ``dirstat scan`` over *project_path* and keeps only the file-format
    groups whose extension appears in :data:`CODE_EXTENSIONS` -- markup, data,
    and lockfiles are therefore not code.  Because ``dirstat`` scans the whole
    tree, each path in *submodule_paths* is scanned separately and subtracted;
    overlapping entries (a submodule nested inside another submodule) are
    subtracted once each, so the totals can go negative.

    Returns ``(0, 0)`` when the scan fails, times out (60s per scan), or emits
    output that is not parseable JSON; a failing submodule subtraction is
    skipped while the outer total is kept.
    """
    try:
        result = effects.run(
            [
                "dirstat", "scan", str(project_path),
                "--output", "json",
                "--type", "text",
                "--stats", "count",
                "--stats", "total-loc",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            read=True,
        )
        data = json.loads(result.stdout)
        code_loc = 0
        code_files = 0
        for group in data.get("groups", []):
            fmt = group.get("format", "").lower()
            if fmt in CODE_EXTENSIONS:
                code_loc += group.get("total_loc", 0)
                code_files += group.get("count", 0)

        if submodule_paths:
            for sp in submodule_paths:
                sub_dir = Path(project_path) / sp
                if not sub_dir.is_dir():
                    continue
                try:
                    sub_result = effects.run(
                        [
                            "dirstat", "scan", str(sub_dir),
                            "--output", "json",
                            "--type", "text",
                            "--stats", "count",
                            "--stats", "total-loc",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=60,
                        read=True,
                    )
                    sub_data = json.loads(sub_result.stdout)
                    for group in sub_data.get("groups", []):
                        fmt = group.get("format", "").lower()
                        if fmt in CODE_EXTENSIONS:
                            code_loc -= group.get("total_loc", 0)
                            code_files -= group.get("count", 0)
                except Exception:
                    pass

        return (code_loc, code_files)
    except Exception:
        return (0, 0)


def count_markdown(project_path, submodule_paths=None, root_file_templates=None):
    """Return ``(doc_loc, doc_files)`` for the project's Markdown.

    Walks *project_path* counting lines in every ``.md`` file, skipping:

    * the directories in :data:`SKIP_DIRS` plus ``todo/`` (planning notes are
      not documentation) and every directory in *submodule_paths*;
    * the filenames in :data:`SKIP_MD_FILES` (generated changelogs);
    * every path in *root_file_templates* -- the ``docs/_README.md`` style
      templates named by ``root_files`` in selfdoc.json.  Their generated
      output (``README.md``, ``CLAUDE.md``) sits at the project root and is
      counted instead, so skipping the template avoids counting the same
      prose twice.  Paths are matched relative to *project_path*, exactly as
      selfdoc.json spells them.

    Files that cannot be read are skipped rather than counted as empty.
    """
    doc_loc = 0
    doc_files = 0
    submodule_abs = set()
    if submodule_paths:
        for sp in submodule_paths:
            submodule_abs.add(str(Path(project_path) / sp))

    template_set = set(root_file_templates) if root_file_templates else set()

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [
            d for d in dirs
            if d not in SKIP_DIRS
            and d != "todo"
            and os.path.join(root, d) not in submodule_abs
        ]
        for fname in files:
            if not fname.endswith(".md"):
                continue
            if fname in SKIP_MD_FILES:
                continue
            full_path = os.path.join(root, fname)
            if template_set:
                rel = os.path.relpath(full_path, project_path)
                if rel in template_set:
                    continue
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                doc_loc += len(lines)
                doc_files += 1
            except Exception:
                pass

    return (doc_loc, doc_files)


def get_selfdoc_info(project_path):
    """Describe the project's selfdoc adoption, as read from selfdoc.json.

    Returns ``{"has_selfdoc": False}`` when selfdoc.json is missing or does
    not parse.  Otherwise the dict also carries:

    * ``auto_readme`` / ``auto_claude`` -- whether ``root_files`` names a
      ``_README.md`` / ``_CLAUDE.md`` template;
    * ``custom_directives`` -- number of entries in the ``directives`` map;
    * ``has_posts`` -- whether a non-empty ``posts`` section exists;
    * ``directive_count`` -- number of lines across the configured ``docs``
      directory (``_build`` excluded) that carry a ``:-:``, ``:<:`` or ``:>:``
      marker.  It counts marker LINES, not directives: a line holding two
      markers counts once, and an open/close block counts twice.

    These flags are what :func:`compute_tier` climbs its ladder on.
    """
    selfdoc_json = Path(project_path) / "selfdoc.json"
    if not selfdoc_json.is_file():
        return {"has_selfdoc": False}

    try:
        config = json.loads(selfdoc_json.read_text())
    except Exception:
        return {"has_selfdoc": False}

    root_files = config.get("root_files", [])
    auto_readme = any(rf.endswith("_README.md") for rf in root_files)
    auto_claude = any(rf.endswith("_CLAUDE.md") for rf in root_files)

    directives_dict = config.get("directives", {})
    custom_directives = len(directives_dict) if isinstance(directives_dict, dict) else 0

    has_posts = bool(config.get("posts"))

    docs_dir = Path(project_path) / config.get("docs", "docs")
    directive_count = 0
    if docs_dir.is_dir():
        for root, dirs, files in os.walk(docs_dir):
            dirs[:] = [d for d in dirs if d != "_build"]
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                full_path = os.path.join(root, fname)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            if ":-:" in line or ":<:" in line or ":>:" in line:
                                directive_count += 1
                except Exception:
                    pass

    return {
        "has_selfdoc": True,
        "auto_readme": auto_readme,
        "auto_claude": auto_claude,
        "custom_directives": custom_directives,
        "has_posts": has_posts,
        "directive_count": directive_count,
    }


def compute_tier(doc_loc, selfdoc_info):
    """Return the maturity tier 0-5 for a project (see :data:`TIERS`).

    The rungs are cumulative and evaluated in order, so the tier is the last
    satisfied requirement: any Markdown at all (1), selfdoc.json present (2),
    a generated README template in ``root_files`` (3), at least one directive
    used in the docs (4), and custom directives or blog posts configured (5).

    *doc_loc* is the Markdown line count from :func:`count_markdown` and
    *selfdoc_info* the dict from :func:`get_selfdoc_info`.
    """
    if doc_loc == 0:
        return 0
    if not selfdoc_info.get("has_selfdoc"):
        return 1
    if not selfdoc_info.get("auto_readme"):
        return 2
    if not selfdoc_info.get("directive_count"):
        return 3
    if not selfdoc_info.get("custom_directives") and not selfdoc_info.get("has_posts"):
        return 4
    return 5


def content_grade(ratio):
    """Grade a documentation-to-source line ratio as A-F.

    Cut-offs, applied to *ratio* (doc LOC / non-test source LOC): 0.30 or more
    is an A, 0.15 a B, 0.05 a C, 0.01 a D, and anything below that an F.
    ``None`` -- meaning there was no source to compare against -- grades as
    ``"-"`` rather than F, so an empty project is not marked as failing.
    """
    if ratio is None:
        return "-"
    if ratio >= 0.30:
        return "A"
    if ratio >= 0.15:
        return "B"
    if ratio >= 0.05:
        return "C"
    if ratio >= 0.01:
        return "D"
    return "F"


def count_test_loc(project_path, submodule_paths=None):
    """Return the total line count of the project's test code.

    Walks *project_path* (skipping :data:`SKIP_DIRS`, ``todo/`` and every
    directory in *submodule_paths*) and counts lines in files that have a
    :data:`CODE_EXTENSIONS` extension AND look like tests -- meaning they sit
    under a ``tests``/``test``/``__tests__``/``testing`` directory at any
    depth, or are named ``conftest.py``, ``test_*.py``, ``*_test.py``,
    ``*_test.go``, or ``*.test.``/``*.spec.`` for js/ts/jsx/tsx.

    :func:`score_project` subtracts this from the ``dirstat`` code total so
    the doc ratio is measured against production source only, and a large
    test suite neither inflates nor deflates a project's grade.
    """
    test_dirs = {"tests", "test", "__tests__", "testing"}

    submodule_abs = set()
    if submodule_paths:
        for sp in submodule_paths:
            submodule_abs.add(str(Path(project_path) / sp))

    def is_test_file(dirpath, filename):
        parts = Path(dirpath).relative_to(project_path).parts
        if any(p in test_dirs for p in parts):
            return True
        if filename == "conftest.py":
            return True
        if filename.startswith("test_") and filename.endswith(".py"):
            return True
        if filename.endswith("_test.go") or filename.endswith("_test.py"):
            return True
        for pat in [".test.ts", ".test.js", ".spec.ts", ".spec.js",
                    ".test.tsx", ".test.jsx", ".spec.tsx", ".spec.jsx"]:
            if filename.endswith(pat):
                return True
        return False

    total = 0
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [
            d for d in dirs
            if d not in SKIP_DIRS
            and d != "todo"
            and os.path.join(root, d) not in submodule_abs
        ]
        for fname in files:
            ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else fname.lower()
            if ext not in CODE_EXTENSIONS:
                continue
            if not is_test_file(root, fname):
                continue
            full_path = os.path.join(root, fname)
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                total += len(lines)
            except Exception:
                pass

    return total


def score_project(project_path):
    """Score one project directory and return its full result dict.

    Runs every counter in this module against *project_path* and combines
    them.  ``source_loc`` is the ``dirstat`` code total minus test LOC,
    floored at 0; ``doc_ratio`` is doc LOC over ``source_loc`` rounded to four
    decimals, or ``None`` when there is no source to divide by.

    The returned dict is the shape both formatters and ``selfdoc quality
    --format json`` consume: ``project``, ``path``, ``tier``, ``tier_name``,
    ``code_loc``, ``test_loc``, ``source_loc``, ``doc_loc``, ``doc_files``,
    ``doc_ratio``, ``content_grade``, the nested ``selfdoc`` adoption dict,
    and ``next_step`` (``None`` at tier 5, where nothing is left to do).
    """
    project_path = Path(project_path)
    submodule_paths = get_submodule_paths(project_path)
    code_loc, code_files = get_code_loc(project_path, submodule_paths)
    test_loc = count_test_loc(project_path, submodule_paths)
    selfdoc_info = get_selfdoc_info(project_path)

    root_file_templates = None
    selfdoc_json = project_path / "selfdoc.json"
    if selfdoc_json.is_file():
        try:
            cfg = json.loads(selfdoc_json.read_text())
            rf = cfg.get("root_files", [])
            if rf:
                root_file_templates = rf
        except Exception:
            pass

    doc_loc, doc_files = count_markdown(project_path, submodule_paths, root_file_templates)
    tier = compute_tier(doc_loc, selfdoc_info)
    source_loc = max(0, code_loc - test_loc)
    ratio = round(doc_loc / source_loc, 4) if source_loc > 0 else None

    return {
        "project": project_path.name,
        "path": str(project_path),
        "tier": tier,
        "tier_name": TIERS[tier][0],
        "code_loc": code_loc,
        "test_loc": test_loc,
        "source_loc": source_loc,
        "doc_loc": doc_loc,
        "doc_files": doc_files,
        "doc_ratio": ratio,
        "content_grade": content_grade(ratio),
        "selfdoc": selfdoc_info,
        "next_step": NEXT_STEPS.get(tier),
    }


def format_single_text(result):
    """Render a :func:`score_project` result as the human-readable report.

    The report is a headline (project, tier, tier name), a one-line metrics
    summary (source LOC, test LOC when non-zero, doc LOC with the ratio as a
    percentage, file count, grade), the selfdoc adoption block or a "not
    configured" line, the tiers already completed, and the tiers still to do
    -- where the immediate next tier is stated as the concrete action from
    :data:`NEXT_STEPS` rather than as a requirement.

    Returns the report as a single string with no trailing newline.
    """
    lines = []
    tier = result["tier"]
    lines.append(
        f"{result['project']} -- Tier {tier} / 5 ({result['tier_name']})"
    )
    lines.append("")

    source_loc = f"{result['source_loc']:,}"
    test_loc = result["test_loc"]
    doc_loc = f"{result['doc_loc']:,}"
    if result["doc_ratio"] is not None:
        ratio = f"{result['doc_ratio'] * 100:.1f}%"
    else:
        ratio = "n/a"
    grade = result["content_grade"]
    parts = [f"{source_loc} source LOC"]
    if test_loc > 0:
        parts.append(f"{test_loc:,} test LOC")
    parts.append(f"{doc_loc} doc LOC ({ratio})")
    parts.append(f"{result['doc_files']} files")
    parts.append(f"Grade: {grade}")
    lines.append(" | ".join(parts))

    lines.append("")
    selfdoc = result["selfdoc"]
    if selfdoc.get("has_selfdoc"):
        lines.append("Selfdoc:")
        lines.append(
            f"  Auto-generated README    "
            f"{'yes' if selfdoc.get('auto_readme') else 'no'}"
        )
        lines.append(
            f"  Auto-generated CLAUDE    "
            f"{'yes' if selfdoc.get('auto_claude') else 'no'}"
        )
        lines.append(
            f"  Custom directives        "
            f"{selfdoc.get('custom_directives') or '-'}"
        )
        lines.append(
            f"  Blog posts               "
            f"{'yes' if selfdoc.get('has_posts') else 'no'}"
        )
        lines.append(
            f"  Directive uses           "
            f"{selfdoc.get('directive_count') or '-'}"
        )
    else:
        lines.append("Selfdoc: not configured")

    if tier > 0:
        lines.append("")
        lines.append("Completed:")
        for t in range(1, tier + 1):
            lines.append(f"  Tier {t} -- {TIERS[t][1]}")

    if tier < 5:
        lines.append("")
        lines.append("To do:")
        for t in range(tier + 1, 6):
            if t == tier + 1:
                lines.append(f"  Tier {t} -- {NEXT_STEPS[tier]}")
            else:
                lines.append(f"  Tier {t} -- {TIERS[t][1]}")
    elif tier == 5:
        lines.append("")
        lines.append("All tiers complete.")

    return "\n".join(lines)


def format_json(data):
    """Serialize a score result as indented JSON (2 spaces), for ``--format json``."""
    return json.dumps(data, indent=2)


def run_quality(format="text"):
    """Run ``selfdoc quality``: score the current directory and print the report.

    Verifies ``dirstat`` is installed first (:func:`check_dirstat` exits the
    process when it is not), scores the current working directory, then prints
    either the JSON document (``format="json"``) or the text report.

    Always returns 0 -- quality is a report, not a gate, so a low tier or a
    failing grade never fails the command.
    """
    check_dirstat()

    result = score_project(Path.cwd())
    if format == "json":
        print(format_json(result))
    else:
        print(format_single_text(result))

    return 0

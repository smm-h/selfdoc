"""Description ownership predicate: machine-owned vs handwritten.

Classifies a generated page's frontmatter ``description`` as either
machine-owned (a placeholder selfdoc emitted and may freely overwrite) or
handwritten (authored by a human/agent and must never be overwritten).

The single guiding principle: descriptions are handwritten; machine text is
only ever a placeholder.  The critical property is the INVERSE -- handwritten
text must NEVER be classified machine-owned.  The reverse (legacy machine
residue occasionally classified handwritten when no ``seed_hash`` was ever
recorded) is acceptable: the next ``selfdoc gen`` reseeds it, and releases
always run gen before check.

Ownership is decided per page kind:

- module pages: the current or historical instantiated template for that
  module, OR the recorded ``seed_hash``.
- gen-index: the current/legacy index templates, OR the recorded ``seed_hash``.
- CLI pages: :func:`is_default_cli_description` (a live recompute from the
  schema, covering the truncated-prefix family), OR the recorded ``seed_hash``.

``seed_hash`` is the SHA-256 of the machine-emitted description TEXT, recorded
per page by ``selfdoc gen`` in the staleness store.

This module lives in the ``selfdoc`` (app) layer, not ``selfdoc_core``,
because CLI ownership needs :mod:`selfdoc.strictcli_support`.
"""

import hashlib
import os
import re

from selfdoc.strictcli_support import is_default_cli_description


# -- Machine templates -------------------------------------------------------

# Current auto-generated module page description (parameterized by module).
MODULE_DESC_TEMPLATE = (
    "API reference for the {module} module — "
    "auto-generated documentation covering public functions, "
    "classes, and type signatures."
)

# Historical auto-generated module page description (pre-current-template).
HISTORICAL_MODULE_DESC_TEMPLATE = "Documentation for {module}"

# Known machine-seeded gen-index descriptions produced by PRE-seeded-marker
# versions of selfdoc.  These hardcode "selfdoc" and so are wrong for every
# consuming project; they are treated as machine residue and reseeded.
LEGACY_INDEX_DESCRIPTIONS = frozenset({
    "Auto-generated API reference index",
    "Auto-generated API reference index for the selfdoc package — "
    "browse all public modules with their docstrings and source locations.",
    "Complete auto-generated API reference index — browse all modules, "
    "classes, and functions with their signatures and docstrings.",
})

# Current gen-index description formats:
#   "API reference index for {project_name} covering {n} module(s)"
#   "API reference index covering {n} module(s)"
# The project name and module count change over time (that is the whole point
# of staleness), so the format -- not a specific instantiation -- is matched.
_INDEX_DESC_RE = re.compile(
    r"^API reference index(?: for .+?)? covering \d+ modules?$"
)


def normalize_description(value):
    """Strip surrounding whitespace and one layer of matching quotes."""
    if value is None:
        return ""
    value = str(value).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()
    return value


def description_seed_hash(value):
    """SHA-256 of a (normalized) machine-emitted description string."""
    return hashlib.sha256(normalize_description(value).encode("utf-8")).hexdigest()


def _matches_seed_hash(value, seed_hash):
    return seed_hash is not None and description_seed_hash(value) == seed_hash


# -- Per-kind predicates -----------------------------------------------------


def is_machine_owned_module_description(value, module_name, seed_hash=None):
    """True if *value* is machine-owned for a module page named *module_name*."""
    v = normalize_description(value)
    if not v:
        return False
    if _matches_seed_hash(v, seed_hash):
        return True
    if module_name:
        if v == MODULE_DESC_TEMPLATE.format(module=module_name):
            return True
        if v == HISTORICAL_MODULE_DESC_TEMPLATE.format(module=module_name):
            return True
    return False


def is_machine_owned_index_description(value, seed_hash=None):
    """True if *value* is a machine-owned gen-index description."""
    v = normalize_description(value)
    if not v:
        return False
    if _matches_seed_hash(v, seed_hash):
        return True
    if v in LEGACY_INDEX_DESCRIPTIONS:
        return True
    if _INDEX_DESC_RE.match(v):
        return True
    return False


def is_machine_owned_cli_description(value, *, kind, name, app_name,
                                     help_text, seed_hash=None):
    """True if *value* is a machine-owned CLI page description."""
    v = normalize_description(value)
    if _matches_seed_hash(v, seed_hash):
        return True
    return is_default_cli_description(
        v, kind=kind, name=name, app_name=app_name, help_text=help_text,
    )


# -- Dispatcher --------------------------------------------------------------


def _lookup_cli(cli_structure, name):
    """Return (kind, help_text, app_name) for a CLI page name, or (None,...)."""
    if not cli_structure:
        return None, None, None
    app_name = cli_structure.get("app_name", "")
    for cmd in cli_structure.get("commands", []):
        if cmd.get("name") == name:
            return "command", cmd.get("help", ""), app_name
    for grp in cli_structure.get("groups", []):
        if grp.get("name") == name:
            return "group", grp.get("help", ""), app_name
    return None, None, None


def is_machine_owned(rel_path, frontmatter, *, seed_hash=None,
                     cli_structure=None):
    """Classify a page's description as machine-owned (True) or handwritten.

    ``rel_path`` selects the page kind by filename; ``frontmatter`` supplies
    the ``description`` (and ``title`` for module pages).  ``seed_hash`` is the
    per-page seed hash from the staleness store (``None`` when unrecorded).
    ``cli_structure`` is the parsed strictcli schema (needed to look up a CLI
    command's help text); pass ``None`` for non-strictcli projects.

    Handwritten text is never classified machine-owned.  Only ``generated``
    pages can be machine-owned -- a non-generated (hand-authored) page always
    returns False, so it receives full staleness protection.
    """
    description = frontmatter.get("description")
    generated = frontmatter.get("generated") is True

    if description is None:
        # No description text to classify.  Fall back to the frontmatter
        # skeleton signal for these edge pages (generated + seeded).
        return generated and frontmatter.get("seeded") is True

    if not generated:
        return False

    v = normalize_description(str(description))
    base = os.path.basename(rel_path)

    if base == "cli-index.md":
        app_name = (cli_structure or {}).get("app_name", "")
        return is_machine_owned_cli_description(
            v, kind="index", name=None, app_name=app_name,
            help_text=None, seed_hash=seed_hash,
        )

    if base.startswith("cli-") and base.endswith(".md"):
        name = base[len("cli-"):-len(".md")]
        kind, help_text, app_name = _lookup_cli(cli_structure, name)
        if kind is not None:
            return is_machine_owned_cli_description(
                v, kind=kind, name=name, app_name=app_name,
                help_text=help_text, seed_hash=seed_hash,
            )
        # Unknown CLI page (no schema available): trust only the seed hash.
        return _matches_seed_hash(v, seed_hash)

    if base == "gen-index.md":
        return is_machine_owned_index_description(v, seed_hash)

    # Module page: the title carries the module name.
    title = frontmatter.get("title")
    return is_machine_owned_module_description(
        v, str(title) if title else None, seed_hash,
    )

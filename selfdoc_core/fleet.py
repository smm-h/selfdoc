"""Enumerating the selfdoc projects that live beside this one.

Two tools need the same answer to "which sibling directories are selfdoc
projects, and can their configs be loaded?": the corpus-wide spelling run
(``selfdoc spell-corpus``) and the one-off lint-impact measurement in
``scripts/measure_lint_fleet.py``.  The enumeration used to live inside the
measurement script, where the second caller could not reach it.  It lives
here now, in the package, so both callers share one hardened implementation.

Hardened means every sibling is *reported*, never fatal.  A directory whose
``selfdoc.json`` is missing, unreadable or rejected by the config schema
comes back as a :class:`FleetProject` carrying the reason, and the caller
decides what to say about it.  A broken neighbour must not be able to stop
a corpus run over the rest of the fleet.

Everything here is read-only with respect to the projects it enumerates.
The one write is a sanitized *copy* of a config, placed in a caller-supplied
scratch directory, never in the project.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass

from selfdoc_core.config import ConfigError, load_config
from selfdoc_core.utils import parse_frontmatter

# Keys the config schema has retired but fleet configs still carry.  A
# project whose only load failure is one of these is loaded from a sanitized
# copy, and the result says so, because a retired key is stale scaffolding
# rather than a broken project.
RETIRED_VERSION_KEYS = ("indexed",)


@dataclass(frozen=True, slots=True)
class FleetProject:
    """One sibling directory carrying a ``selfdoc.json``.

    ``config`` is None exactly when ``error`` is set: the project was found
    but could not be loaded, and *why* is the error string.
    """

    name: str
    path: str
    config: dict | None
    sanitized: bool = False
    error: str | None = None

    @property
    def loaded(self) -> bool:
        """True when the config was read successfully."""
        return self.config is not None


def project_dirs(root: str) -> list[str]:
    """Return every immediate subdirectory of *root* holding a selfdoc.json.

    Sorted by name.  Dot-directories are skipped, so archives and caches
    under ``.archive/`` are not walked.  A *root* that does not exist yields
    nothing rather than raising: "no siblings" is a real answer.
    """
    if not os.path.isdir(root):
        return []
    return [
        os.path.join(root, name)
        for name in sorted(os.listdir(root))
        if not name.startswith(".")
        and os.path.isfile(os.path.join(root, name, "selfdoc.json"))
    ]


def load_project_config(project_dir: str, scratch_dir: str) -> tuple[dict, bool]:
    """Load *project_dir*'s config, retrying once without retired schema keys.

    Args:
        project_dir: Directory holding a ``selfdoc.json``.
        scratch_dir: Where a sanitized copy may be written.  Never the
            project itself.

    Returns:
        ``(config, sanitized)``, where *sanitized* is True when the config
        only loaded after retired keys were dropped from a copy.

    Raises:
        ConfigError: When the config is invalid for a reason retired keys do
            not explain.  Callers that enumerate the fleet should use
            :func:`discover_fleet`, which reports this instead.
    """
    try:
        return load_config(project_dir), False
    except ConfigError:
        pass

    with open(os.path.join(project_dir, "selfdoc.json"), encoding="utf-8") as f:
        raw = json.load(f)
    dropped = False
    for entry in raw.get("versions") or []:
        if not isinstance(entry, dict):
            continue
        for key in RETIRED_VERSION_KEYS:
            if key in entry:
                del entry[key]
                dropped = True
    if not dropped:
        # Nothing retired to blame -- re-raise the original diagnosis.
        return load_config(project_dir), False

    shadow = os.path.join(scratch_dir, os.path.basename(project_dir.rstrip("/")))
    os.makedirs(shadow, exist_ok=True)  # effects: exempt -- caller-owned scratch directory, never the project being read
    with open(os.path.join(shadow, "selfdoc.json"), "w", encoding="utf-8") as f:  # effects: exempt -- self-owned scratch copy of a config, written and read back to load it
        json.dump(raw, f)
    return load_config(shadow), True


def discover_fleet(root: str) -> list[FleetProject]:
    """Enumerate and load every selfdoc project directly under *root*.

    Never raises for a broken project: a config that cannot be read comes
    back with ``config=None`` and an ``error`` naming the failure.  The
    scratch directory used for sanitized config copies is created and
    removed here, so nothing survives the call.
    """
    scratch_dir = tempfile.mkdtemp(prefix="selfdoc-fleet-")
    found: list[FleetProject] = []
    try:
        for path in project_dirs(root):
            name = os.path.basename(path)
            try:
                config, sanitized = load_project_config(path, scratch_dir)
            except Exception as exc:  # noqa: BLE001 -- reported, never fatal
                found.append(FleetProject(
                    name=name, path=path, config=None,
                    error=f"{type(exc).__name__}: {exc}",
                ))
                continue
            if config is None:
                found.append(FleetProject(
                    name=name, path=path, config=None,
                    error="selfdoc.json disappeared while loading",
                ))
                continue
            found.append(FleetProject(
                name=name, path=path, config=config, sanitized=sanitized,
            ))
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)  # effects: exempt -- removes this call's own scratch directory
    return found


def load_docs_bodies(docs_dir: str) -> dict[str, tuple[dict, str, str, int]]:
    """Read a docs tree into the shape the lint rules consume.

    Frontmatter is parsed; directives are NOT resolved, because resolution
    runs a project's extractors over its source and a corpus pass must stay
    read-only and cheap over projects it does not own.  The resolved slot is
    therefore the empty string.

    Returns:
        ``{rel_path: (frontmatter, "", body, fm_line_count)}``, matching
        ``resolve_all_docs``.  Empty when *docs_dir* is not a directory.
    """
    bodies: dict[str, tuple[dict, str, str, int]] = {}
    if not os.path.isdir(docs_dir):
        return bodies
    for root, _dirs, files in os.walk(docs_dir):
        if "_build" in root.split(os.sep):
            continue
        for fname in sorted(files):
            if not fname.endswith(".md") or fname.startswith("_"):
                continue
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, docs_dir)
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            metadata, body = parse_frontmatter(content)
            fm_line_count = len(content.split("\n")) - len(body.split("\n"))
            bodies[rel_path] = (metadata, "", body, fm_line_count)
    return bodies

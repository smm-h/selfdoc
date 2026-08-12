"""The authoring app's repository registry: a hand-written TOML file.

This is not framework configuration.  It is one machine-local list of the
repositories the editor may open, written by hand by the one person the
editor serves, and read strictly: every key is known, every required key is
present, every name is unique and addressable in a URL, and every local path
really is a directory.  Anything else refuses and names the offender.

The strictness is the point.  A registry entry that quietly fails to parse is
a project whose posts silently stop being editable, with no error anywhere to
explain why -- so there is no shape here that is merely skipped.

Format
------

Two kinds of entry, both under ``[[repo]]``, both declaring their ``kind``::

    [[repo]]
    name = "selfdoc"
    kind = "local"
    path = "~/Projects/selfdoc"

    [[repo]]
    name = "afar"
    kind = "remote"
    repo = "smm-h/afar"
    ref = "v1.2.3"
    cache = "~/.cache/selfblog/afar"
    render = true

A remote entry is validated in full but not served yet: the server refuses it
with "remote entries not yet served" rather than pretending.  ``render`` is
required and has no default because directive resolution reads a source tree,
and whether a remote entry gets one is a decision the file has to state.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass

#: Where the registry lives.  Machine-local by design -- the editor writes
#: working trees on this machine and is not a published, shared surface, so
#: its list of repositories belongs beside the other machine-local records
#: rather than in any project's committed config.
DEFAULT_REGISTRY_PATH = os.path.join(
    os.path.expanduser("~"), "Projects", "ark", "selfblog-registry.toml",
)

#: A registry name is a URL path segment (``/api/repos/<name>/posts``) and a
#: nav key.  Restricting it here means path traversal cannot enter through a
#: registry entry, and a name never has to be escaped anywhere downstream.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_LOCAL_KEYS = frozenset({"name", "kind", "path"})
_REMOTE_KEYS = frozenset({"name", "kind", "repo", "ref", "cache", "render"})


class RegistryError(RuntimeError):
    """The registry file is unusable, and the message says exactly how."""


@dataclass(frozen=True)
class LocalRepo:
    """A working tree on this machine.  Edits land in it directly."""

    name: str
    path: str
    kind: str = "local"


@dataclass(frozen=True)
class RemoteRepo:
    """A repository elsewhere.  Validated here, not served yet.

    ``render`` states whether rendering runs against a checkout: directive
    resolution needs a source tree, so an entry that answers "no" can only
    ever serve prose.  It is required precisely because neither answer is
    safe to assume.
    """

    name: str
    repo: str
    ref: str
    cache: str
    render: bool
    kind: str = "remote"


class Registry:
    """The parsed registry: ordered entries, addressable by name."""

    def __init__(self, entries, path):
        self.entries = list(entries)
        self.path = path
        self._by_name = {entry.name: entry for entry in self.entries}

    def names(self):
        """Entry names, in the order the file declares them."""
        return [entry.name for entry in self.entries]

    def get(self, name):
        """The entry called *name*, or a refusal naming what is on offer."""
        try:
            return self._by_name[name]
        except KeyError:
            known = ", ".join(self.names()) or "(none)"
            raise RegistryError(
                f"No repository named {name!r} in {self.path}. "
                f"Known repositories: {known}."
            ) from None

    def __len__(self):
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)


def load_registry(path=None):
    """Read and validate the registry at *path*.

    Args:
        path: The registry file.  Defaults to :data:`DEFAULT_REGISTRY_PATH`.

    Returns:
        A :class:`Registry`.

    Raises:
        RegistryError: The file is missing, unparsable, or declares any shape
            this module does not accept.  The message names the offender.
    """
    path = path or DEFAULT_REGISTRY_PATH

    if not os.path.isfile(path):
        raise RegistryError(
            f"No editor registry at {path}. Create it with one [[repo]] "
            f"block per repository: name, kind, and (for kind = \"local\") "
            f"path."
        )

    with open(path, "rb") as handle:
        try:
            document = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise RegistryError(f"{path} is not valid TOML: {exc}") from None

    unknown = sorted(set(document) - {"repo"})
    if unknown:
        raise RegistryError(
            f"{path}: unknown top-level key(s) {', '.join(unknown)}. "
            f"The registry holds [[repo]] entries and nothing else."
        )

    raw_entries = document.get("repo", [])
    if not isinstance(raw_entries, list):
        raise RegistryError(
            f"{path}: 'repo' must be an array of tables ([[repo]]), got "
            f"{type(raw_entries).__name__}."
        )

    entries = []
    seen = {}
    for index, raw in enumerate(raw_entries):
        entry = _parse_entry(raw, index, path)
        if entry.name in seen:
            raise RegistryError(
                f"{path}: duplicate repository name {entry.name!r}, declared "
                f"by entry #{seen[entry.name] + 1} and entry #{index + 1}."
            )
        seen[entry.name] = index
        entries.append(entry)

    return Registry(entries, path)


def _parse_entry(raw, index, path):
    """Validate one ``[[repo]]`` table into a typed entry."""
    where = f"{path}: entry #{index + 1}"
    if not isinstance(raw, dict):
        raise RegistryError(
            f"{where}: each 'repo' element must be a table ([[repo]]), got "
            f"{type(raw).__name__}."
        )

    name = raw.get("name")
    if name is None:
        raise RegistryError(f"{where}: 'name' is required.")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise RegistryError(
            f"{where}: 'name' must be a URL-addressable identifier "
            f"(letters, digits, dot, dash, underscore; no slashes, no "
            f"spaces), got {name!r}."
        )

    where = f"{path}: repository {name!r}"

    kind = raw.get("kind")
    if kind is None:
        raise RegistryError(
            f"{where}: 'kind' is required and has no default. Declare "
            f'kind = "local" for a working tree on this machine, or '
            f'kind = "remote" for a repository elsewhere.'
        )
    if kind == "local":
        return _parse_local(raw, name, where)
    if kind == "remote":
        return _parse_remote(raw, name, where)
    raise RegistryError(
        f"{where}: unknown kind {kind!r}. Valid kinds are \"local\" and "
        f"\"remote\"."
    )


def _reject_unknown_keys(raw, allowed, where, kind):
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise RegistryError(
            f"{where}: unknown key(s) {', '.join(unknown)} on a {kind} "
            f"entry. A {kind} entry takes: {', '.join(sorted(allowed))}."
        )


def _require_string(raw, key, where):
    value = raw.get(key)
    if value is None:
        raise RegistryError(f"{where}: {key!r} is required.")
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(
            f"{where}: {key!r} must be a non-empty string, got {value!r}."
        )
    return value


def _parse_local(raw, name, where):
    _reject_unknown_keys(raw, _LOCAL_KEYS, where, "local")
    path = os.path.abspath(os.path.expanduser(_require_string(raw, "path", where)))
    if not os.path.isdir(path):
        raise RegistryError(
            f"{where}: path {path} is not a directory. A local entry names a "
            f"working tree on this machine."
        )
    return LocalRepo(name=name, path=path)


def _parse_remote(raw, name, where):
    _reject_unknown_keys(raw, _REMOTE_KEYS, where, "remote")
    repo = _require_string(raw, "repo", where)
    ref = _require_string(raw, "ref", where)
    cache = os.path.abspath(
        os.path.expanduser(_require_string(raw, "cache", where)),
    )

    render = raw.get("render")
    if render is None:
        raise RegistryError(
            f"{where}: 'render' is required and has no default. Declare "
            f"render = true if rendering runs against a checkout of this "
            f"repository (directive resolution needs a source tree), or "
            f"render = false if it does not."
        )
    if not isinstance(render, bool):
        raise RegistryError(
            f"{where}: 'render' must be true or false, got {render!r}."
        )

    return RemoteRepo(
        name=name, repo=repo, ref=ref, cache=cache, render=render,
    )

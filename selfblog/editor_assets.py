"""Where the editor's front-end comes from, declared rather than discovered.

Two asset trees are served: tinymoon's (the framework chrome plus the editor
tier the authoring surface is built on) and the editor's own (the shell page,
its module, its stylesheet).  The second ships inside this package.  The
first does not -- selfblog depends on strictcli and selfdoc-core and nothing
else, and tinymoon is not going to become a runtime dependency for a
local-only command.

So the caller states where tinymoon's assets are.  There are exactly two
answers and the caller picks one before anything binds a port:

* a path, from ``--tinymoon-assets`` -- a checkout's ``assets/`` directory;
* nothing, meaning "the installed tinymoon package", read through its own
  ``assets_path()``.

Neither is a fallback for the other: an absent package with no flag is a hard
error naming the flag, not a quiet switch to some other tree.  Either way the
resolved tree is checked for every file the shell loads, including the editor
tier, and a tree missing any of them is refused with all the missing names.
That refusal exists because the alternative is a shell that loads, renders
its chrome, and never mounts an editor -- a failure that looks like a bug in
the app rather than a missing dependency.
"""

from __future__ import annotations

import importlib.resources
import os

#: The three files that make up tinymoon's editor tier.  Newer than any
#: released tinymoon at the time of writing, which is exactly why the
#: ``--tinymoon-assets`` path exists.
TINYMOON_EDITOR_TIER = (
    "js/editor.js",
    "js/completion.js",
    "css/editor.css",
)

#: Every tinymoon file the editor shell names DIRECTLY -- the stylesheets its
#: page links, in the framework's own load order, and the modules its app
#: imports by name.  Not the transitive module graph: those imports resolve
#: inside the served tree at load time, and enumerating them here would be a
#: copy of tinymoon's internals that goes stale on its next refactor.  The
#: editor tier is the one exception: ``js/completion.js`` is reached only
#: through ``js/editor.js``, and it is named anyway because the tier's
#: presence is the thing being checked.  A test keeps this list and the
#: shell's own references in step in both directions.
TINYMOON_REQUIRED = (
    "css/tokens.css",
    "css/base.css",
    "css/shell.css",
    "css/primitives.css",
    "css/widgets.css",
    "css/editor.css",
    "js/dom.js",
    "js/shell.js",
    "js/view.js",
    "js/states.js",
    "js/toast.js",
    "js/modal.js",
    "js/settings.js",
    "js/editor.js",
    "js/completion.js",
)


class AssetsError(RuntimeError):
    """The front-end assets cannot be served, and the message says why."""


def ui_assets_path():
    """The directory holding the editor's own shell page, module and CSS."""
    return str(importlib.resources.files("selfblog").joinpath("editor_ui"))


def resolve_tinymoon_assets(explicit=""):
    """Resolve tinymoon's asset tree, or refuse.

    Args:
        explicit: A path to a tinymoon ``assets/`` directory.  Empty means
            "read it from the installed tinymoon package".

    Returns:
        ``(path, source)`` -- the resolved directory and a human-readable
        note about where it came from, which the command prints so a session
        never has to guess which tinymoon it is looking at.

    Raises:
        AssetsError: The path is not a directory, the package is not
            installed, or the tree is missing files the shell loads.
    """
    if explicit:
        path = os.path.abspath(os.path.expanduser(explicit))
        if not os.path.isdir(path):
            raise AssetsError(
                f"--tinymoon-assets {path} is not a directory. Point it at a "
                f"tinymoon checkout's 'assets' directory."
            )
        source = path
    else:
        path, source = _installed_tinymoon()

    _require_tree(path, source)
    return path, source


def _installed_tinymoon():
    """The installed tinymoon package's asset tree, or a refusal."""
    try:
        import tinymoon
    except ImportError as exc:
        raise AssetsError(
            "The editor serves tinymoon's assets and no tinymoon package is "
            "installed in this environment. Either install tinymoon, or pass "
            "--tinymoon-assets <path-to-tinymoon>/assets to serve them from a "
            "checkout. (The editor tier -- js/editor.js, js/completion.js, "
            "css/editor.css -- is newer than the released package, so a "
            "checkout is currently the only complete source.)"
        ) from exc

    try:
        path = str(tinymoon.assets_path())
    except FileNotFoundError as exc:
        raise AssetsError(
            f"The installed tinymoon package has no assets directory: {exc}"
        ) from exc

    version = getattr(tinymoon, "__version__", "unknown")
    return path, f"installed tinymoon {version} ({path})"


def _require_tree(path, source):
    """Refuse a tree missing anything the shell loads, naming all of it."""
    missing = [
        rel for rel in TINYMOON_REQUIRED
        if not os.path.isfile(os.path.join(path, *rel.split("/")))
    ]
    if not missing:
        return

    tier = [rel for rel in missing if rel in TINYMOON_EDITOR_TIER]
    note = ""
    if tier:
        note = (
            " The editor tier (" + ", ".join(TINYMOON_EDITOR_TIER) + ") is "
            "newer than the released tinymoon package; serve the assets from "
            "a checkout with --tinymoon-assets <path-to-tinymoon>/assets."
        )
    raise AssetsError(
        f"The tinymoon assets at {source} are missing "
        f"{len(missing)} file(s) the editor loads: {', '.join(missing)}.{note}"
    )

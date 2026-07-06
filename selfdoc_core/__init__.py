"""selfdoc_core: Shared engine for code-aware documentation generation.

This package contains the core build pipeline, HTML generation, directive
parsing, language extractors, theming, and all shared infrastructure used
by both selfdoc (code-aware docs) and selfblog (blog system).
"""

from selfdoc_core._version import __version__  # noqa: F401

# -- Directive registry -------------------------------------------------------
#
# The directive registry allows packages (selfdoc, selfblog) to register
# custom directive resolvers without core knowing about them.  Core's
# resolve_content() checks the registry AFTER its built-in directives.
#
# Each entry maps a directive name to a resolver callable with signature:
#   (name: str, attrs: dict, body: list[str], base_dir: str,
#    *, config: dict | None) -> str | None
#
# Resolvers return the replacement Markdown/HTML string, or None if they
# cannot handle the directive (which would be a bug -- only register
# directives you own).

_directive_registry: dict[str, object] = {}


def register_directive(name: str, resolver: object) -> None:
    """Register a custom directive resolver.

    Args:
        name: Directive name (e.g. "table-commands").
        resolver: Callable matching the content directive resolver signature.

    Raises:
        ValueError: If the name is already registered.
    """
    if name in _directive_registry:
        raise ValueError(
            f"directive {name!r} is already registered"
        )
    _directive_registry[name] = resolver


def get_directive_registry() -> dict[str, object]:
    """Return the current directive registry (read-only view)."""
    return dict(_directive_registry)


# -- Posts-injection hook -----------------------------------------------------
#
# The posts-injection hook allows selfblog to register its post-injection
# implementation without core importing selfblog.  Core's build() calls the
# registered hook to inject blog posts into the docs pipeline.
#
# The hook signature is:
#   (dir_path: str, config: dict, docs_dir: str, include_drafts: bool)
#       -> list[str]  (list of absolute paths to injected files)
#
# If posts are configured in selfdoc.json but no hook is registered,
# build() raises a hard error (posts-configured-but-no-hook = HARD ERROR).

_posts_injection_hook: object | None = None


def register_posts_hook(hook: object) -> None:
    """Register the posts-injection hook.

    Args:
        hook: Callable matching the posts-injection hook signature.

    Raises:
        ValueError: If a hook is already registered.
    """
    global _posts_injection_hook
    if _posts_injection_hook is not None:
        raise ValueError("posts-injection hook is already registered")
    _posts_injection_hook = hook


def get_posts_hook() -> object | None:
    """Return the registered posts-injection hook, or None."""
    return _posts_injection_hook

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


# -- Post provider ------------------------------------------------------------
#
# The post provider allows selfblog to supply its post-discovery
# implementation without core importing selfblog.  The provider is a
# ``discover_posts`` callable with signature:
#
#   (posts_dir: str, manifest_path: str | None = None) -> list[dict]
#
# Core's build pipeline calls the registered provider whenever posts are
# present.  If posts are present but no provider is registered,
# require_post_provider() raises a hard error naming selfblog.

_post_provider: object | None = None


def register_post_provider(provider: object) -> None:
    """Register the post provider (selfblog's ``discover_posts``).

    Registering the same callable again is a no-op, so repeated imports
    of the registering package are safe.

    Args:
        provider: Callable matching the post provider signature.

    Raises:
        ValueError: If a different provider is already registered.
    """
    global _post_provider
    if _post_provider is not None and _post_provider is not provider:
        raise ValueError("a different post provider is already registered")
    _post_provider = provider


def get_post_provider() -> object | None:
    """Return the registered post provider, or None."""
    return _post_provider


def require_post_provider() -> object:
    """Return the registered post provider, or raise a hard error.

    Raises:
        RuntimeError: If no provider is registered.  Blog posts are
            handled by selfblog; the error directs the user there.
    """
    if _post_provider is None:
        raise RuntimeError(
            "Posts are present but no post provider is registered. "
            "Blog posts are handled by selfblog -- install it "
            "(pip install selfblog) and run post operations through "
            "the selfblog CLI."
        )
    return _post_provider

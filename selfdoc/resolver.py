"""Resolver factory -- dispatches directives to language-specific extractors."""

import os


def make_resolver(config, base_dir="."):
    """Create a resolver function for the project's language.

    Args:
        config: Validated config dict from selfdoc.json.
        base_dir: Project root directory (for resolving relative paths).

    Returns:
        A callable(name, arg, body) -> str that resolves directives to markdown.
    """
    language = config["language"]
    source_paths = config["source"]
    # Normalize base_dir to absolute for consistent path resolution
    base_dir = os.path.abspath(base_dir)

    def resolve(name, arg, body):
        if language == "python":
            from .extractors.python import resolve_python

            return resolve_python(name, arg, body, source_paths, base_dir)
        if language == "go":
            from .extractors.go import resolve_go

            return resolve_go(name, arg, body, source_paths, base_dir)
        if language in ("typescript", "javascript"):
            from .extractors.typescript import resolve_typescript

            return resolve_typescript(name, arg, body, source_paths, base_dir)
        return (
            f"> *[selfdoc: unsupported language '{language}' "
            f"for :::{name} {arg}]*"
        )

    return resolve

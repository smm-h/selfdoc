"""Resolver factory -- dispatches directives to language-specific extractors."""

import importlib.util
import os

from selfdoc_core.content import resolve_content
from selfdoc_core.extractors import SourceEntry


def _load_custom_directive(script_path, name):
    """Dynamically import a custom directive script and return its module.

    Args:
        script_path: Absolute path to the Python script.
        name: Directive name (used as the module name for importlib).

    Returns:
        The loaded module, or None if loading fails.

    Raises:
        FileNotFoundError: If the script file does not exist.
        AttributeError: If the module has no 'resolve' callable.
        Exception: Any other import/load error.
    """
    if not os.path.isfile(script_path):
        raise FileNotFoundError(f"custom directive script not found: {script_path}")

    spec = importlib.util.spec_from_file_location(
        f"selfdoc_custom_{name}", script_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not callable(getattr(module, "resolve", None)):
        raise AttributeError(
            f"custom directive script '{script_path}' has no callable 'resolve'"
        )

    return module


class Resolver:
    """Multi-language directive resolver.

    Groups source entries by (language, extractor) and dispatches each
    directive to the correct language extractor based on path resolution.
    Tracks the last matched source entry for downstream consumers.
    """

    def __init__(self, config, base_dir="."):
        from selfdoc_core.extractors import resolve_source_entries

        self.last_source_entry: SourceEntry | None = None
        self._config = config
        self._base_dir = os.path.abspath(base_dir)
        self._custom_directives = config.get("directives", {})

        src_entries = resolve_source_entries(config)

        # Group source entries by (language, extractor) so each group
        # collects all paths for one language.
        seen: dict[str, tuple[str, object, list[str]]] = {}
        for entry in src_entries:
            key = entry.language
            if key not in seen:
                seen[key] = (entry.language, entry.extractor, [])
            seen[key][2].append(entry.path)
        self._groups: list[tuple[str, object, list[str]]] = list(seen.values())

    def __call__(self, name, attrs, body) -> str:
        """Resolve a directive by name, attributes, and body.

        Tries content directives first (language-agnostic), then custom
        directives, then dispatches to language extractors. For multi-
        language projects, resolves which language group matches the
        directive's path argument and errors on ambiguity.
        """
        self.last_source_entry = None

        # Content directives (callouts, glossary, tree, deps, features,
        # modules, commands, directives, config-schema, var)
        content_result = resolve_content(
            name, attrs, body, self._base_dir, config=self._config,
        )
        if content_result is not None:
            return content_result

        # Custom directives take priority over built-in names
        if name in self._custom_directives:
            script_rel = self._custom_directives[name]
            script_path = os.path.join(self._base_dir, script_rel)
            try:
                module = _load_custom_directive(script_path, name)
                return module.resolve(attrs, self._config, body)
            except Exception as exc:
                return (
                    f"> *[selfdoc: custom directive '{name}' failed: {exc}]*"
                )

        # No language groups configured.  Everything that reaches this point
        # extracts from source code, and a codeless project has none.  Raise:
        # rendering a placeholder note here would silently turn a page that
        # asks for an API reference into a page that has none.
        if not self._groups:
            raise RuntimeError(
                f"Directive :-: {name} extracts from source code, but "
                "selfdoc.json declares no 'source' entries. Either remove "
                "the directive, or declare the code it should read: "
                '"source": [{"path": "src/", "language": "python"}]'
            )

        # Single language group: dispatch directly (no ambiguity possible)
        if len(self._groups) == 1:
            language, extractor, paths = self._groups[0]
            result = extractor.extract(
                name, attrs, body, paths, self._base_dir,
            )
            # Set last_source_entry if path resolved
            path_arg = attrs.get("path", "")
            if path_arg:
                resolved = extractor.resolve_path(
                    path_arg, paths, self._base_dir,
                )
                if resolved is not None:
                    self.last_source_entry = SourceEntry(
                        path=paths[0], language=language, extractor=extractor,
                    )
            return result

        # Multi-language dispatch: find which group(s) can resolve the path
        path_arg = attrs.get("path", "")
        lang_filter = attrs.get("lang", "")

        # When lang is specified, only consider groups for that language
        groups = self._groups
        if lang_filter:
            groups = [g for g in groups if g[0] == lang_filter]

        matches: list[tuple[str, object, list[str], str]] = []
        for language, extractor, paths in groups:
            resolved = extractor.resolve_path(
                path_arg, paths, self._base_dir,
            )
            if resolved is not None:
                matches.append((language, extractor, paths, resolved))

        if len(matches) == 1:
            language, extractor, paths, _resolved = matches[0]
            self.last_source_entry = SourceEntry(
                path=paths[0], language=language, extractor=extractor,
            )
            return extractor.extract(
                name, attrs, body, paths, self._base_dir,
            )

        if len(matches) > 1:
            langs = ", ".join(m[0] for m in matches)
            raise RuntimeError(
                f"Ambiguous directive :::{name} path={path_arg!r} "
                f"resolves in multiple languages: {langs}"
            )

        # Zero matches
        if lang_filter and not groups:
            # lang specified a language that is not configured
            configured = ", ".join(g[0] for g in self._groups)
            return (
                f"> *[selfdoc: lang={lang_filter!r} not found in "
                f"configured source languages: {configured}]*"
            )

        # Use the first group for error reporting (extractor produces
        # a "not found" message for the unresolvable path)
        language, extractor, paths = (groups or self._groups)[0]
        return extractor.extract(
            name, attrs, body, paths, self._base_dir,
        )


def make_resolver(config, base_dir="."):
    """Create a resolver callable for the project.

    Returns a Resolver instance (callable) that dispatches directives
    to language-specific extractors. The returned object also exposes
    ``last_source_entry`` for tracking which source entry matched.

    Args:
        config: Validated config dict from selfdoc_core.json.
        base_dir: Project root directory (for resolving relative paths).

    Returns:
        A Resolver instance (callable(name, attrs, body) -> str).
    """
    return Resolver(config, base_dir)

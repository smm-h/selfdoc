"""Auto-generate documentation pages from project structure."""

import fnmatch
import os
import re
import stat
from dataclasses import dataclass, field

from selfdoc.utils import parse_frontmatter as _parse_frontmatter
from selfdoc_core.prose import first_sentence
from selfdoc.catalog import ALL_BUILTIN_DIRECTIVES
from selfdoc.directives import resolve_directives, validate_directive_names
from selfdoc.resolver import make_resolver
from selfdoc.utils import atomic_write as _atomic_write
from selfdoc.ownership import (
    MODULE_DESC_TEMPLATE,
    LEGACY_INDEX_DESCRIPTIONS as _LEGACY_INDEX_DESCRIPTIONS,
    description_seed_hash,
    is_machine_owned_index_description,
    is_machine_owned_module_description,
)
from selfdoc_core.staleness import load_hashes, save_hashes


@dataclass
class GenResult:
    """Result of a generate_docs call, tracking written and deleted files."""

    written: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)


# Default exclusion patterns (always applied in addition to user-configured ones).
# These are matched against both the full relative path and the basename,
# so ``test_*`` will match ``test_core.py`` at any depth.
_DEFAULT_EXCLUDES = [
    "test_*",
    "*_test.*",
    "__pycache__",
    "tests",
]

# Directories that should ALWAYS be pruned from os.walk during source walks.
# Modifying dirs[:] in-place prevents os.walk from descending into these.
_SKIP_DIRS = {
    ".venv", "venv", "node_modules", "__pycache__", ".git", ".hg",
    ".svn", "dist", "build", "_build", ".tox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".zig-cache", "zig-cache",
}


def _should_skip_dir(dirname):
    """Return True if a directory name should be pruned during source walks."""
    if dirname in _SKIP_DIRS:
        return True
    # Also skip directories ending in .egg-info (e.g. mylib.egg-info)
    if dirname.endswith(".egg-info"):
        return True
    return False


def _has_generated_marker(filepath):
    """Check whether a Markdown file has ``generated: true`` in its frontmatter.

    Returns True if the file starts with ``---`` frontmatter containing
    ``generated: true``, False otherwise (including when the file does
    not exist or cannot be read).
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return False

    if not content.startswith("---"):
        return False

    lines = content.split("\n")
    for idx in range(1, len(lines)):
        line = lines[idx].strip()
        if line == "---":
            break
        if line == "generated: true":
            return True
    return False


def _file_to_module_path(file_path, base_dir, language):
    """Convert a source file path to a module/package path string.

    The path is computed relative to ``base_dir`` (the project root) so
    that the resulting module path matches what ``:-: ref path="..."``
    expects.

    For Python: ``mylib/config.py`` -> ``mylib.config``
    For Go: ``pkg/handler.go`` -> ``pkg/handler``
    For TypeScript/JavaScript: ``src/utils.ts`` -> ``src/utils``
    """
    # Make path relative to the project root
    rel = os.path.relpath(file_path, base_dir)

    # Strip extension
    root, _ext = os.path.splitext(rel)

    if language == "python":
        # Remove trailing /__init__ for package init files
        if root.endswith("/__init__") or root == "__init__":
            root = root.rsplit("/__init__", 1)[0] if "/" in root else ""
        if not root:
            return None
        # Convert path separators to dots
        return root.replace(os.sep, ".").replace("/", ".")

    # Go, TypeScript, JavaScript: keep path separators as slashes
    return root.replace(os.sep, "/")


def _module_to_filename(module_path, language):
    """Convert a module path to a Markdown filename for docs/.

    Replaces dots (Python) or slashes (Go/TS/JS) with dashes.
    E.g. ``selfdoc.config`` -> ``selfdoc-config.md``
    E.g. ``pkg/handler`` -> ``pkg-handler.md``
    """
    if language == "python":
        return module_path.replace(".", "-") + ".md"
    return module_path.replace("/", "-") + ".md"


def _staleness_store_key(config, locale_dir_code, filename):
    """Compute the hashes.json key for a generated page.

    Mirrors the locale-prefixing that build.py and check.py apply so that gen
    writes ``seed_hash`` under the same key those layers read/write.  When
    locales are configured, keys are prefixed with the first locale's code
    (matching check_docs); ``locale_dir_code`` is the subdirectory a page was
    written under ("" for single-locale projects without a locale subdir).
    """
    rp_top = os.path.join(locale_dir_code, filename) if locale_dir_code else filename
    rp_top = rp_top.replace(os.sep, "/")
    locales = config.get("locales") or []
    if locales:
        return f"{locales[0]['code']}/{rp_top}"
    return rp_top


def _read_go_module_name(base_dir):
    """Read the module name from go.mod in base_dir.

    Returns the last path segment of the module path (e.g. "myapp" from
    "github.com/user/myapp"), or None if go.mod is missing or unparseable.
    """
    go_mod = os.path.join(base_dir, "go.mod")
    try:
        with open(go_mod, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("module "):
                    module_path = line[len("module "):].strip()
                    # Last segment of the module path
                    return module_path.rstrip("/").rsplit("/", 1)[-1]
    except OSError:
        pass
    return None


def _go_root_package_name(base_dir):
    """Determine the filename stem for the root Go package.

    Reads the module name from go.mod; falls back to the project directory
    basename.
    """
    name = _read_go_module_name(base_dir)
    if name:
        return name
    return os.path.basename(os.path.abspath(base_dir))


def _collect_go_packages(source_paths, base_dir, exclude_patterns):
    """Walk source paths and group .go files by parent directory (package).

    Returns a list of (module_path, pkg_dir_abs) tuples sorted by module_path.
    Excludes test files and files matching exclude_patterns.
    The module_path is source-path-qualified: for a root package under
    ``router/``, the module_path is ``"router"`` (not ``"."``).  For a
    sub-package ``middleware/`` under ``router/``, it is
    ``"router/middleware"``.  This ensures uniqueness across multiple
    source paths.
    """
    packages = {}  # module_path -> pkg_dir absolute path

    for sp in source_paths:
        source_root = os.path.join(base_dir, sp.rstrip("/"))
        if not os.path.isdir(source_root):
            continue

        # The source path prefix used to qualify module paths.
        # e.g. "router/" -> "router", "." -> ""
        sp_prefix = sp.rstrip("/")
        if sp_prefix == ".":
            sp_prefix = ""

        for dirpath, dirnames, filenames in os.walk(source_root):
            dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
            has_go_file = False
            for fname in filenames:
                if not fname.endswith(".go"):
                    continue
                if fname.endswith("_test.go"):
                    continue

                full_path = os.path.join(dirpath, fname)
                rel_to_source = os.path.relpath(full_path, source_root)

                if _is_excluded(rel_to_source, exclude_patterns):
                    continue

                has_go_file = True

            if has_go_file:
                rel_dir = os.path.relpath(dirpath, source_root)
                # Normalise to forward slashes
                if rel_dir == ".":
                    # Root of this source path -- use source path name
                    if sp_prefix:
                        module_path = sp_prefix
                    else:
                        module_path = "."
                else:
                    rel_normalized = rel_dir.replace(os.sep, "/")
                    if sp_prefix:
                        module_path = sp_prefix + "/" + rel_normalized
                    else:
                        module_path = rel_normalized

                # Check exclusion against the package path itself
                if module_path != "." and _is_excluded(
                    module_path, exclude_patterns
                ):
                    continue

                if module_path not in packages:
                    packages[module_path] = os.path.abspath(dirpath)

    return sorted(packages.items(), key=lambda t: t[0])


def _is_excluded(rel_path, exclude_patterns):
    """Check whether a relative path matches any exclusion glob pattern.

    Supports ``**/`` prefix as "match at any depth" by stripping the
    prefix and testing against every path component and the basename.
    Plain patterns are matched against the full path, the basename, and
    each directory component.
    """
    # Normalise to forward slashes for consistent matching
    normalized = rel_path.replace(os.sep, "/")
    parts = normalized.split("/")
    basename = parts[-1]
    dir_parts = parts[:-1]
    for pattern in exclude_patterns:
        # Strip leading **/ for "any depth" semantics
        stripped = pattern
        while stripped.startswith("**/"):
            stripped = stripped[3:]

        if fnmatch.fnmatch(normalized, stripped):
            return True
        if fnmatch.fnmatch(basename, stripped):
            return True
        # Check each directory component
        for part in dir_parts:
            if fnmatch.fnmatch(part, stripped):
                return True
        # Also try the original pattern against the full path
        if pattern != stripped and fnmatch.fnmatch(normalized, pattern):
            return True
    return False


def _read_existing_description(filepath, module_name=None, seed_hash=None):
    """Return the hand-edited module-page ``description``, or ``None`` to reseed.

    Consults the ownership predicate rather than trusting the ``seeded: true``
    frontmatter flag: a description is recomputed (returns ``None``) only when
    it is machine-owned -- i.e. it matches the current/historical module
    template for *module_name*, or the recorded *seed_hash*.  Any other text is
    a genuine hand edit and is preserved verbatim, EVEN IF a stale
    ``seeded: true`` flag is still present (the "human rewrote but forgot to
    remove seeded:true" trap is dead).
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None

    metadata, _ = _parse_frontmatter(content)

    raw = metadata.get("description")
    if raw is None or not isinstance(raw, str):
        return None

    # Strip wrapping quotes (single or double) that may survive the simple
    # parser in build.py.
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()

    if not value:
        return None

    if is_machine_owned_module_description(value, module_name, seed_hash):
        return None

    return value


def _generate_page_content(module_name, module_path, nav_order,
                           existing_description=None,
                           docstring_description=None,
                           language=None):
    """Build the Markdown content for a generated documentation page.

    If ``existing_description`` is provided, it is used verbatim as the page's
    ``description`` frontmatter value.  Otherwise, if ``docstring_description``
    is provided (extracted from the module's docstring), it is used.  Finally,
    if neither is available, the default auto-generated template is used.

    When the description is auto-generated (not from ``existing_description``),
    ``seeded: true`` is added to frontmatter to indicate the description was
    machine-generated and hasn't been hand-edited.

    ``language`` is emitted as a ``lang`` attribute on the ref directive to
    disambiguate in multi-language projects.
    """
    if existing_description is not None:
        desc = existing_description
        seeded = False
    elif docstring_description is not None:
        desc = docstring_description
        seeded = True
    else:
        desc = MODULE_DESC_TEMPLATE.format(module=module_name)
        seeded = True
    seeded_line = "seeded: true\n" if seeded else ""
    lang_attr = f' lang="{language}"' if language else ""
    return (
        f"---\n"
        f"title: {module_name}\n"
        f"description: \"{desc}\"\n"
        f"generated: true\n"
        f"{seeded_line}"
        f'nav_group: "API Reference"\n'
        f"nav_order: {nav_order}\n"
        f"---\n"
        f"<!-- generated by selfdoc gen, do not edit -->\n"
        f"\n"
        f"# {module_name}\n"
        f"\n"
        f':-: ref path="{module_path}"{lang_attr}\n'
    )


def _resolve_project_name(config, base_dir):
    """Resolve the project name for the API reference index description.

    Resolution order (single source of truth: the config ``name`` key):

    1. Explicit top-level ``name`` in selfdoc.json wins.
    2. Otherwise, when there is exactly one source entry, derive the name
       from it (an unambiguous single-source project): a root source path
       (``.`` / ``/`` / empty) resolves to the project directory basename;
       any other single path resolves to its basename.
    3. Otherwise (zero or multiple source entries), return ``None`` -- the
       name is ambiguous, and a generic count-only description is used
       instead. Generic beats wrong.
    """
    name = config.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()

    source_entries = config.get("source", [])
    if len(source_entries) == 1:
        raw_path = source_entries[0].get("path", "")
        stripped = raw_path.strip("/")
        if stripped in ("", "."):
            return os.path.basename(os.path.abspath(base_dir))
        return stripped.split("/")[-1]

    return None


def _read_existing_index_description(filepath, seed_hash=None):
    """Return the hand-edited gen-index description, or ``None`` to reseed.

    Consults the ownership predicate: returns ``None`` (recompute + add
    ``seeded: true``) when the description is machine-owned -- i.e. it matches
    the current index format, a KNOWN legacy machine-seed phrase, or the
    recorded *seed_hash*.  Any other description is a genuine hand edit and is
    preserved verbatim, regardless of a stale ``seeded: true`` flag.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None

    metadata, _ = _parse_frontmatter(content)

    raw = metadata.get("description")
    if raw is None or not isinstance(raw, str):
        return None

    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()

    if not value:
        return None

    if is_machine_owned_index_description(value, seed_hash):
        return None

    return value


def _generate_index_content(generated_pages, project_name,
                            existing_description=None):
    """Build the gen-index.md page listing all generated pages with links.

    ``generated_pages`` is a list of (module_name, md_filename) tuples,
    already sorted by module name.

    ``project_name`` is used to derive the auto-generated description. When
    it is ``None`` (an ambiguous multi-source project with no configured
    ``name``), a generic count-only description with no project name is used
    instead -- generic beats wrong.

    If ``existing_description`` is provided (from a hand-edited page),
    it is preserved verbatim.  Otherwise, a content-aware description
    is generated from the project name and module count, and
    ``seeded: true`` is added to frontmatter.
    """
    n = len(generated_pages)
    if existing_description is not None:
        desc = existing_description
        seeded = False
    else:
        module_phrase = f"covering {n} module{'s' if n != 1 else ''}"
        if project_name:
            desc = f"API reference index for {project_name} {module_phrase}"
        else:
            desc = f"API reference index {module_phrase}"
        seeded = True
    lines = [
        "---",
        "title: API Reference",
        f'description: "{desc}"',
        "generated: true",
    ]
    if seeded:
        lines.append("seeded: true")
    lines.extend([
        'nav_group: "API Reference"',
        "nav_order: 0",
        "order: 90",
        "---",
        "<!-- generated by selfdoc gen, do not edit -->",
        "",
        "# API Reference",
        "",
    ])
    for module_name, md_filename in generated_pages:
        # Link to the sibling page (same docs/ directory)
        html_name = md_filename.replace(".md", ".html")
        lines.append(f"- [{module_name}]({html_name})")
    lines.append("")
    return "\n".join(lines)


def _remove_stale_generated(docs_dir, new_filenames):
    """Delete previously generated files that are no longer in the new set.

    Only removes files whose frontmatter contains ``generated: true``.

    Returns a list of deleted filenames (basenames, not full paths).
    """
    deleted = []
    new_set = set(new_filenames)
    for entry in os.listdir(docs_dir):
        if not entry.endswith(".md"):
            continue
        if entry in new_set:
            continue
        full = os.path.join(docs_dir, entry)
        if os.path.isfile(full) and _has_generated_marker(full):
            os.unlink(full)
            deleted.append(entry)
    return deleted


def _get_locale_docs_dirs(config, base_dir):
    """Return a list of (locale_code, docs_dir) for generation.

    For single-locale projects without locale subdirectories, returns
    [("", docs_dir)] so generation goes to docs/ directly.
    For multi-locale projects, returns [(code, docs/code/), ...] for
    each configured locale.
    """
    locales = config.get("locales")
    docs_rel = config.get("docs", "docs/").rstrip("/")
    docs_dir = os.path.join(base_dir, docs_rel)

    if not locales or len(locales) == 0:
        return [("", docs_dir)]

    if len(locales) == 1:
        code = locales[0]["code"]
        locale_dir = os.path.join(docs_dir, code)
        if os.path.isdir(locale_dir):
            return [(code, locale_dir)]
        # Single locale without subdir -- use docs/ directly
        return [("", docs_dir)]

    # Multiple locales: generate into each locale subdir
    result = []
    for loc in locales:
        code = loc["code"]
        locale_dir = os.path.join(docs_dir, code)
        result.append((code, locale_dir))
    return result


def generate_docs(config, base_dir="."):
    """Auto-discover project source files and generate documentation pages.

    For multi-language projects, groups source entries by language and
    runs a generation pass for each language group.  Stale cleanup runs
    once after all groups so one language's output is never deleted by
    another's pass.

    For multi-locale projects, generates pages under docs/{locale_code}/
    for each configured locale. For single-locale projects without locale
    subdirectories, generates directly under docs/.

    Returns a ``GenResult`` with written and deleted file paths relative
    to the docs directory.
    """
    from selfdoc.extractors import resolve_source_entries, source_paths as _source_paths

    src_entries = resolve_source_entries(config)

    # Group entries by (language, extractor identity) so each group
    # collects all source paths for one language.
    groups: dict[tuple[str, int], tuple[str, object, list[str]]] = {}
    for entry in src_entries:
        key = (entry.language, id(entry.extractor))
        if key not in groups:
            groups[key] = (entry.language, entry.extractor, [])
        groups[key][2].append(entry.path)

    all_source_paths = _source_paths(config)

    locale_dirs = _get_locale_docs_dirs(config, base_dir)
    all_written = []
    all_deleted = []

    # Resolve strictcli structure once (shared across locales)
    from selfdoc.strictcli_support import (
        uses_strictcli,
        extract_cli_structure,
        generate_cli_pages,
        expected_cli_page_filenames,
    )
    cli_structure = None
    if uses_strictcli(all_source_paths, base_dir):
        cli_structure = extract_cli_structure(all_source_paths, base_dir)
    cli_page_names = expected_cli_page_filenames(cli_structure)

    # Resolve the project name for the index description (see helper docs).
    project_name = _resolve_project_name(config, base_dir)

    # Load the staleness store once.  gen is a second writer of this store
    # (alongside build/check): it reads the per-page ``seed_hash`` to decide
    # preserve-vs-reseed and records fresh seed hashes for the pages it seeds.
    stored_hashes = load_hashes(base_dir)

    for locale_code, locale_docs_dir in locale_dirs:
        def _seed_hash_of(filename, _lc=locale_code):
            key = _staleness_store_key(config, _lc, filename)
            return stored_hashes.get(key, {}).get("seed_hash")

        # Collect filenames across all language groups for stale cleanup
        locale_all_filenames: list[str] = []
        locale_written: list[str] = []
        locale_index_pages: list[tuple[str, str]] = []

        for language, extractor, group_paths in groups.values():
            result, index_pages = _generate_docs_for_dir(
                config, base_dir, language, extractor,
                locale_docs_dir, group_paths, _seed_hash_of,
            )
            locale_written.extend(result.written)
            locale_all_filenames.extend(result.written)
            locale_index_pages.extend(index_pages)

        # Sort index entries across all language groups for deterministic output
        locale_index_pages.sort(key=lambda t: t[0])

        # Generate combined index page across all language groups
        index_path = os.path.join(locale_docs_dir, "gen-index.md")
        existing_index_desc = _read_existing_index_description(
            index_path, seed_hash=_seed_hash_of("gen-index.md"),
        )
        index_content = _generate_index_content(
            locale_index_pages, project_name,
            existing_description=existing_index_desc,
        )
        os.makedirs(locale_docs_dir, exist_ok=True)
        if os.path.isfile(index_path):
            try:
                os.chmod(index_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
        _atomic_write(index_path, index_content, permissions=0o444)
        locale_written.append("gen-index.md")
        locale_all_filenames.append("gen-index.md")

        # Include strictcli page names so they survive stale cleanup
        locale_all_filenames.extend(cli_page_names)

        # Generate CLI pages (once per locale, not per language group)
        if cli_structure is not None:
            cli_pages = generate_cli_pages(cli_structure, locale_docs_dir)
            locale_written.extend(cli_pages)

        # Stale cleanup: run ONCE after all language groups have generated
        deleted = _remove_stale_generated(locale_docs_dir, locale_all_filenames)

        # Record per-page seed_hash for the pages gen just seeded.  A page
        # written with ``seeded: true`` carries machine text this run; hash it.
        # A page written WITHOUT the marker was preserved as handwritten, so
        # drop any stale seed_hash so it re-enters staleness protection.
        _record_seed_hashes(
            config, locale_code, locale_docs_dir,
            dict.fromkeys(locale_written), stored_hashes,
        )

        if locale_code:
            all_written.extend(
                os.path.join(locale_code, f) for f in locale_written
            )
            all_deleted.extend(
                os.path.join(locale_code, f) for f in deleted
            )
        else:
            all_written.extend(locale_written)
            all_deleted.extend(deleted)

    save_hashes(stored_hashes, base_dir)

    return GenResult(written=all_written, deleted=all_deleted)


def _record_seed_hashes(config, locale_code, locale_docs_dir, filenames,
                        stored_hashes):
    """Record/clear per-page ``seed_hash`` for the pages gen wrote this run.

    ``filenames`` is an iterable of basenames (relative to *locale_docs_dir*).
    Merges into *stored_hashes* in place, preserving all build/check-owned
    fields.
    """
    for filename in filenames:
        page_path = os.path.join(locale_docs_dir, filename)
        try:
            with open(page_path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue
        metadata, _ = _parse_frontmatter(content)
        key = _staleness_store_key(config, locale_code, filename)
        description = metadata.get("description")
        if metadata.get("seeded") is True and isinstance(description, str):
            entry = stored_hashes.get(key, {})
            entry["seed_hash"] = description_seed_hash(description)
            stored_hashes[key] = entry
        else:
            if key in stored_hashes:
                stored_hashes[key].pop("seed_hash", None)


def _generate_docs_for_dir(config, base_dir, language, extractor,
                           docs_dir, source_paths, seed_hash_of=None):
    """Generate docs for a single language group in one directory.

    ``source_paths`` is the list of source path strings for this
    language group (already extracted from config by the caller).

    ``seed_hash_of`` is an optional callable mapping a page filename to its
    recorded ``seed_hash`` (from the staleness store), used to decide whether
    an existing machine-seeded description should be reseeded or preserved.

    Stale cleanup and index generation are NOT done here -- the caller
    (``generate_docs``) handles them after all language groups have
    generated.

    Returns a tuple of ``(GenResult, index_pages)`` where
    ``index_pages`` is a list of ``(module_name, md_filename)`` for
    the combined index page.
    """
    os.makedirs(docs_dir, exist_ok=True)

    extensions = set(extractor.file_extensions())

    # Build exclusion patterns: defaults + user-configured
    gen_config = config.get("gen") or {}
    user_excludes = gen_config.get("exclude", [])
    exclude_patterns = list(_DEFAULT_EXCLUDES) + list(user_excludes)

    # Collect (module_path, module_name, md_filename, src_path_or_pkg_dir) tuples.
    # For Go, src_path_or_pkg_dir is the package directory; for others it is
    # the individual source file path.
    modules = []

    if language == "go":
        # Go: group by package directory, one page per directory
        go_packages = _collect_go_packages(
            source_paths, base_dir, exclude_patterns,
        )
        root_pkg_name = _go_root_package_name(base_dir)

        for module_path, pkg_dir_abs in go_packages:
            if module_path == ".":
                display_name = root_pkg_name
                ref_path = "."
                md_filename = root_pkg_name + ".md"
            else:
                display_name = module_path
                ref_path = module_path
                md_filename = _module_to_filename(module_path, language)

            # Skip if a hand-written page already exists
            existing_md = os.path.join(docs_dir, md_filename)
            if os.path.isfile(existing_md) and not _has_generated_marker(
                existing_md
            ):
                continue

            modules.append(
                (ref_path, display_name, md_filename, pkg_dir_abs)
            )
    else:
        # Python, TypeScript, JavaScript: one page per file
        for sp in source_paths:
            source_root = os.path.join(base_dir, sp.rstrip("/"))
            if not os.path.isdir(source_root):
                continue

            for dirpath, dirnames, filenames in os.walk(source_root):
                dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
                for fname in filenames:
                    _root, ext = os.path.splitext(fname)
                    if ext not in extensions:
                        continue

                    full_path = os.path.join(dirpath, fname)
                    rel_to_source = os.path.relpath(full_path, source_root)

                    if _is_excluded(rel_to_source, exclude_patterns):
                        continue

                    module_path = _file_to_module_path(
                        full_path, base_dir, language,
                    )
                    if module_path is None:
                        continue

                    # Also check exclude patterns against the computed module path
                    # (supports dotted module names like "selfdoc.staleness")
                    if _is_excluded(module_path, exclude_patterns):
                        continue

                    md_filename = _module_to_filename(module_path, language)

                    # Skip if a hand-written page already exists
                    existing_md = os.path.join(docs_dir, md_filename)
                    if os.path.isfile(existing_md) and not _has_generated_marker(
                        existing_md
                    ):
                        continue

                    modules.append((module_path, module_path, md_filename, full_path))

    # Sort for deterministic output
    modules.sort(key=lambda t: t[0])

    # Deduplicate by md_filename (in case multiple source paths yield the same module)
    seen = set()
    unique_modules = []
    for mod_path, mod_name, md_fname, src_path in modules:
        if md_fname not in seen:
            seen.add(md_fname)
            unique_modules.append((mod_path, mod_name, md_fname, src_path))
    modules = unique_modules

    generated = []

    for nav_order, (mod_path, mod_name, md_fname, src_path) in enumerate(modules, start=1):
        out_path = os.path.join(docs_dir, md_fname)
        page_seed_hash = seed_hash_of(md_fname) if seed_hash_of else None
        existing_description = _read_existing_description(
            out_path, module_name=mod_name, seed_hash=page_seed_hash,
        )
        # Try module/package docstring when no custom description exists
        docstring_description = None
        if existing_description is None:
            raw = extractor.module_docstring(src_path)
            docstring_description = first_sentence(raw) or None
        content = _generate_page_content(
            mod_name, mod_path, nav_order,
            existing_description=existing_description,
            docstring_description=docstring_description,
            language=language,
        )
        # Make writable if it already exists with 0o444
        if os.path.isfile(out_path):
            try:
                os.chmod(out_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
        _atomic_write(out_path, content, permissions=0o444)
        generated.append(md_fname)

    # Return index entries for the caller to merge across language groups
    index_pages = [(mod_name, md_fname) for _, mod_name, md_fname, _ in modules]

    return GenResult(written=generated, deleted=[]), index_pages


# -- Header comment for auto-generated root files ---------------------------

_ROOT_FILE_HEADER_PREFIX = "<!-- Auto-generated by selfdoc from "


def _make_root_file_header(template_path):
    """Build the header comment for a generated root file."""
    return (
        f"<!-- Auto-generated by selfdoc from {template_path}"
        " — do not edit -->\n\n"
    )


def generate_root_files(config, base_dir="."):
    """Resolve root-file templates and write them to the project root.

    Reads ``config["root_files"]`` (a list of template paths like
    ``"docs/_CLAUDE.md"``).  Each template is resolved via the project's
    directive resolver, then written with an auto-generated header and
    read-only (0o444) permissions.

    Returns a list of output paths relative to *base_dir*.
    """
    root_files = config.get("root_files", [])
    if not root_files:
        return []

    resolver = make_resolver(config, base_dir)
    custom_names = set(config.get("directives", {}).keys())
    validate_directive_names(custom_names)
    valid_names = ALL_BUILTIN_DIRECTIVES | custom_names

    generated = []

    for template_path in root_files:
        full_template = os.path.join(base_dir, template_path)
        if not os.path.isfile(full_template):
            raise RuntimeError(
                f"Root file template not found: {template_path}"
            )

        basename = os.path.basename(template_path)
        if not basename.startswith("_"):
            raise RuntimeError(
                f"Root file template basename must start with '_': "
                f"{template_path}"
            )
        output_name = basename[1:]  # strip leading underscore
        output_path = os.path.join(base_dir, output_name)

        # Read template
        with open(full_template, "r", encoding="utf-8") as f:
            content = f.read()

        # Strip frontmatter (not used in output)
        _metadata, content = _parse_frontmatter(content)

        # Resolve directives to Markdown
        resolved = resolve_directives(
            content, resolver, valid_names=valid_names,
        )

        # Prepend auto-generated header
        header = _make_root_file_header(template_path)
        final_content = header + resolved

        # Overwrite safety check
        if os.path.isfile(output_path):
            with open(output_path, "r", encoding="utf-8") as f:
                first_line = f.readline()
            if not first_line.startswith(_ROOT_FILE_HEADER_PREFIX):
                raise RuntimeError(
                    f"Refusing to overwrite {output_path}: file exists and "
                    f"is not auto-generated by selfdoc. To migrate, add "
                    f"'{_make_root_file_header(template_path).rstrip()}' as "
                    f"the first line, or rename the existing file."
                )

        _atomic_write(output_path, final_content, permissions=0o444)
        generated.append(output_name)

    return generated

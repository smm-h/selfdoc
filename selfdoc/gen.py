"""Auto-generate documentation pages from project structure."""

import fnmatch
import os
import re
import stat
from dataclasses import dataclass, field

from selfdoc.docs import parse_frontmatter as _parse_frontmatter
from selfdoc.catalog import ALL_BUILTIN_DIRECTIVES
from selfdoc.directives import resolve_directives
from selfdoc.extractors import EXTRACTORS
from selfdoc.extractors.base import read_source
from selfdoc.extractors.go import _extract_package_doc
from selfdoc.resolver import make_resolver
from selfdoc.utils import extract_module_docstring as _extract_module_docstring
from selfdoc.utils import atomic_write as _atomic_write


@dataclass
class GenResult:
    """Result of a generate_docs call, tracking written and deleted files."""

    written: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)


# Matches the default per-module description template so we can detect when a
# page still has its auto-generated description (and recompute it) versus when
# a user has hand-edited the description (and we should preserve it).
_DEFAULT_DESCRIPTION_RE = re.compile(
    r"^API reference for (the )?[\w.]+( module)? — "
    r"auto-generated documentation covering public functions, "
    r"classes, and type signatures\.?$"
)


# Default exclusion patterns (always applied in addition to user-configured ones).
# These are matched against both the full relative path and the basename,
# so ``test_*`` will match ``test_core.py`` at any depth.
_DEFAULT_EXCLUDES = [
    "test_*",
    "*_test.*",
    "__pycache__",
    "tests",
]


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


def _extract_go_package_description(pkg_dir):
    """Extract the package doc comment from a Go package directory.

    Reads .go files (excluding _test.go), preferring doc.go, then the file
    matching the directory name, then any file with a package doc comment.
    Returns the first line of the doc comment (truncated to 155 chars), or None.
    """
    go_files = sorted(
        f for f in os.listdir(pkg_dir)
        if f.endswith(".go") and not f.endswith("_test.go")
    )
    if not go_files:
        return None

    # Prioritise doc.go and the file matching the directory basename
    dir_basename = os.path.basename(pkg_dir)
    priority_names = ["doc.go", f"{dir_basename}.go"]
    ordered = []
    for pn in priority_names:
        if pn in go_files:
            ordered.append(pn)
    for gf in go_files:
        if gf not in ordered:
            ordered.append(gf)

    file_contents = {}
    for gf in ordered:
        content, _err = read_source(os.path.join(pkg_dir, gf))
        file_contents[gf] = content if content is not None else ""

    _pkg_name, doc = _extract_package_doc(file_contents)
    if not doc:
        return None

    # Take first line, truncate to 155 chars
    first_line = doc.split("\n", 1)[0].strip()
    if not first_line:
        return None
    # Take up to the first sentence-ending period
    match = re.search(r"\.\s", first_line)
    if match:
        first_line = first_line[: match.start() + 1]
    elif first_line.endswith("."):
        pass
    if len(first_line) > 155:
        first_line = first_line[:152] + "..."
    return first_line


def _collect_go_packages(source_paths, base_dir, exclude_patterns):
    """Walk source paths and group .go files by parent directory (package).

    Returns a list of (module_path, pkg_dir_abs) tuples sorted by module_path.
    Excludes test files and files matching exclude_patterns.
    The module_path is the relative directory path from the source root
    (e.g. "internal/commit"), or "." for the source root itself.
    """
    packages = {}  # module_path -> pkg_dir absolute path

    for sp in source_paths:
        source_root = os.path.join(base_dir, sp.rstrip("/"))
        if not os.path.isdir(source_root):
            continue

        for dirpath, _dirnames, filenames in os.walk(source_root):
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
                    module_path = "."
                else:
                    module_path = rel_dir.replace(os.sep, "/")

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


def _read_existing_description(filepath):
    """Return the user-customized ``description`` from a page's frontmatter.

    Returns ``None`` if the file does not exist, has no ``description`` key,
    or still has the default auto-generated description (in which case the
    caller should recompute it from the current module name).
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

    if _DEFAULT_DESCRIPTION_RE.match(value):
        return None

    return value


def _generate_page_content(module_name, module_path, nav_order,
                           existing_description=None,
                           docstring_description=None):
    """Build the Markdown content for a generated documentation page.

    If ``existing_description`` is provided, it is used verbatim as the page's
    ``description`` frontmatter value.  Otherwise, if ``docstring_description``
    is provided (extracted from the module's docstring), it is used.  Finally,
    if neither is available, the default auto-generated template is used.
    """
    if existing_description is not None:
        desc = existing_description
    elif docstring_description is not None:
        desc = docstring_description
    else:
        desc = (
            f"API reference for the {module_name} module — "
            f"auto-generated documentation covering public functions, "
            f"classes, and type signatures."
        )
    return (
        f"---\n"
        f"title: {module_name}\n"
        f"description: \"{desc}\"\n"
        f"generated: true\n"
        f'nav_group: "API Reference"\n'
        f"nav_order: {nav_order}\n"
        f"---\n"
        f"<!-- generated by selfdoc gen, do not edit -->\n"
        f"\n"
        f"# {module_name}\n"
        f"\n"
        f':-: ref path="{module_path}"\n'
    )


def _generate_index_content(generated_pages):
    """Build the gen-index.md page listing all generated pages with links.

    ``generated_pages`` is a list of (module_name, md_filename) tuples,
    already sorted by module name.
    """
    lines = [
        "---",
        "title: API Reference",
        'description: "Complete auto-generated API reference index — browse all modules, classes, and functions with their signatures and docstrings."',
        "generated: true",
        'nav_group: "API Reference"',
        "nav_order: 0",
        "order: 90",
        "---",
        "<!-- generated by selfdoc gen, do not edit -->",
        "",
        "# API Reference",
        "",
    ]
    for module_name, md_filename in generated_pages:
        # Link to the sibling page (same docs/ directory)
        html_name = md_filename.replace(".md", ".html")
        lines.append(f"- [{module_name}]({html_name})")
    lines.append("")
    return "\n".join(lines)


def _remove_stale_generated(docs_dir, new_filenames):
    """Delete previously generated files that are no longer in the new set.

    Only removes files whose frontmatter contains ``generated: true``.
    """
    new_set = set(new_filenames)
    for entry in os.listdir(docs_dir):
        if not entry.endswith(".md"):
            continue
        if entry in new_set:
            continue
        full = os.path.join(docs_dir, entry)
        if os.path.isfile(full) and _has_generated_marker(full):
            os.unlink(full)


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

    For multi-locale projects, generates pages under docs/{locale_code}/
    for each configured locale. For single-locale projects without locale
    subdirectories, generates directly under docs/.

    Returns a list of generated file paths relative to the docs directory.
    """
    language = config["language"]
    extractor = EXTRACTORS.get(language)
    if extractor is None:
        raise RuntimeError(f"no extractor for language {language!r}")

    locale_dirs = _get_locale_docs_dirs(config, base_dir)
    all_generated = []

    for locale_code, locale_docs_dir in locale_dirs:
        generated = _generate_docs_for_dir(
            config, base_dir, language, extractor, locale_docs_dir,
        )
        if locale_code:
            # Prefix paths with locale code for the caller
            all_generated.extend(
                os.path.join(locale_code, f) for f in generated
            )
        else:
            all_generated.extend(generated)

    return all_generated


def _generate_docs_for_dir(config, base_dir, language, extractor, docs_dir):
    """Generate docs for a single directory. Returns list of generated filenames."""

    source_paths = config["source"]
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

            for dirpath, _dirnames, filenames in os.walk(source_root):
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

    # Collect all filenames we will write (pages + index) for stale cleanup
    all_filenames = [md_fname for _, _, md_fname, _ in modules]
    all_filenames.append("gen-index.md")

    # Resolve the strictcli structure up front so the CLI page names can
    # join all_filenames before the stale-cleanup pass — otherwise the
    # cleanup deletes every cli-*.md file (they have ``generated: true``)
    # and the per-page description preservation has no existing file to
    # read from when generate_cli_pages re-renders them.
    from selfdoc.strictcli_support import (
        uses_strictcli,
        extract_cli_structure,
        generate_cli_pages,
        expected_cli_page_filenames,
    )
    cli_structure = None
    if uses_strictcli(source_paths, base_dir):
        cli_structure = extract_cli_structure(source_paths, base_dir)
    all_filenames.extend(expected_cli_page_filenames(cli_structure))

    # Remove stale generated files before writing new ones
    _remove_stale_generated(docs_dir, all_filenames)

    generated = []

    for nav_order, (mod_path, mod_name, md_fname, src_path) in enumerate(modules, start=1):
        out_path = os.path.join(docs_dir, md_fname)
        existing_description = _read_existing_description(out_path)
        # Try module/package docstring when no custom description exists
        docstring_description = None
        if existing_description is None:
            if language == "go":
                # src_path is a package directory for Go
                docstring_description = _extract_go_package_description(
                    src_path
                )
            else:
                docstring_description = _extract_module_docstring(src_path)
        content = _generate_page_content(
            mod_name, mod_path, nav_order,
            existing_description=existing_description,
            docstring_description=docstring_description,
        )
        # Make writable if it already exists with 0o444
        if os.path.isfile(out_path):
            try:
                os.chmod(out_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
        _atomic_write(out_path, content, permissions=0o444)
        generated.append(md_fname)

    # Generate index page
    index_pages = [(mod_name, md_fname) for _, mod_name, md_fname, _ in modules]
    index_content = _generate_index_content(index_pages)
    index_path = os.path.join(docs_dir, "gen-index.md")
    if os.path.isfile(index_path):
        try:
            os.chmod(index_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    _atomic_write(index_path, index_content, permissions=0o444)
    generated.append("gen-index.md")

    # strictcli support: auto-generate CLI documentation pages
    # (cli_structure was resolved earlier so its page names could be
    # excluded from the stale-cleanup pass)
    if cli_structure is not None:
        cli_pages = generate_cli_pages(cli_structure, docs_dir)
        generated.extend(cli_pages)

    return generated


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
    valid_names = ALL_BUILTIN_DIRECTIVES | set(
        config.get("directives", {}).keys()
    )

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

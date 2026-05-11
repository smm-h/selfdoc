"""Check command -- validate directives and report documentation coverage.

Scans docs/ templates for directives, attempts to resolve each one,
and reports per-directive status (OK or FAILED). For Python projects,
also computes coverage: how many public symbols are referenced by
:::module directives vs. the total public symbols in source files.
"""

import ast
import os
from dataclasses import dataclass, field

import re

from selfdoc.build import _parse_frontmatter
from selfdoc.config import load_config
from selfdoc.directives import parse_directives
from selfdoc.resolver import make_resolver


@dataclass
class DirectiveResult:
    """Result of validating a single directive."""

    file: str  # relative path within docs/
    line: int
    directive: str  # e.g. ":::module selfdoc.config"
    status: str  # "OK" or "FAILED"
    error: str = ""  # non-empty when status is FAILED


@dataclass
class CoverageStats:
    """Coverage of public symbols by :::module directives."""

    total_public: int = 0
    referenced: int = 0
    # Symbols that are documented (referenced by a :::module directive)
    documented_symbols: list[str] = field(default_factory=list)
    # Symbols that are NOT documented
    undocumented_symbols: list[str] = field(default_factory=list)


@dataclass
class LintResult:
    """A single lint diagnostic (e.g. SEO warning)."""

    file: str  # relative path within docs/
    line: int | None
    code: str  # e.g. "SEO001"
    message: str
    severity: str  # "warning" or "error"


@dataclass
class CheckResult:
    """Aggregate result of check_docs()."""

    directive_results: list[DirectiveResult] = field(default_factory=list)
    coverage: CoverageStats | None = None
    lints: list[LintResult] = field(default_factory=list)


def check_docs(dir_path=".", config=None):
    """Validate all directives in docs templates and report coverage.

    Scans docs/ for .md templates, parses directives, attempts to resolve
    each one, and computes coverage for Python projects.

    Args:
        dir_path: Project root directory.
        config: Pre-loaded config dict (if None, loads from selfdoc.json).

    Returns:
        CheckResult with per-directive results and optional coverage stats.
    """
    if config is None:
        config = load_config(dir_path)

    if config is None:
        raise RuntimeError(
            "No selfdoc.json found. Run 'selfdoc init' to initialize."
        )

    docs_dir = os.path.join(dir_path, config["docs"].rstrip("/"))
    if not os.path.isdir(docs_dir):
        raise RuntimeError(
            f"Docs directory '{config['docs']}' not found."
        )

    resolver = make_resolver(config, dir_path)
    result = CheckResult()

    # Track which module args are referenced (for coverage)
    referenced_modules = []

    # Normalize output dir so we can skip it during the walk
    output_dir = os.path.join(dir_path, config["output"].rstrip("/"))
    abs_output = os.path.abspath(output_dir)

    # Scan docs/ for .md templates
    for root, _dirs, files in os.walk(docs_dir):
        # Skip the output directory to avoid processing previous build artifacts
        if os.path.abspath(root) == abs_output or os.path.abspath(root).startswith(abs_output + os.sep):
            continue
        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, docs_dir)

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            directives = parse_directives(content)
            for directive in directives:
                directive_str = f":::{directive.name} {directive.arg}".strip()
                try:
                    resolved = resolver(
                        directive.name, directive.arg, directive.body
                    )
                    # Resolver returns error markers starting with "> *[selfdoc:"
                    # when something goes wrong -- detect those as failures
                    if resolved.startswith("> *[selfdoc:"):
                        # Extract error message from the marker
                        error_msg = resolved.strip("> *[]")
                        # Clean up: remove "selfdoc: " prefix
                        if error_msg.startswith("selfdoc: "):
                            error_msg = error_msg[len("selfdoc: "):]
                        result.directive_results.append(DirectiveResult(
                            file=rel_path,
                            line=directive.line_number,
                            directive=directive_str,
                            status="FAILED",
                            error=error_msg,
                        ))
                    else:
                        result.directive_results.append(DirectiveResult(
                            file=rel_path,
                            line=directive.line_number,
                            directive=directive_str,
                            status="OK",
                        ))
                        # Track successful module references for coverage
                        if directive.name == "module" and directive.arg:
                            referenced_modules.append(directive.arg)
                except Exception as exc:
                    result.directive_results.append(DirectiveResult(
                        file=rel_path,
                        line=directive.line_number,
                        directive=directive_str,
                        status="FAILED",
                        error=str(exc),
                    ))

    # Compute coverage for Python projects
    if config["language"] == "python":
        result.coverage = _compute_python_coverage(
            config, dir_path, referenced_modules
        )

    # Run lint checks (SEO and other diagnostics)
    result.lints = _run_lints(docs_dir, resolver, config)

    return result


def _run_lints(docs_dir, resolver, config):
    """Run lint checks on documentation templates.

    Returns a list of LintResult diagnostics covering SEO best practices:
    multiple H1s, heading level gaps, empty alt text, title length,
    missing base_url, and missing description.
    """
    results = []

    # Collect .md files (same walk pattern as check_docs)
    md_files = []
    for root, _dirs, files in os.walk(docs_dir):
        for fname in sorted(files):
            if fname.endswith(".md"):
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, docs_dir)
                md_files.append((rel_path, full_path))

    project_name = os.path.basename(os.path.dirname(os.path.abspath(docs_dir)))

    for rel_path, full_path in md_files:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")
        metadata, _ = _parse_frontmatter(content)

        # SEO001 -- Multiple H1s
        h1_count = 0
        for line in lines:
            if re.match(r"^# (?!#)", line):
                h1_count += 1
        if h1_count > 1:
            results.append(LintResult(
                file=rel_path,
                line=None,
                code="SEO001",
                message=f"Multiple H1 headings ({h1_count} found); use a single H1 per page",
                severity="warning",
            ))

        # SEO002 -- Heading level gaps
        prev_level = 0
        for line_num, line in enumerate(lines, start=1):
            m = re.match(r"^(#{1,6})\s", line)
            if m:
                level = len(m.group(1))
                if prev_level > 0 and level > prev_level + 1:
                    results.append(LintResult(
                        file=rel_path,
                        line=line_num,
                        code="SEO002",
                        message=(
                            f"Heading level jumps from H{prev_level} to H{level}"
                            f" (skips H{prev_level + 1})"
                        ),
                        severity="warning",
                    ))
                prev_level = level

        # SEO003 -- Empty alt text
        for line_num, line in enumerate(lines, start=1):
            if "![](" in line:
                results.append(LintResult(
                    file=rel_path,
                    line=line_num,
                    code="SEO003",
                    message="Image with empty alt text",
                    severity="warning",
                ))

        # SEO004 -- Title too long
        title = metadata.get("title")
        if title is not None:
            combined = f"{title} - {project_name}"
            if len(combined) > 60:
                results.append(LintResult(
                    file=rel_path,
                    line=None,
                    code="SEO004",
                    message=(
                        f"Title too long for SEO ({len(combined)} chars):"
                        f" \"{combined}\""
                    ),
                    severity="warning",
                ))

        # SEO006 -- Missing description
        if "description" not in metadata:
            results.append(LintResult(
                file=rel_path,
                line=None,
                code="SEO006",
                message="No 'description' in frontmatter",
                severity="warning",
            ))

    # SEO005 -- Missing base_url (project-level, not per-file)
    if config.get("base_url") is None:
        results.append(LintResult(
            file="selfdoc.json",
            line=None,
            code="SEO005",
            message=(
                "base_url not set in config; canonical URLs,"
                " sitemap, and OG tags will be missing"
            ),
            severity="warning",
        ))

    return results


def _compute_python_coverage(config, base_dir, referenced_modules):
    """Count public symbols in source files vs. those referenced by directives.

    A "public symbol" is a top-level function or class whose name does not
    start with underscore. Each :::module directive that resolves to a file
    counts all public symbols in that file as "documented".
    """
    base_dir = os.path.abspath(base_dir)
    source_paths = config["source"]
    stats = CoverageStats()

    # Collect all .py files and their public symbols
    # Map: relative module path -> list of public symbol names
    all_symbols: dict[str, list[str]] = {}

    for sp in source_paths:
        src_dir = os.path.join(base_dir, sp)
        if not os.path.isdir(src_dir):
            continue
        for root, _dirs, files in os.walk(src_dir):
            for fname in sorted(files):
                if not fname.endswith(".py"):
                    continue
                full_path = os.path.join(root, fname)
                rel_to_base = os.path.relpath(full_path, base_dir)
                symbols = _extract_public_symbols(full_path)
                if symbols:
                    all_symbols[rel_to_base] = symbols

    # Determine which files are "documented" via :::module directives
    documented_files = set()
    for mod_arg in referenced_modules:
        resolved = _resolve_module_to_relpath(
            mod_arg, source_paths, base_dir
        )
        if resolved:
            documented_files.add(resolved)

    # Tally
    for rel_path, symbols in sorted(all_symbols.items()):
        for sym in symbols:
            qualified = f"{rel_path}:{sym}"
            stats.total_public += 1
            if rel_path in documented_files:
                stats.referenced += 1
                stats.documented_symbols.append(qualified)
            else:
                stats.undocumented_symbols.append(qualified)

    return stats


def _extract_public_symbols(filepath):
    """Parse a Python file and return names of public top-level functions/classes."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except (OSError, UnicodeDecodeError):
        return []

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return []

    symbols = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                symbols.append(node.name)
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                symbols.append(node.name)
    return symbols


def _resolve_module_to_relpath(arg, source_paths, base_dir):
    """Resolve a module argument to a path relative to base_dir.

    Mirrors the resolution logic in extractors/python.py but returns
    the relative path instead of the absolute path.
    """
    dotted_as_path = arg.replace(".", "/") + ".py"
    dotted_as_pkg = arg.replace(".", "/") + "/__init__.py"

    candidates = []
    for sp in source_paths:
        candidates.append(os.path.join(sp, dotted_as_path))
        candidates.append(os.path.join(sp, dotted_as_pkg))
    candidates.append(dotted_as_path)
    candidates.append(dotted_as_pkg)

    if arg.endswith(".py"):
        candidates.append(arg)
        for sp in source_paths:
            candidates.append(os.path.join(sp, arg))

    for candidate in candidates:
        full = os.path.join(base_dir, candidate)
        if os.path.isfile(full):
            return os.path.relpath(full, base_dir)

    return None


def print_results(result):
    """Print check results to stdout in a human-readable format."""
    if not result.directive_results:
        print("No directives found in documentation templates.")
        return

    # Per-directive results
    for dr in result.directive_results:
        status_str = dr.status
        if dr.error:
            status_str = f"FAILED: {dr.error}"
        print(f"  {dr.file}:{dr.line}  {dr.directive}  {status_str}")

    # Summary counts
    ok_count = sum(1 for dr in result.directive_results if dr.status == "OK")
    fail_count = sum(
        1 for dr in result.directive_results if dr.status == "FAILED"
    )
    total = len(result.directive_results)
    print(f"\n{total} directive(s): {ok_count} OK, {fail_count} FAILED")

    # Coverage stats
    if result.coverage is not None:
        cov = result.coverage
        if cov.total_public > 0:
            pct = cov.referenced * 100 // cov.total_public
            print(
                f"Coverage: {cov.referenced}/{cov.total_public} "
                f"public symbols documented ({pct}%)"
            )
        else:
            print("Coverage: no public symbols found in source files")

    # Lint results
    if result.lints:
        print()
        for lint in result.lints:
            line_part = f":{lint.line}" if lint.line is not None else ""
            print(
                f"  {lint.severity}: [{lint.code}] "
                f"{lint.file}{line_part} - {lint.message}"
            )
    else:
        print("No lints.")

"""Check command -- validate directives and report documentation coverage.

Scans docs/ templates for directives, attempts to resolve each one,
and reports per-directive status (OK or FAILED). For Python, Go, and
TypeScript/JavaScript projects, computes coverage: how many public/exported
symbols are referenced by :::module directives vs. the total in source files.
"""

import ast
import os
import sys
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
class ResolvedDirective:
    """A successfully resolved directive with its output content."""

    name: str  # directive name (module, schema, test, cli, config)
    arg: str  # directive argument
    content: str  # resolved output text


@dataclass
class CoverageStats:
    """Coverage of public symbols by directives."""

    total_public: int = 0
    referenced: int = 0
    # Symbols that are documented (referenced by a directive)
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
    severity: str  # "warning", "error", or "info"


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

    # Track all successfully resolved directives (for coverage)
    resolved_directives = []

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
                        # Track all successful directives for coverage
                        if directive.arg:
                            resolved_directives.append(
                                ResolvedDirective(
                                    name=directive.name,
                                    arg=directive.arg,
                                    content=resolved,
                                )
                            )
                except Exception as exc:
                    result.directive_results.append(DirectiveResult(
                        file=rel_path,
                        line=directive.line_number,
                        directive=directive_str,
                        status="FAILED",
                        error=str(exc),
                    ))

    # Compute coverage
    language = config["language"]
    if language == "python":
        result.coverage = _compute_python_coverage(
            config, dir_path, resolved_directives
        )
    elif language == "go":
        result.coverage = _compute_go_coverage(
            config, dir_path, resolved_directives
        )
    elif language in ("typescript", "javascript"):
        result.coverage = _compute_ts_coverage(
            config, dir_path, resolved_directives
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
        # SEO013 -- Missing H1
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
        elif h1_count == 0:
            results.append(LintResult(
                file=rel_path,
                line=None,
                code="SEO013",
                message="No H1 heading found; each page should have exactly one H1",
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
        else:
            # Auto-extract title from first H1 heading
            h1_match = re.search(r"^# (.+)$", content, re.MULTILINE)
            if h1_match:
                h1_title = h1_match.group(1)
                combined = f"{h1_title} - {project_name}"
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
                severity="error",
            ))

        # SEO009 -- Description too short
        # SEO010 -- Frontmatter description too long
        fm_description = metadata.get("description")
        if fm_description is not None:
            # Frontmatter has an explicit description
            if isinstance(fm_description, str) and len(fm_description) > 155:
                results.append(LintResult(
                    file=rel_path,
                    line=None,
                    code="SEO010",
                    message=(
                        f"Frontmatter description is {len(fm_description)}"
                        f" chars (max 155)"
                    ),
                    severity="warning",
                ))
            effective_desc = str(fm_description)
        else:
            # Auto-extract from first paragraph (first non-heading,
            # non-blank line), take first sentence
            effective_desc = ""
            _, body_content = _parse_frontmatter(content)
            for body_line in body_content.split("\n"):
                stripped = body_line.strip()
                if not stripped:
                    continue
                if stripped.startswith("#"):
                    continue
                # Found first paragraph line; take first sentence
                match = re.search(r"[.!?]", stripped)
                if match:
                    effective_desc = stripped[:match.end()]
                else:
                    effective_desc = stripped[:155]
                break

        # Only fire SEO009 when there IS a description to check.
        # When fm_description is None and no paragraph was found,
        # effective_desc is "" (falsy) -- SEO006 already covers that.
        if effective_desc and len(effective_desc) < 120:
            results.append(LintResult(
                file=rel_path,
                line=None,
                code="SEO009",
                message=(
                    f"Effective description is only"
                    f" {len(effective_desc)} chars"
                    f" (aim for 120-155)"
                ),
                severity="warning",
            ))

        # SEO007 -- Paragraph length after headings
        for line_num, line in enumerate(lines, start=1):
            m = re.match(r"^(#{2,3})\s+(.+)", line)
            if not m:
                continue
            heading_text = m.group(2).strip()
            # Look at the next non-empty line after the heading
            next_idx = line_num  # 0-based index of line after heading
            if next_idx >= len(lines):
                continue
            # Skip blank lines between heading and content
            content_start = next_idx
            while content_start < len(lines) and lines[content_start].strip() == "":
                content_start += 1
            if content_start >= len(lines):
                continue
            first_content_line = lines[content_start].strip()
            # Skip if followed by a list, code block, or another heading
            if (first_content_line.startswith(("-", "*", "+", "1."))
                    or first_content_line.startswith("```")
                    or first_content_line.startswith("#")):
                continue
            # Collect the paragraph (lines until blank line or heading)
            para_lines = []
            for pi in range(content_start, len(lines)):
                pl = lines[pi].strip()
                if pl == "" or pl.startswith("#"):
                    break
                para_lines.append(pl)
            paragraph = " ".join(para_lines)
            word_count = len(paragraph.split())
            if word_count < 30 or word_count > 80:
                results.append(LintResult(
                    file=rel_path,
                    line=line_num,
                    code="SEO007",
                    message=(
                        f"First paragraph after '{heading_text}' is"
                        f" {word_count} words (aim for 40-60 for AI citation)"
                    ),
                    severity="warning",
                ))

        # SEO008 -- Statistics density
        # Strip frontmatter for counting
        body = content
        if content.startswith("---"):
            fm_lines = content.split("\n")
            end_idx = None
            for idx in range(1, len(fm_lines)):
                if fm_lines[idx].strip() == "---":
                    end_idx = idx
                    break
            if end_idx is not None:
                body = "\n".join(fm_lines[end_idx + 1:])

        words = body.split()
        total_words = len(words)
        numeric_tokens = sum(
            1 for w in words if any(c.isdigit() for c in w)
        )
        if total_words > 200 and numeric_tokens == 0:
            results.append(LintResult(
                file=rel_path,
                line=None,
                code="SEO008",
                message=(
                    f"Page has {total_words} words but no numeric data"
                    f" points (statistics improve AI citation)"
                ),
                severity="warning",
            ))

        # SEO011 -- Empty heading section (heading followed by same-or-higher
        # level heading with no content between)
        last_heading_line = None  # (line_number, level)
        for line_num, line in enumerate(lines, start=1):
            heading_match = re.match(r"^(#{2,3})\s", line)
            if heading_match:
                level = len(heading_match.group(1))
                if last_heading_line is not None:
                    prev_line_num, prev_level = last_heading_line
                    # Warn if next heading is same or higher level
                    # (fewer or equal #'s), meaning the previous section
                    # was empty
                    if level <= prev_level:
                        results.append(LintResult(
                            file=rel_path,
                            line=prev_line_num,
                            code="SEO011",
                            message=(
                                f"H{prev_level} heading has no content"
                                f" before next H{level} heading"
                            ),
                            severity="warning",
                        ))
                last_heading_line = (line_num, level)
            elif line.strip():
                # Non-blank, non-heading line resets tracking
                last_heading_line = None

    # SEO014 -- Meaningless alt text
    # SEO015 -- Generic anchor text
    _MEANINGLESS_ALT = {
        "image", "screenshot", "photo", "picture",
        "img", "pic", "figure", "graphic",
    }
    _FILENAME_EXTS = re.compile(
        r"\.(png|jpg|jpeg|gif|svg|webp)$", re.IGNORECASE,
    )
    _GENERIC_ANCHORS = {
        "click here", "here", "this link", "this page",
        "link", "read more", "more", "learn more",
    }

    for rel_path, full_path in md_files:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")

        # SEO014 -- Meaningless alt text
        for line_num, line in enumerate(lines, start=1):
            for m in re.finditer(r"!\[([^\]]*)\]\(", line):
                alt = m.group(1)
                if not alt:
                    continue  # empty alt is SEO003
                is_meaningless = (
                    alt.lower() in _MEANINGLESS_ALT
                    or len(alt) == 1
                    or _FILENAME_EXTS.search(alt.lower())
                )
                if is_meaningless:
                    results.append(LintResult(
                        file=rel_path,
                        line=line_num,
                        code="SEO014",
                        message=(
                            f"Meaningless alt text '{alt}';"
                            f" use a descriptive alternative"
                        ),
                        severity="warning",
                    ))

        # SEO015 -- Generic anchor text (skip code blocks)
        in_code_block = False
        for line_num, line in enumerate(lines, start=1):
            if line.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue
            for m in re.finditer(r"\[([^\]]+)\]\(", line):
                text = m.group(1).strip().lower()
                if text in _GENERIC_ANCHORS:
                    results.append(LintResult(
                        file=rel_path,
                        line=line_num,
                        code="SEO015",
                        message=(
                            f"Generic anchor text '{m.group(1).strip()}';"
                            f" use descriptive link text"
                        ),
                        severity="warning",
                    ))

    # SEO012 -- WCAG contrast ratio checks
    _check_contrast(results, config, docs_dir)

    return results


def _parse_hex_color(hex_color):
    """Parse a #RRGGBB hex color to (R, G, B) tuple of 0-255 ints."""
    hex_color = hex_color.strip().lstrip("#")
    if len(hex_color) != 6:
        return None
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return (r, g, b)
    except ValueError:
        return None


def _relative_luminance(rgb):
    """Compute WCAG 2.1 relative luminance from an (R, G, B) tuple."""
    channels = []
    for c in rgb:
        srgb = c / 255.0
        if srgb <= 0.04045:
            linear = srgb / 12.92
        else:
            linear = ((srgb + 0.055) / 1.055) ** 2.4
        channels.append(linear)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast_ratio(rgb1, rgb2):
    """Compute WCAG 2.1 contrast ratio between two RGB colors."""
    l1 = _relative_luminance(rgb1)
    l2 = _relative_luminance(rgb2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _extract_css_vars(css_block):
    """Extract CSS custom properties from a block of CSS text.

    Returns a dict mapping property names (e.g. '--bg') to values.
    """
    props = {}
    for match in re.finditer(r"(--[\w-]+)\s*:\s*([^;]+);", css_block):
        props[match.group(1)] = match.group(2).strip()
    return props


def _check_contrast(lints, config, base_dir):
    """Check WCAG 2.1 contrast ratios for theme colors (SEO012).

    Parses the theme CSS for custom properties and verifies critical
    foreground/background pairs meet minimum contrast ratios.
    """
    theme_name = config.get("theme", "minimal")

    # Locate theme CSS using the same path as selfdoc.themes
    themes_dir = os.path.join(os.path.dirname(__file__), "themes")
    css_path = os.path.join(themes_dir, f"{theme_name}.css")
    if not os.path.isfile(css_path):
        return

    with open(css_path, "r", encoding="utf-8") as f:
        css_content = f.read()

    # Critical pairs: (foreground var, background var, label, threshold)
    pairs = [
        ("--text", "--bg", "body text", 4.5),
        ("--text-secondary", "--bg", "secondary text", 4.5),
        ("--heading", "--bg", "headings", 3.0),
        ("--link", "--bg", "links", 4.5),
        ("--sidebar-text", "--sidebar-bg", "sidebar text", 4.5),
    ]

    # Extract :root block variables (light mode)
    root_match = re.search(r":root\s*\{([^}]+)\}", css_content)
    if root_match:
        light_vars = _extract_css_vars(root_match.group(1))
        _check_pairs(lints, light_vars, pairs, "")

    # Extract [data-theme="dark"] block variables
    dark_match = re.search(
        r'\[data-theme="dark"\]\s*\{([^}]+)\}', css_content
    )
    if dark_match:
        dark_vars = _extract_css_vars(dark_match.group(1))
        _check_pairs(lints, dark_vars, pairs, "dark mode ")


def _check_pairs(lints, css_vars, pairs, mode_prefix):
    """Check contrast ratio for each pair and emit SEO012 if below threshold."""
    css_file = "theme CSS"

    for fg_var, bg_var, name, threshold in pairs:
        fg_hex = css_vars.get(fg_var)
        bg_hex = css_vars.get(bg_var)
        if not fg_hex or not bg_hex:
            continue

        fg_rgb = _parse_hex_color(fg_hex)
        bg_rgb = _parse_hex_color(bg_hex)
        if fg_rgb is None or bg_rgb is None:
            continue

        ratio = _contrast_ratio(fg_rgb, bg_rgb)
        if ratio < threshold:
            lints.append(LintResult(
                file=css_file,
                line=None,
                code="SEO012",
                message=(
                    f"Low contrast ratio {ratio:.1f}:1 for "
                    f"{mode_prefix}{name} on {bg_var} "
                    f"(WCAG AA requires {threshold}:1)"
                ),
                severity="warning",
            ))


def _compute_python_coverage(config, base_dir, resolved_directives):
    """Count public symbols in source files vs. those documented by directives.

    A "public symbol" is a top-level function or class whose name does not
    start with underscore. Coverage is tracked per-symbol:

    - For :::module directives, each public symbol in the referenced file is
      checked: the symbol is "documented" only if its name appears in the
      directive's resolved content.
    - For :::schema, :::test, :::cli, :::config directives, the arg typically
      names a specific symbol -- that symbol is marked as documented directly.
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

    # Build set of documented symbols (as "rel/path.py:symbol_name")
    documented_set: set[str] = set()

    for rd in resolved_directives:
        if rd.name == "module":
            # Resolve the module arg to a file path
            rel_path = _resolve_module_to_relpath(
                rd.arg, source_paths, base_dir
            )
            if rel_path and rel_path in all_symbols:
                # Check each public symbol against the resolved content
                for sym in all_symbols[rel_path]:
                    if sym in rd.content:
                        documented_set.add(f"{rel_path}:{sym}")
        elif rd.name in ("schema", "test", "cli", "config"):
            # Extract symbol name from the arg. For schema, the arg is
            # "module_path ClassName" -- extract the class/function name.
            # For test, the arg is "file_path [target_name]".
            # For cli/config, the arg is a module path or file path.
            parts = rd.arg.split()
            if rd.name == "schema" and len(parts) >= 2:
                # "dotted.module ClassName" -- the symbol is the class name
                symbol_name = parts[-1]
                module_arg = parts[0]
            elif rd.name == "test" and len(parts) >= 2:
                # "file_path target_name" -- the symbol is the target
                symbol_name = parts[-1]
                module_arg = parts[0]
            else:
                # cli/config or single-arg schema/test -- use the module arg
                # to find the file's symbols and mark them via content check
                module_arg = parts[0]
                symbol_name = None

            if symbol_name:
                # Try to find the file for this module arg and mark
                # the specific symbol
                rel_path = _resolve_module_to_relpath(
                    module_arg, source_paths, base_dir
                )
                if rel_path is None and module_arg.endswith(".py"):
                    # Direct file path
                    candidate = os.path.join(base_dir, module_arg)
                    if os.path.isfile(candidate):
                        rel_path = os.path.relpath(candidate, base_dir)
                if rel_path and rel_path in all_symbols:
                    if symbol_name in all_symbols[rel_path]:
                        documented_set.add(f"{rel_path}:{symbol_name}")

    # Tally
    for rel_path, symbols in sorted(all_symbols.items()):
        for sym in symbols:
            qualified = f"{rel_path}:{sym}"
            stats.total_public += 1
            if qualified in documented_set:
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


# ---------------------------------------------------------------------------
# Go coverage
# ---------------------------------------------------------------------------

# Patterns for exported Go symbols (applied to non-comment lines)
_GO_FUNC_RE = re.compile(r"^func\s+([A-Z]\w*)\s*\(")
_GO_METHOD_RE = re.compile(r"^func\s+\([^)]+\)\s+([A-Z]\w*)\s*\(")
_GO_TYPE_RE = re.compile(r"^type\s+([A-Z]\w*)\s+")
_GO_VAR_RE = re.compile(r"^var\s+([A-Z]\w*)")
_GO_CONST_RE = re.compile(r"^const\s+([A-Z]\w*)")


def _extract_go_public_symbols(filepath):
    """Parse a Go file and return names of exported (uppercase) symbols.

    Skips lines inside // and /* */ comments.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except (OSError, UnicodeDecodeError):
        return []

    lines = source.split("\n")
    symbols = []
    in_block_comment = False

    for line in lines:
        stripped = line.strip()

        # Handle block comments
        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
                # Content after */ on the same line -- process it below
                idx = stripped.index("*/")
                stripped = stripped[idx + 2:].strip()
                if not stripped:
                    continue
            else:
                continue

        # Check for block comment start
        if "/*" in stripped:
            # Handle single-line block comments: /* ... */
            if "*/" in stripped[stripped.index("/*") + 2:]:
                # Remove the block comment and process remainder
                stripped = re.sub(r"/\*.*?\*/", "", stripped).strip()
                if not stripped:
                    continue
            else:
                in_block_comment = True
                # Process content before /* on this line
                stripped = stripped[:stripped.index("/*")].strip()
                if not stripped:
                    continue

        # Skip line comments
        if stripped.startswith("//"):
            continue

        # Remove trailing line comments
        comment_idx = stripped.find("//")
        if comment_idx >= 0:
            stripped = stripped[:comment_idx].strip()

        for pattern in (
            _GO_METHOD_RE,  # Check method before func (method is more specific)
            _GO_FUNC_RE,
            _GO_TYPE_RE,
            _GO_VAR_RE,
            _GO_CONST_RE,
        ):
            m = pattern.match(stripped)
            if m:
                name = m.group(1)
                if name not in symbols:
                    symbols.append(name)
                break

    return symbols


def _compute_go_coverage(config, base_dir, resolved_directives):
    """Count exported symbols in Go source files vs. those documented by directives.

    An exported symbol is any top-level func, type, var, or const whose name
    starts with an uppercase letter. A symbol is "documented" if its file's
    package directory was referenced by a :::module directive and the symbol's
    name appears in the resolved content.
    """
    base_dir = os.path.abspath(base_dir)
    source_paths = config["source"]
    stats = CoverageStats()

    # Collect all .go files (excluding _test.go) and their exported symbols
    # Map: relative file path -> list of exported symbol names
    all_symbols: dict[str, list[str]] = {}

    for sp in source_paths:
        src_dir = os.path.join(base_dir, sp)
        if not os.path.isdir(src_dir):
            continue
        for root, _dirs, files in os.walk(src_dir):
            for fname in sorted(files):
                if not fname.endswith(".go") or fname.endswith("_test.go"):
                    continue
                full_path = os.path.join(root, fname)
                rel_to_base = os.path.relpath(full_path, base_dir)
                symbols = _extract_go_public_symbols(full_path)
                if symbols:
                    all_symbols[rel_to_base] = symbols

    # Build set of documented symbols
    # For Go, :::module arg is a package directory path (e.g. "internal/commit").
    # We match if the file's directory (relative to base_dir) matches the arg
    # resolved through source paths.
    documented_set: set[str] = set()

    for rd in resolved_directives:
        if rd.name == "module":
            # The arg is a package directory path. Find which of our collected
            # files live in that package directory.
            pkg_dir = _resolve_go_package_dir(rd.arg, source_paths, base_dir)
            if pkg_dir is None:
                continue
            pkg_dir_abs = os.path.abspath(pkg_dir)
            for rel_path, syms in all_symbols.items():
                file_dir = os.path.dirname(
                    os.path.join(base_dir, rel_path)
                )
                if os.path.abspath(file_dir) == pkg_dir_abs:
                    for sym in syms:
                        if sym in rd.content:
                            documented_set.add(f"{rel_path}:{sym}")

    # Tally
    for rel_path, symbols in sorted(all_symbols.items()):
        for sym in symbols:
            qualified = f"{rel_path}:{sym}"
            stats.total_public += 1
            if qualified in documented_set:
                stats.referenced += 1
                stats.documented_symbols.append(qualified)
            else:
                stats.undocumented_symbols.append(qualified)

    return stats


def _resolve_go_package_dir(arg, source_paths, base_dir):
    """Resolve a Go package path argument to an actual directory.

    Mirrors the resolution logic in extractors/go.py.
    """
    candidates = []
    for sp in source_paths:
        candidates.append(os.path.join(base_dir, sp, arg))
    candidates.append(os.path.join(base_dir, arg))

    for candidate in candidates:
        if os.path.isdir(candidate):
            if any(f.endswith(".go") for f in os.listdir(candidate)):
                return candidate

    return None


# ---------------------------------------------------------------------------
# TypeScript/JavaScript coverage
# ---------------------------------------------------------------------------

# File extensions for TS/JS source files
_TS_JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")

# Patterns for exported TS/JS symbols (applied to non-comment lines)
_TS_NAMED_FUNC_RE = re.compile(
    r"^export\s+(?:async\s+)?function\s+(\w+)"
)
_TS_CLASS_RE = re.compile(r"^export\s+class\s+(\w+)")
_TS_VAR_RE = re.compile(r"^export\s+(?:const|let|var)\s+(\w+)")
_TS_TYPE_RE = re.compile(r"^export\s+(?:interface|type|enum)\s+(\w+)")
_TS_DEFAULT_RE = re.compile(
    r"^export\s+default\s+(?:function|class)\s+(\w+)"
)
_TS_REEXPORT_RE = re.compile(r"^export\s*\{([^}]+)\}")


def _extract_ts_public_symbols(filepath):
    """Parse a TS/JS file and return names of exported symbols.

    Skips lines inside // and /* */ comments.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except (OSError, UnicodeDecodeError):
        return []

    lines = source.split("\n")
    symbols = []
    in_block_comment = False

    for line in lines:
        stripped = line.strip()

        # Handle block comments
        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
                idx = stripped.index("*/")
                stripped = stripped[idx + 2:].strip()
                if not stripped:
                    continue
            else:
                continue

        # Check for block comment start
        if "/*" in stripped:
            if "*/" in stripped[stripped.index("/*") + 2:]:
                stripped = re.sub(r"/\*.*?\*/", "", stripped).strip()
                if not stripped:
                    continue
            else:
                in_block_comment = True
                stripped = stripped[:stripped.index("/*")].strip()
                if not stripped:
                    continue

        # Skip line comments
        if stripped.startswith("//"):
            continue

        # Remove trailing line comments
        comment_idx = stripped.find("//")
        if comment_idx >= 0:
            stripped = stripped[:comment_idx].strip()

        # Check re-export pattern first: export { A, B, C }
        m = _TS_REEXPORT_RE.match(stripped)
        if m:
            names_str = m.group(1)
            for name_part in names_str.split(","):
                name_part = name_part.strip()
                # Handle "Name as Alias" -- use the exported name (Alias)
                if " as " in name_part:
                    name_part = name_part.split(" as ")[-1].strip()
                if name_part and name_part not in symbols:
                    symbols.append(name_part)
            continue

        # Check default export before other patterns (more specific)
        m = _TS_DEFAULT_RE.match(stripped)
        if m:
            name = m.group(1)
            if name not in symbols:
                symbols.append(name)
            continue

        for pattern in (
            _TS_NAMED_FUNC_RE,
            _TS_CLASS_RE,
            _TS_VAR_RE,
            _TS_TYPE_RE,
        ):
            m = pattern.match(stripped)
            if m:
                name = m.group(1)
                if name not in symbols:
                    symbols.append(name)
                break

    return symbols


def _compute_ts_coverage(config, base_dir, resolved_directives):
    """Count exported symbols in TS/JS source files vs. those documented.

    An exported symbol is anything declared with `export` (function, class,
    const, let, var, interface, type, enum, default, re-export).
    """
    base_dir = os.path.abspath(base_dir)
    source_paths = config["source"]
    stats = CoverageStats()

    # Collect all TS/JS files and their exported symbols
    all_symbols: dict[str, list[str]] = {}

    for sp in source_paths:
        src_dir = os.path.join(base_dir, sp)
        if not os.path.isdir(src_dir):
            continue
        for root, _dirs, files in os.walk(src_dir):
            for fname in sorted(files):
                if not any(fname.endswith(ext) for ext in _TS_JS_EXTENSIONS):
                    continue
                # Skip test files
                if any(
                    fname.endswith(f".test{ext}") or fname.endswith(f".spec{ext}")
                    for ext in _TS_JS_EXTENSIONS
                ):
                    continue
                full_path = os.path.join(root, fname)
                rel_to_base = os.path.relpath(full_path, base_dir)
                symbols = _extract_ts_public_symbols(full_path)
                if symbols:
                    all_symbols[rel_to_base] = symbols

    # Build set of documented symbols
    documented_set: set[str] = set()

    for rd in resolved_directives:
        if rd.name == "module":
            # The arg is a file path (e.g. "src/utils" or "src/utils.ts").
            # Resolve it to a relative path and check symbols.
            rel_path = _resolve_ts_module_to_relpath(
                rd.arg, source_paths, base_dir
            )
            if rel_path and rel_path in all_symbols:
                for sym in all_symbols[rel_path]:
                    if sym in rd.content:
                        documented_set.add(f"{rel_path}:{sym}")

    # Tally
    for rel_path, symbols in sorted(all_symbols.items()):
        for sym in symbols:
            qualified = f"{rel_path}:{sym}"
            stats.total_public += 1
            if qualified in documented_set:
                stats.referenced += 1
                stats.documented_symbols.append(qualified)
            else:
                stats.undocumented_symbols.append(qualified)

    return stats


def _resolve_ts_module_to_relpath(arg, source_paths, base_dir):
    """Resolve a TypeScript/JavaScript module argument to a relative path.

    Tries the arg as-is and with common extensions appended.
    """
    candidates = []

    # Direct path attempts
    candidates.append(arg)
    for sp in source_paths:
        candidates.append(os.path.join(sp, arg))

    # If no recognized extension, try common ones
    _, ext = os.path.splitext(arg)
    if ext not in _TS_JS_EXTENSIONS:
        for try_ext in _TS_JS_EXTENSIONS:
            candidates.append(arg + try_ext)
            for sp in source_paths:
                candidates.append(os.path.join(sp, arg + try_ext))
            # Also try index files: arg/index.ts etc.
            candidates.append(os.path.join(arg, "index" + try_ext))
            for sp in source_paths:
                candidates.append(os.path.join(sp, arg, "index" + try_ext))

    for candidate in candidates:
        full = os.path.join(base_dir, candidate)
        if os.path.isfile(full):
            return os.path.relpath(full, base_dir)

    return None


_USE_COLOR = sys.stdout.isatty()


def _color(text, code):
    """Wrap *text* in ANSI escape codes when color output is enabled."""
    if _USE_COLOR:
        return f"\033[{code}m{text}\033[0m"
    return text


def filter_lints(lints, ignore_codes):
    """Return lints excluding those whose code is in *ignore_codes*.

    Args:
        lints: List of LintResult objects.
        ignore_codes: Set or collection of code strings to suppress.

    Returns:
        Filtered list of LintResult objects.
    """
    if not ignore_codes:
        return lints
    return [lint for lint in lints if lint.code not in ignore_codes]


def print_results(result):
    """Print check results to stdout in a human-readable format.

    Args:
        result: CheckResult to print.
    """
    if not result.directive_results:
        print(_color("No directives found in documentation templates.", "1"))
    else:
        # Per-directive results
        print(_color("Directives", "1"))
        for dr in result.directive_results:
            if dr.error:
                status_str = _color(f"FAILED: {dr.error}", "31")
            else:
                status_str = _color("OK", "32")
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
                # Print undocumented symbols when coverage is below 100%
                if cov.undocumented_symbols and pct < 100:
                    print(_color("Undocumented symbols:", "1"))
                    # Group by file path
                    by_file: dict[str, list[str]] = {}
                    for qualified in cov.undocumented_symbols:
                        # qualified is "rel/path.py:symbol_name"
                        if ":" in qualified:
                            fpath, sym = qualified.rsplit(":", 1)
                        else:
                            fpath, sym = qualified, qualified
                        by_file.setdefault(fpath, []).append(sym)
                    for fpath in sorted(by_file):
                        symbols = ", ".join(by_file[fpath])
                        print(f"  {fpath}: {symbols}")
            else:
                print("Coverage: no public symbols found in source files")

    # Lint results -- all lints are always shown
    if result.lints:
        print()
        print(_color("Lints", "1"))
        for lint in result.lints:
            line_part = f":{lint.line}" if lint.line is not None else ""
            if lint.severity == "error":
                sev_str = _color(lint.severity, "31")
            elif lint.severity == "warning":
                sev_str = _color(lint.severity, "33")
            else:
                sev_str = lint.severity
            code_str = _color(f"[{lint.code}]", "36")
            print(
                f"  {sev_str}: {code_str} "
                f"{lint.file}{line_part} - {lint.message}"
            )
    else:
        print("No lints.")

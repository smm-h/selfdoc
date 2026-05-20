"""Check command -- validate directives and report documentation coverage.

Scans docs/ templates for directives, attempts to resolve each one,
and reports per-directive status (OK or FAILED). For all supported
languages, computes coverage: how many public/exported symbols are
referenced by directives vs. the total in source files.
"""

import os
import sys
from dataclasses import dataclass, field

import re

from selfdoc.docs import parse_frontmatter as _parse_frontmatter
from selfdoc.catalog import ALL_BUILTIN_DIRECTIVES
from selfdoc.tokenizer import (
    tokenize, Heading, Paragraph, BlankLine, CodeBlock,
    UnorderedList, OrderedList, Blockquote, DefinitionList,
    Directive,
)
from selfdoc.config import load_config
from selfdoc.directives import parse_directives, resolve_directives
from selfdoc.extractors import EXTRACTORS
from selfdoc.resolver import make_resolver
from selfdoc.staleness import (
    check_staleness,
    compute_content_hash,
    compute_description_hash,
    load_hashes,
    save_hashes,
)


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

    name: str  # directive name (ref, table-schema, code-test, etc.)
    attrs: dict  # directive attributes
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

    # Build valid directive names for parse-time validation
    valid_names = ALL_BUILTIN_DIRECTIVES | set(config.get("directives", {}).keys())

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
            if fname.startswith("_"):
                continue
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, docs_dir)

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            directives = parse_directives(content, valid_names=valid_names)
            for directive in directives:
                attrs_str = " ".join(
                    f'{k}="{v}"' for k, v in directive.attrs.items()
                )
                directive_str = f"{directive.name} {attrs_str}".strip()
                try:
                    resolved = resolver(
                        directive.name, directive.attrs, directive.body
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
                        if directive.attrs:
                            resolved_directives.append(
                                ResolvedDirective(
                                    name=directive.name,
                                    attrs=directive.attrs,
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

    # strictcli hard error: if the project uses strictcli and any directive
    # uses code-help, emit a hard error directing users to 'selfdoc gen'.
    if config["language"] == "python":
        from selfdoc.strictcli_support import uses_strictcli

        has_code_help = any(
            dr.directive.startswith("code-help")
            for dr in result.directive_results
        )
        if has_code_help and uses_strictcli(config["source"], dir_path):
            raise RuntimeError(
                "Project uses strictcli — use 'selfdoc gen' for CLI"
                " documentation instead of code-help directives"
            )

    # Compute coverage (language-agnostic via extractor protocol)
    language = config["language"]
    extractor = EXTRACTORS.get(language)
    if extractor is not None:
        result.coverage = _compute_coverage(
            config, dir_path, resolved_directives, extractor
        )

    # Run lint checks (SEO and other diagnostics)
    result.lints = _run_lints(docs_dir, resolver, config)

    # Description staleness detection: check if page content changed
    # but frontmatter description was not updated.
    stored_hashes = load_hashes(dir_path)
    current_hashes: dict[str, dict] = {}
    for root, _dirs, files in os.walk(docs_dir):
        if (os.path.abspath(root) == abs_output
                or os.path.abspath(root).startswith(abs_output + os.sep)):
            continue
        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue
            if fname.startswith("_"):
                continue
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, docs_dir)
            with open(full_path, "r", encoding="utf-8") as f:
                raw_content = f.read()
            metadata, body_content = _parse_frontmatter(raw_content)
            description = metadata.get("description")
            if description is None:
                continue
            # Resolve directives to get the final content for hashing
            resolved_content = resolve_directives(
                body_content, resolver, valid_names=valid_names,
            )
            c_hash = compute_content_hash(resolved_content)
            d_hash = compute_description_hash(str(description))
            current_hashes[rel_path] = {
                "content": c_hash,
                "description": d_hash,
            }
            stale_msg = check_staleness(
                rel_path, c_hash, d_hash, stored_hashes,
            )
            if stale_msg is not None:
                result.lints.append(LintResult(
                    file=rel_path,
                    line=None,
                    code="STALE001",
                    message=stale_msg,
                    severity="error",
                ))
    # Merge current hashes into stored (preserve pages not in this run)
    stored_hashes.update(current_hashes)
    save_hashes(stored_hashes, dir_path)

    return result


def _token_text_lines(tok):
    """Extract text lines from a content-bearing token.

    Returns a list of strings (one per source line) so the caller can
    compute per-line offsets from ``tok.start``.
    """
    if isinstance(tok, (Paragraph, Blockquote)):
        return tok.lines
    if isinstance(tok, (UnorderedList, OrderedList)):
        return tok.items
    if isinstance(tok, DefinitionList):
        lines = []
        for term, defs in tok.entries:
            lines.append(term)
            lines.extend(defs)
        return lines
    return []


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
            if fname.endswith(".md") and not fname.startswith("_"):
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, docs_dir)
                md_files.append((rel_path, full_path))

    project_name = os.path.basename(os.path.dirname(os.path.abspath(docs_dir)))

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

        metadata, body_content = _parse_frontmatter(content)
        tokens = tokenize(body_content)

        # Compute line offset: number of frontmatter lines consumed,
        # so token.start (1-based in body) maps to the original file
        fm_offset = len(content.split("\n")) - len(body_content.split("\n"))

        # Collect heading tokens for reuse across checks
        heading_tokens = [t for t in tokens if isinstance(t, Heading)]
        h1_tokens = [t for t in heading_tokens if t.level == 1]

        # Token types that carry prose content (not code blocks)
        _TEXT_TYPES = (
            Paragraph, UnorderedList, OrderedList, Blockquote,
            DefinitionList,
        )

        # SEO001 -- Multiple H1 headings in Markdown source
        # SEO013 -- No title source (neither frontmatter title nor # heading)
        h1_count = len(h1_tokens)
        if h1_count > 1:
            results.append(LintResult(
                file=rel_path,
                line=None,
                code="SEO001",
                message=f"Multiple H1 headings ({h1_count} found); use a single '# ' heading per page",
                severity="error",
            ))
        has_frontmatter_title = bool(metadata.get("title"))
        if h1_count == 0 and not has_frontmatter_title:
            results.append(LintResult(
                file=rel_path,
                line=None,
                code="SEO013",
                message="No title source: add a '# Heading' or set 'title:' in frontmatter",
                severity="error",
            ))

        # SEO002 -- Heading level gaps
        prev_level = 0
        for ht in heading_tokens:
            level = ht.level
            if prev_level > 0 and level > prev_level + 1:
                results.append(LintResult(
                    file=rel_path,
                    line=ht.start + fm_offset,
                    code="SEO002",
                    message=(
                        f"Heading level jumps from H{prev_level} to H{level}"
                        f" (skips H{prev_level + 1})"
                    ),
                    severity="warning",
                ))
            prev_level = level

        # SEO003 -- Empty alt text (only in text-bearing tokens)
        for tok in tokens:
            if not isinstance(tok, _TEXT_TYPES):
                continue
            # Get text lines from the token
            tok_lines = _token_text_lines(tok)
            for offset, line in enumerate(tok_lines):
                if "![](" in line:
                    results.append(LintResult(
                        file=rel_path,
                        line=tok.start + offset + fm_offset,
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
            # Auto-extract title from first H1 heading token
            if h1_tokens:
                h1_title = h1_tokens[0].text
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
            # Auto-extract from first Paragraph token (skipping
            # initial Heading, BlankLine, CodeBlock tokens)
            effective_desc = ""
            for tok in tokens:
                if isinstance(tok, (Heading, BlankLine, CodeBlock)):
                    continue
                if isinstance(tok, Paragraph):
                    first_line = tok.lines[0].strip() if tok.lines else ""
                    if first_line:
                        match = re.search(r"[.!?]", first_line)
                        if match:
                            effective_desc = first_line[:match.end()]
                        else:
                            effective_desc = first_line[:155]
                    break
                # Stop at any other content block type
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
        for i, tok in enumerate(tokens):
            if not isinstance(tok, Heading):
                continue
            if tok.level not in (2, 3):
                continue
            heading_text = tok.text.strip()
            # Collect non-BlankLine tokens after this heading
            next_tok = None
            next_tok_idx = None
            for j in range(i + 1, len(tokens)):
                if not isinstance(tokens[j], BlankLine):
                    next_tok = tokens[j]
                    next_tok_idx = j
                    break
            if next_tok is None:
                continue
            # Heading followed directly by a Directive: suppress SEO007
            if isinstance(next_tok, Directive):
                continue
            if not isinstance(next_tok, Paragraph):
                continue
            paragraph = " ".join(line.strip() for line in next_tok.lines)
            word_count = len(paragraph.split())
            if word_count < 30 or word_count > 80:
                # Check if a Directive follows the short paragraph
                # (possibly with BlankLines between). If so, the
                # directive will expand into content, so suppress.
                has_directive_after = False
                for k in range(next_tok_idx + 1, len(tokens)):
                    if isinstance(tokens[k], BlankLine):
                        continue
                    if isinstance(tokens[k], Directive):
                        has_directive_after = True
                    break
                if has_directive_after:
                    continue
                results.append(LintResult(
                    file=rel_path,
                    line=tok.start + fm_offset,
                    code="SEO007",
                    message=(
                        f"First paragraph after '{heading_text}' is"
                        f" {word_count} words (aim for 40-60 for AI citation)"
                    ),
                    severity="warning",
                ))

        # SEO008 -- Statistics density (count only prose content tokens)
        prose_words = []
        for tok in tokens:
            if isinstance(tok, Paragraph):
                for line in tok.lines:
                    prose_words.extend(line.split())
            elif isinstance(tok, (UnorderedList, OrderedList)):
                for item in tok.items:
                    prose_words.extend(item.split())
            elif isinstance(tok, Blockquote):
                for line in tok.lines:
                    prose_words.extend(line.split())
            elif isinstance(tok, DefinitionList):
                for term, defs in tok.entries:
                    prose_words.extend(term.split())
                    for d in defs:
                        prose_words.extend(d.split())

        total_words = len(prose_words)
        if total_words >= 200:
            numeric_count = sum(
                1 for w in prose_words if any(c.isdigit() for c in w)
            )
            expected = max(1, total_words // 200)
            if numeric_count < expected:
                results.append(LintResult(
                    file=rel_path,
                    line=None,
                    code="SEO008",
                    message=(
                        f"Page has {total_words} words but only"
                        f" {numeric_count} numeric data points"
                        f" (recommend at least {expected}"
                        f" for AI citation)"
                    ),
                    severity="warning",
                ))

        # SEO011 -- Empty heading section (heading followed by same-or-higher
        # level heading with no content between)
        last_heading_info = None  # (start_line, level)
        for tok in tokens:
            if isinstance(tok, Heading) and tok.level in (2, 3):
                level = tok.level
                if last_heading_info is not None:
                    prev_line_num, prev_level = last_heading_info
                    if level <= prev_level:
                        results.append(LintResult(
                            file=rel_path,
                            line=prev_line_num + fm_offset,
                            code="SEO011",
                            message=(
                                f"H{prev_level} heading has no content"
                                f" before next H{level} heading"
                            ),
                            severity="warning",
                        ))
                last_heading_info = (tok.start, level)
            elif not isinstance(tok, (BlankLine, Heading)):
                # Non-blank, non-heading token resets tracking
                last_heading_info = None

        # SEO014 -- Meaningless alt text (only in text-bearing tokens)
        for tok in tokens:
            if not isinstance(tok, _TEXT_TYPES):
                continue
            tok_lines = _token_text_lines(tok)
            for offset, line in enumerate(tok_lines):
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
                            line=tok.start + offset + fm_offset,
                            code="SEO014",
                            message=(
                                f"Meaningless alt text '{alt}';"
                                f" use a descriptive alternative"
                            ),
                            severity="warning",
                        ))

        # SEO015 -- Generic anchor text (only in text-bearing tokens)
        for tok in tokens:
            if not isinstance(tok, _TEXT_TYPES):
                continue
            tok_lines = _token_text_lines(tok)
            for offset, line in enumerate(tok_lines):
                for m in re.finditer(r"\[([^\]]+)\]\(", line):
                    text = m.group(1).strip().lower()
                    if text in _GENERIC_ANCHORS:
                        results.append(LintResult(
                            file=rel_path,
                            line=tok.start + offset + fm_offset,
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
    light_vars = _extract_css_vars(root_match.group(1)) if root_match else {}

    # Extract [data-theme="dark"] block variables
    dark_match = re.search(
        r'\[data-theme="dark"\]\s*\{([^}]+)\}', css_content
    )
    dark_vars = _extract_css_vars(dark_match.group(1)) if dark_match else {}

    # Check theme defaults
    if light_vars:
        _check_pairs(lints, light_vars, pairs, "")
    if dark_vars:
        _check_pairs(lints, dark_vars, pairs, "dark mode ")

    # Check custom.css overrides (if present)
    custom_css_path = os.path.join(base_dir, "custom.css")
    if os.path.isfile(custom_css_path):
        with open(custom_css_path, "r", encoding="utf-8") as f:
            custom_content = f.read()

        # Extract custom :root overrides and merge onto theme defaults
        custom_root_match = re.search(
            r":root\s*\{([^}]+)\}", custom_content
        )
        if custom_root_match and light_vars:
            custom_light = _extract_css_vars(custom_root_match.group(1))
            merged_light = {**light_vars, **custom_light}
            _check_pairs(
                lints, merged_light, pairs, "",
                css_file="custom.css",
            )

        # Extract custom dark mode overrides and merge onto theme defaults
        custom_dark_match = re.search(
            r'\[data-theme="dark"\]\s*\{([^}]+)\}', custom_content
        )
        if custom_dark_match and dark_vars:
            custom_dark = _extract_css_vars(custom_dark_match.group(1))
            merged_dark = {**dark_vars, **custom_dark}
            _check_pairs(
                lints, merged_dark, pairs, "dark mode ",
                css_file="custom.css",
            )


def _check_pairs(lints, css_vars, pairs, mode_prefix, css_file="theme CSS"):
    """Check contrast ratio for each pair and emit SEO012 if below threshold."""
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


def _compute_coverage(config, base_dir, resolved_directives, extractor):
    """Count public symbols in source files vs. those documented by directives.

    Language-agnostic: uses the extractor protocol to discover public symbols
    and resolve file paths. A symbol is "documented" if its name appears in
    the resolved content of a directive that references its file.

    Files whose module path matches a ``gen.exclude`` pattern are skipped
    so that intentionally-internal modules do not drag down coverage.
    """
    from selfdoc.gen import _file_to_module_path, _is_excluded

    base_dir = os.path.abspath(base_dir)
    source_paths = config["source"]
    language = config["language"]
    stats = CoverageStats()
    extensions = extractor.file_extensions()

    # Build gen-exclude list from config
    gen_config = config.get("gen") or {}
    gen_excludes = list(gen_config.get("exclude", []))

    # Collect all source files and their public symbols
    # Map: relative file path -> list of public symbol names
    all_symbols: dict[str, list[str]] = {}

    for sp in source_paths:
        src_dir = os.path.join(base_dir, sp)
        if not os.path.isdir(src_dir):
            continue
        for root, _dirs, files in os.walk(src_dir):
            for fname in sorted(files):
                if not any(fname.endswith(ext) for ext in extensions):
                    continue
                # Skip test files (Go: *_test.go, TS/JS: *.test.* / *.spec.*)
                if fname.endswith("_test.go"):
                    continue
                if any(
                    fname.endswith(f".test{ext}") or fname.endswith(f".spec{ext}")
                    for ext in extensions
                ):
                    continue
                full_path = os.path.join(root, fname)
                rel_to_base = os.path.relpath(full_path, base_dir)
                # Skip files excluded from doc generation
                if gen_excludes:
                    mod_path = _file_to_module_path(
                        full_path, base_dir, language,
                    )
                    if mod_path and _is_excluded(mod_path, gen_excludes):
                        continue
                symbols = extractor.public_symbols(full_path)
                if symbols:
                    all_symbols[rel_to_base] = symbols

    # Build set of documented symbols (as "rel/path:symbol_name")
    documented_set: set[str] = set()

    for rd in resolved_directives:
        # Directives that reference source files have a "path" attr
        path_arg = rd.attrs.get("path", "")
        if not path_arg:
            continue

        # Resolve path via the extractor
        resolved_path = extractor.resolve_path(
            path_arg, source_paths, base_dir
        )
        if resolved_path is None:
            continue

        # For directory-based resolution (e.g. Go packages), resolved_path
        # is a directory. Match all files in that directory.
        if os.path.isdir(resolved_path):
            dir_abs = os.path.abspath(resolved_path)
            for rel_path, syms in all_symbols.items():
                file_dir = os.path.dirname(
                    os.path.join(base_dir, rel_path)
                )
                if os.path.abspath(file_dir).startswith(dir_abs):
                    for sym in syms:
                        if sym in rd.content:
                            documented_set.add(f"{rel_path}:{sym}")
        else:
            # File-based resolution
            rel_path = os.path.relpath(resolved_path, base_dir)
            if rel_path in all_symbols:
                # For ref directives, check each symbol against content
                if rd.name == "ref":
                    for sym in all_symbols[rel_path]:
                        if sym in rd.content:
                            documented_set.add(f"{rel_path}:{sym}")
                else:
                    # For targeted directives (table-schema, code-test, etc.),
                    # check the target attr for a specific symbol
                    target = rd.attrs.get("target", "")
                    if target and target in all_symbols[rel_path]:
                        documented_set.add(f"{rel_path}:{target}")
                    else:
                        # No target -- check all symbols against content
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

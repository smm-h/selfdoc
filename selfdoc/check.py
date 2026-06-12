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

from selfdoc.build import _extract_version_content
from selfdoc.utils import parse_frontmatter as _parse_frontmatter
from selfdoc.docs import resolve_all_docs
from selfdoc.catalog import ALL_BUILTIN_DIRECTIVES
from selfdoc.tokenizer import (
    tokenize, Heading, Paragraph, BlankLine, CodeBlock,
    UnorderedList, OrderedList, Blockquote, DefinitionList,
    Directive,
)
from selfdoc.config import load_config
from selfdoc.directives import parse_directives
from selfdoc.extractors import EXTRACTORS, SourceEntry
from selfdoc.resolver import make_resolver, Resolver
from selfdoc.staleness import update_hashes
from selfdoc.gen import _DEFAULT_DESCRIPTION_RE


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
    file: str = ""  # relative path within docs/ (which page this directive is on)
    source_entry: "SourceEntry | None" = None  # which source entry matched


@dataclass
class CoverageStats:
    """Coverage of public symbols by directives."""

    total_public: int = 0
    referenced: int = 0
    documented: int = 0  # symbols on non-skeleton (hand-written or customized) pages
    # Symbols that are referenced by any directive (skeleton or not)
    referenced_symbols: list[str] = field(default_factory=list)
    # Symbols that are documented on non-skeleton (hand-written or customized) pages
    documented_symbols: list[str] = field(default_factory=list)
    # Symbols that are NOT referenced by any directive
    unreferenced_symbols: list[str] = field(default_factory=list)


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


def _validate_directives(docs_dict, resolver, valid_names, file_prefix="",
                         collect_resolved=False):
    """Validate directives across a set of documentation templates.

    Parses directives from each template, attempts resolution, and
    records per-directive OK/FAILED results.

    Args:
        docs_dict: Dict from resolve_all_docs mapping rel_path to
            (frontmatter, resolved, raw_content, fm_line_count).
        resolver: Directive resolver callable.
        valid_names: Set of valid directive names for parse-time validation.
        file_prefix: String prepended to rel_path in results (e.g. "[0.1.0] ").
        collect_resolved: If True, collect successfully resolved directives
            with attrs into a list for coverage tracking.

    Returns:
        (directive_results, resolved_directives) where directive_results is
        a list of DirectiveResult and resolved_directives is a list of
        ResolvedDirective (empty if collect_resolved is False).
    """
    directive_results = []
    resolved_directives = []

    for rel_path in sorted(docs_dict):
        _fm, _resolved, raw_content, fm_line_count = docs_dict[rel_path]
        directives = parse_directives(raw_content, valid_names=valid_names)
        display_file = f"{file_prefix}{rel_path}" if file_prefix else rel_path

        for directive in directives:
            file_line = directive.line_number + fm_line_count
            attrs_str = " ".join(
                f'{k}="{v}"' for k, v in directive.attrs.items()
            )
            directive_str = f"{directive.name} {attrs_str}".strip()
            try:
                resolved = resolver(
                    directive.name, directive.attrs, directive.body,
                )
                if resolved.startswith("> *[selfdoc:"):
                    error_msg = resolved.strip("> *[]")
                    if error_msg.startswith("selfdoc: "):
                        error_msg = error_msg[len("selfdoc: "):]
                    directive_results.append(DirectiveResult(
                        file=display_file,
                        line=file_line,
                        directive=directive_str,
                        status="FAILED",
                        error=error_msg,
                    ))
                else:
                    directive_results.append(DirectiveResult(
                        file=display_file,
                        line=file_line,
                        directive=directive_str,
                        status="OK",
                    ))
                    if collect_resolved and directive.attrs:
                        # Read the matched source entry from the resolver
                        src_entry = None
                        if isinstance(resolver, Resolver):
                            src_entry = resolver.last_source_entry
                        resolved_directives.append(
                            ResolvedDirective(
                                name=directive.name,
                                attrs=directive.attrs,
                                content=resolved,
                                file=rel_path,
                                source_entry=src_entry,
                            )
                        )
            except Exception as exc:
                directive_results.append(DirectiveResult(
                    file=display_file,
                    line=file_line,
                    directive=directive_str,
                    status="FAILED",
                    error=str(exc),
                ))

    return directive_results, resolved_directives


def check_docs(dir_path=".", config=None, dry_run=False):
    """Validate all directives in docs templates and report coverage.

    Scans docs/ for .md templates, parses directives, attempts to resolve
    each one, and computes coverage for Python projects.

    Args:
        dir_path: Project root directory.
        config: Pre-loaded config dict (if None, loads from selfdoc.json).
        dry_run: If True, report staleness without writing hashes to disk.

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

    # Resolve all docs via the shared pipeline (provides frontmatter,
    # resolved content, raw content, and frontmatter line count).
    all_docs = resolve_all_docs(config, base_dir=dir_path)

    # Per-directive validation and coverage tracking.
    dir_results, resolved_directives = _validate_directives(
        all_docs, resolver, valid_names, collect_resolved=True,
    )
    result.directive_results.extend(dir_results)

    # strictcli hard error: if the project uses strictcli and any directive
    # uses code-help, emit a hard error directing users to 'selfdoc gen'.
    from selfdoc.strictcli_support import uses_strictcli

    has_code_help = any(
        dr.directive.startswith("code-help")
        for dr in result.directive_results
    )
    from selfdoc.extractors import resolve_source_entries, source_paths as _source_paths

    if has_code_help and uses_strictcli(_source_paths(config), dir_path):
        raise RuntimeError(
            "Project uses strictcli — use 'selfdoc gen' for CLI"
            " documentation instead of code-help directives"
        )

    # Compute coverage (language-agnostic via extractor protocol)
    src_entries = resolve_source_entries(config)
    if src_entries:
        result.coverage = _compute_coverage(
            config, dir_path, resolved_directives, src_entries, all_docs
        )

    # Run lint checks (SEO and other diagnostics)
    result.lints = _run_lints(all_docs, docs_dir, resolver, config)

    # XREF002: directive path validation -- verify resolved directive
    # source files actually exist on disk.
    for rd in resolved_directives:
        path_arg = rd.attrs.get("path", "")
        if not path_arg or rd.source_entry is None:
            continue
        entry = rd.source_entry
        resolved_path = entry.extractor.resolve_path(
            path_arg, [entry.path], dir_path,
        )
        if resolved_path is None or not os.path.isfile(resolved_path):
            result.lints.append(LintResult(
                file=rd.file,
                line=None,
                code="XREF002",
                message=(
                    f"directive path '{path_arg}' resolves but"
                    f" file does not exist on disk"
                ),
                severity="error",
            ))

    # LANG001: unsupported language detection via StubExtractor
    from selfdoc.extractors.base import StubExtractor as _StubExtractor
    for entry in src_entries:
        if isinstance(entry.extractor, _StubExtractor):
            result.lints.append(LintResult(
                file="selfdoc.json",
                line=None,
                code="LANG001",
                message=(
                    f"No extractor for language '{entry.language}'"
                    f" (source path: {entry.path})"
                ),
                severity="error",
            ))

    # Project-level version consistency checks
    result.lints.extend(_check_version_consistency(config, dir_path))

    # Description staleness detection: check if page content changed
    # but frontmatter description was not updated.
    # Uses frontmatter and resolved content from resolve_all_docs instead
    # of re-walking docs/ and re-resolving directives.
    # Prefix hash keys with locale code (matching build.py) so that gen
    # and check use the same key space in hashes.json.
    locales = config.get("locales") or []
    if locales:
        locale_code = locales[0]["code"]
        prefixed_docs = {f"{locale_code}/{rp}": val for rp, val in all_docs.items()}
        stale_warnings = update_hashes(prefixed_docs, dir_path, dry_run=dry_run)
    else:
        stale_warnings = update_hashes(all_docs, dir_path, dry_run=dry_run)
    for rel_path, stale_msg in stale_warnings:
        result.lints.append(LintResult(
            file=rel_path,
            line=None,
            code="STALE001",
            message=stale_msg,
            severity="error",
        ))

    # Validate old versions when multi-version is configured.
    # The working-tree check above covers the latest version; here we
    # extract each older version from its git tag and run directive
    # validation and lint on it, prefixing results with the version string.
    versions = config.get("versions") or []
    if len(versions) > 1:
        latest_version = versions[-1]["version"]
        for ver_entry in versions:
            ver_str = ver_entry["version"]
            if ver_str == latest_version:
                continue  # already validated above (working tree)
            try:
                cache_dir = _extract_version_content(
                    ver_str, config, dir_path,
                )
            except RuntimeError:
                result.lints.append(LintResult(
                    file=f"[{ver_str}]",
                    line=None,
                    code="VER001",
                    message=f"Could not extract content for version {ver_str}",
                    severity="error",
                ))
                continue

            # Build a resolver against the extracted content
            ver_resolver = make_resolver(config, cache_dir)
            ver_docs = resolve_all_docs(config, base_dir=cache_dir)

            ver_dir_results, _ = _validate_directives(
                ver_docs, ver_resolver, valid_names,
                file_prefix=f"[{ver_str}] ",
            )
            result.directive_results.extend(ver_dir_results)

            # Run lint checks on the extracted version's docs
            ver_docs_dir = os.path.join(
                cache_dir, config["docs"].rstrip("/"),
            )
            if os.path.isdir(ver_docs_dir):
                ver_lints = _run_lints(
                    ver_docs, ver_docs_dir, ver_resolver, config,
                )
                for lint in ver_lints:
                    lint.file = f"[{ver_str}] {lint.file}"
                    result.lints.append(lint)

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


def _check_version_consistency(config, dir_path):
    """Check version consistency between config and project manifest.

    VER002: config["version"] differs from detected project version.
    VER003: versions array last entry doesn't match config["version"].
    """
    from selfdoc.utils import detect_project_version

    results = []

    config_version = config.get("version")

    # VER002: config version vs detected project version
    # Skip when version_source is set -- the version was already read from
    # the manifest during config loading, so it cannot diverge.
    if config_version and not config.get("version_source"):
        detected = detect_project_version(dir_path)
        if detected and detected != config_version:
            results.append(LintResult(
                file="selfdoc.json",
                line=None,
                code="VER002",
                message=(
                    f"Config version '{config_version}' does not match"
                    f" detected project version '{detected}'"
                ),
                severity="error",
            ))

    # VER003: versions array last entry vs config version
    versions = config.get("versions") or []
    if config_version and versions:
        last_version = versions[-1].get("version", "")
        if last_version and last_version != config_version:
            results.append(LintResult(
                file="selfdoc.json",
                line=None,
                code="VER003",
                message=(
                    f"Last entry in versions array ('{last_version}') does"
                    f" not match config version ('{config_version}')"
                ),
                severity="error",
            ))

    return results


def _run_lints(all_docs, docs_dir, resolver, config):
    """Run lint checks on documentation templates.

    Args:
        all_docs: Dict from resolve_all_docs mapping rel_path to
            (frontmatter, resolved, raw_content, fm_line_count).
        docs_dir: Absolute path to the docs directory.
        resolver: Directive resolver callable.
        config: Project configuration dict.

    Returns a list of LintResult diagnostics covering SEO best practices:
    multiple H1s, heading level gaps, empty alt text, title length,
    missing base_url, and missing description.
    """
    results = []

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

    for rel_path in sorted(all_docs):
        metadata, _resolved, body_content, fm_offset = all_docs[rel_path]
        tokens = tokenize(body_content)

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


def _is_skeleton_page(frontmatter):
    """Return True if the page is a skeleton auto-generated page.

    A page is "skeleton" when it has ``generated: true`` AND its
    description still matches the default auto-generated pattern.
    A generated page whose description has been customized counts
    as documented (someone edited it).
    """
    if frontmatter.get("generated") is not True:
        return False
    description = frontmatter.get("description", "")
    if not isinstance(description, str):
        return False
    return bool(_DEFAULT_DESCRIPTION_RE.match(description))


def _compute_coverage(config, base_dir, resolved_directives, source_entries,
                      all_docs=None):
    """Count public symbols in source files vs. those documented by directives.

    Multi-language: iterates over all source entries, using each entry's
    extractor to discover public symbols and resolve file paths. Two-tier
    tracking:
    - "referenced": symbol appears in ANY directive's resolved output
    - "documented": symbol appears on a non-skeleton page (hand-written or
      generated with a customized description)

    Files whose module path matches a ``gen.exclude`` pattern are skipped
    so that intentionally-internal modules do not drag down coverage.

    Args:
        source_entries: List of SourceEntry objects (each with path, language,
            extractor). Replaces the old single-extractor parameter.
        all_docs: Dict from resolve_all_docs mapping rel_path to
            (frontmatter, resolved, raw_content, fm_line_count).
            When provided, enables two-tier skeleton page detection.
    """
    from selfdoc.gen import _file_to_module_path, _is_excluded, _should_skip_dir

    base_dir = os.path.abspath(base_dir)
    stats = CoverageStats()

    # Build gen-exclude list from config
    gen_config = config.get("gen") or {}
    gen_excludes = list(gen_config.get("exclude", []))

    # Pre-compute set of skeleton pages (for two-tier coverage)
    skeleton_pages: set[str] = set()
    if all_docs:
        for rel_path, (frontmatter, _resolved, _raw, _fm_lc) in all_docs.items():
            if _is_skeleton_page(frontmatter):
                skeleton_pages.add(rel_path)

    # Group source entries by (language, extractor) to collect all paths
    # for each language together.
    groups: dict[str, tuple[str, object, list[str]]] = {}
    for entry in source_entries:
        key = entry.language
        if key not in groups:
            groups[key] = (entry.language, entry.extractor, [])
        groups[key][2].append(entry.path)

    # Collect all source files and their public symbols across all languages.
    # Map: relative file path -> list of public symbol names
    all_symbols: dict[str, list[str]] = {}

    for language, extractor, paths in groups.values():
        extensions = extractor.file_extensions()
        for sp in paths:
            src_dir = os.path.join(base_dir, sp)
            if not os.path.isdir(src_dir):
                continue
            for root, dirs, files in os.walk(src_dir):
                dirs[:] = [d for d in dirs if not _should_skip_dir(d)]
                for fname in sorted(files):
                    if not any(fname.endswith(ext) for ext in extensions):
                        continue
                    # Skip test files:
                    # Go: *_test.go
                    # TS/JS: *.test.* / *.spec.*
                    # Python: test_*.py, conftest.py
                    if fname.endswith("_test.go"):
                        continue
                    if any(
                        fname.endswith(f".test{ext}") or fname.endswith(f".spec{ext}")
                        for ext in extensions
                    ):
                        continue
                    if fname.startswith("test_") and fname.endswith(".py"):
                        continue
                    if fname == "conftest.py":
                        continue
                    # Skip files inside test directories (tests/, test/, __tests__/)
                    rel_to_src = os.path.relpath(root, src_dir)
                    path_parts = rel_to_src.replace(os.sep, "/").split("/")
                    if any(
                        part in ("tests", "test", "__tests__")
                        for part in path_parts
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

    # Build two sets:
    # - referenced_set: all symbols matched by any directive
    # - documented_set: symbols matched by directives on non-skeleton pages
    referenced_set: set[str] = set()
    documented_set: set[str] = set()

    for rd in resolved_directives:
        # Directives that reference source files have a "path" attr
        path_arg = rd.attrs.get("path", "")
        if not path_arg:
            continue

        # Use the directive's matched source entry for resolution.
        # Content directives (source_entry is None) are skipped.
        if rd.source_entry is None:
            continue

        rd_extractor = rd.source_entry.extractor
        rd_language = rd.source_entry.language
        # Get all paths for the directive's language group
        if rd_language in groups:
            _, _, rd_source_paths = groups[rd_language]
        else:
            continue

        resolved_path = rd_extractor.resolve_path(
            path_arg, rd_source_paths, base_dir
        )
        if resolved_path is None:
            continue

        is_skeleton = rd.file in skeleton_pages

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
                            qualified = f"{rel_path}:{sym}"
                            referenced_set.add(qualified)
                            if not is_skeleton:
                                documented_set.add(qualified)
        else:
            # File-based resolution
            rel_path = os.path.relpath(resolved_path, base_dir)
            if rel_path in all_symbols:
                # For ref directives, check each symbol against content
                if rd.name == "ref":
                    for sym in all_symbols[rel_path]:
                        if sym in rd.content:
                            qualified = f"{rel_path}:{sym}"
                            referenced_set.add(qualified)
                            if not is_skeleton:
                                documented_set.add(qualified)
                else:
                    # For targeted directives (table-schema, code-test, etc.),
                    # check the target attr for a specific symbol
                    target = rd.attrs.get("target", "")
                    if target and target in all_symbols[rel_path]:
                        qualified = f"{rel_path}:{target}"
                        referenced_set.add(qualified)
                        if not is_skeleton:
                            documented_set.add(qualified)
                    else:
                        # No target -- check all symbols against content
                        for sym in all_symbols[rel_path]:
                            if sym in rd.content:
                                qualified = f"{rel_path}:{sym}"
                                referenced_set.add(qualified)
                                if not is_skeleton:
                                    documented_set.add(qualified)

    # Tally
    for rel_path, symbols in sorted(all_symbols.items()):
        for sym in symbols:
            qualified = f"{rel_path}:{sym}"
            stats.total_public += 1
            if qualified in referenced_set:
                stats.referenced += 1
                stats.referenced_symbols.append(qualified)
                if qualified in documented_set:
                    stats.documented += 1
                    stats.documented_symbols.append(qualified)
            else:
                stats.unreferenced_symbols.append(qualified)

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
                doc_pct = cov.documented * 100 // cov.total_public
                ref_pct = cov.referenced * 100 // cov.total_public
                print(
                    f"Coverage: {cov.documented}/{cov.total_public} "
                    f"symbols documented ({doc_pct}%)"
                )
                if cov.referenced != cov.documented:
                    print(
                        f"          {cov.referenced}/{cov.total_public} "
                        f"symbols referenced ({ref_pct}%)"
                    )
                # Print unreferenced symbols when ref coverage is below 100%
                if cov.unreferenced_symbols and ref_pct < 100:
                    print(_color("Unreferenced symbols:", "1"))
                    # Group by file path
                    by_file: dict[str, list[str]] = {}
                    for qualified in cov.unreferenced_symbols:
                        # qualified is "rel/path.py:symbol_name"
                        if ":" in qualified:
                            fpath, sym = qualified.rsplit(":", 1)
                        else:
                            fpath, sym = qualified, qualified
                        by_file.setdefault(fpath, []).append(sym)
                    for fpath in sorted(by_file):
                        symbols = ", ".join(by_file[fpath])
                        print(f"  {fpath}: {symbols}")
                # Print skeleton-only symbols when doc coverage is below 100%
                if doc_pct < 100:
                    documented_set = set(cov.documented_symbols)
                    skeleton_only = [
                        s for s in cov.referenced_symbols
                        if s not in documented_set
                    ]
                    if skeleton_only:
                        print(_color("Skeleton-only symbols:", "1"))
                        by_file_skel: dict[str, list[str]] = {}
                        for qualified in skeleton_only:
                            if ":" in qualified:
                                fpath, sym = qualified.rsplit(":", 1)
                            else:
                                fpath, sym = qualified, qualified
                            by_file_skel.setdefault(fpath, []).append(sym)
                        for fpath in sorted(by_file_skel):
                            symbols = ", ".join(by_file_skel[fpath])
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


def check_unified(dir_path=".", config=None, dry_run=False):
    """Check all constituent projects in a unified build.

    Iterates over each project in the ``unified`` config section,
    loads its own selfdoc.json, and runs check_docs on it. Errors
    are prefixed with the project slug for clear attribution.

    Also checks the docs-site's own content (the common pages).

    Args:
        dir_path: The docs-site's project root directory.
        config: Pre-loaded config dict (if None, loads from selfdoc.json).
        dry_run: If True, report staleness without writing hashes to disk.

    Returns:
        CheckResult with aggregated results from all projects.
    """
    from selfdoc.unified import _project_slug, _resolve_project_path

    if config is None:
        config = load_config(dir_path)
    if config is None:
        raise RuntimeError(
            "No selfdoc.json found. Run 'selfdoc init' to initialize."
        )

    unified_config = config.get("unified")
    if unified_config is None:
        raise RuntimeError("No 'unified' section in selfdoc.json")

    aggregate = CheckResult()

    # Check each constituent project
    for project_entry in unified_config["projects"]:
        slug = _project_slug(project_entry)
        project_path = _resolve_project_path(project_entry, dir_path)
        proj_config = load_config(project_path)
        if proj_config is None:
            aggregate.lints.append(LintResult(
                file=f"[{slug}]",
                line=None,
                code="UNIFIED001",
                message=f"No selfdoc.json in project '{slug}'",
                severity="error",
            ))
            continue

        try:
            proj_result = check_docs(project_path, config=proj_config, dry_run=dry_run)
        except RuntimeError as exc:
            aggregate.lints.append(LintResult(
                file=f"[{slug}]",
                line=None,
                code="UNIFIED002",
                message=str(exc),
                severity="error",
            ))
            continue

        # Prefix directive results with project slug
        for dr in proj_result.directive_results:
            dr.file = f"[{slug}] {dr.file}"
            aggregate.directive_results.append(dr)

        # Prefix lint results with project slug
        for lint in proj_result.lints:
            lint.file = f"[{slug}] {lint.file}"
            aggregate.lints.append(lint)

        # Merge coverage stats
        if proj_result.coverage is not None:
            if aggregate.coverage is None:
                aggregate.coverage = CoverageStats()
            aggregate.coverage.total_public += proj_result.coverage.total_public
            aggregate.coverage.referenced += proj_result.coverage.referenced
            aggregate.coverage.documented += proj_result.coverage.documented
            aggregate.coverage.referenced_symbols.extend(
                f"[{slug}] {s}" for s in proj_result.coverage.referenced_symbols
            )
            aggregate.coverage.documented_symbols.extend(
                f"[{slug}] {s}" for s in proj_result.coverage.documented_symbols
            )
            aggregate.coverage.unreferenced_symbols.extend(
                f"[{slug}] {s}" for s in proj_result.coverage.unreferenced_symbols
            )

    # Check the docs-site's own content
    try:
        common_result = check_docs(dir_path, config=config, dry_run=dry_run)
    except RuntimeError as exc:
        aggregate.lints.append(LintResult(
            file="[common]",
            line=None,
            code="UNIFIED002",
            message=str(exc),
            severity="error",
        ))
    else:
        for dr in common_result.directive_results:
            dr.file = f"[common] {dr.file}"
            aggregate.directive_results.append(dr)
        for lint in common_result.lints:
            lint.file = f"[common] {lint.file}"
            aggregate.lints.append(lint)

    return aggregate

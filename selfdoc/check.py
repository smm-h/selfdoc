"""Check command -- validates directive resolution, measures documentation coverage, runs SEO lint rules, and detects stale or drifted descriptions.

Scans docs/ templates for directives, attempts to resolve each one,
and reports per-directive status (OK or FAILED). For all supported
languages, computes coverage: how many public/exported symbols are
referenced by directives vs. the total in source files.
"""

import ast
import dataclasses
import json
import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

import re

from selfdoc.build import _extract_version_content
from selfdoc_core.prose import first_sentence
from selfdoc.docs import resolve_all_docs
from selfdoc.utils import parse_frontmatter
from selfdoc.catalog import ALL_BUILTIN_DIRECTIVES
from selfdoc.tokenizer import (
    tokenize, Heading, Paragraph, BlankLine, CodeBlock,
    UnorderedList, OrderedList, Blockquote, DefinitionList,
    Directive, TEXT_BEARING, token_text_lines,
)
from selfdoc.catalog import validate_directive_attrs
from selfdoc.config import load_config
from selfdoc.directives import parse_directives, validate_directive_names
from selfdoc.extractors import SourceEntry
from selfdoc_core.extractors.base import symbol_heading_pattern
from selfdoc.resolver import make_resolver, Resolver
from selfdoc.strictcli_support import SchemaDiscoveryError
from selfdoc.staleness import (
    compute_current_hashes,
    compute_schema_hash,
    load_hashes,
    save_hashes,
    update_hashes,
)
from selfdoc.ownership import is_machine_owned

from selfdoc_core import effects, spelling
# Re-exported: the lint registry owns LintResult (severity is derived from the
# registered code, never passed in) and the shared check-verdict rules.
from selfdoc_core.lints import (  # noqa: F401
    LINT_REGISTRY,
    LintResult,
    check_exit_code,
    coverage_below_threshold,
)


def _machine_owned_keys(all_docs, dir_path, cli_structure, locale_prefix):
    """Return the locale-prefixed page keys whose description is machine-owned.

    These pages are exempt from the STALE001/DRIFT001 baseline hold: their
    description is a machine placeholder (recognized by the ownership predicate
    via template match or the recorded ``seed_hash``), so holding the baseline
    would deadlock -- they cannot be hand-fixed.  Hand-described generated
    pages (text NOT machine-classified) are absent from this set and therefore
    receive full staleness protection.
    """
    stored = load_hashes(dir_path)
    keys = set()
    for rp, (fm, _r, _raw, _lc) in all_docs.items():
        key = f"{locale_prefix}/{rp}" if locale_prefix else rp
        seed = stored.get(key, {}).get("seed_hash")
        if is_machine_owned(rp, fm, seed_hash=seed, cli_structure=cli_structure):
            keys.add(key)
    return keys

_DIRECTIVE_MARKERS = {":-:", ":<:", ":>:", ":@:", ":=:", ":::"}


# ---------------------------------------------------------------------------
# EXAMPLE002/EXAMPLE003 -- opt-in semantic example validation
# ---------------------------------------------------------------------------
#
# EXAMPLE001 parses a fenced block; it cannot tell a program that compiles
# from a program that works.  A ``validate`` token in the fence info string
# opts a block into the semantic tier: selfdoc writes it to a scratch file
# and hands the path to the command configured for that language under the
# ``examples`` config key.  The marker is opt-in because most documentation
# snippets are deliberately partial -- an opt-out polarity would flag them
# all.  A marker whose language has no configured command is EXAMPLE003, a
# hard error rather than a silent skip: a marker that validates nothing is
# indistinguishable from a passing one, which is the failure mode the whole
# tier exists to remove.
#
# No sandbox: the configured validators compile and register, they are not a
# harness for running untrusted payloads, and the snippets are the project's
# own documentation.

# Seconds a configured validator may run before it is killed.  Selfdoc's
# "external calls must have timeouts" convention -- no unbounded wait.
_EXAMPLE_VALIDATE_TIMEOUT = 60

# How many trailing output lines of a failing validator reach the message.
_EXAMPLE_STDERR_TAIL_LINES = 5

# Scratch-file suffix per fenced-block language.  Validators dispatch on the
# extension (a Go toolchain will not look at a file that is not ``*.go``), so
# the marked language has to survive the trip to disk.
_EXAMPLE_SUFFIXES = {
    "python": ".py", "py": ".py", "python3": ".py",
    "go": ".go", "golang": ".go",
    "ts": ".ts", "typescript": ".ts",
    "js": ".js", "javascript": ".js", "jsx": ".jsx", "tsx": ".tsx",
    "json": ".json",
    "rust": ".rs", "rs": ".rs",
    "sh": ".sh", "bash": ".sh", "shell": ".sh",
    "c": ".c", "cpp": ".cpp", "c++": ".cpp",
    "java": ".java", "kotlin": ".kt", "kt": ".kt",
    "swift": ".swift", "dart": ".dart", "zig": ".zig",
    "ruby": ".rb", "rb": ".rb",
    "sql": ".sql", "toml": ".toml",
    "yaml": ".yaml", "yml": ".yml",
    "svelte": ".svelte",
}


def _example_suffix(lang):
    """Return the scratch-file suffix for a fenced-block *lang*."""
    known = _EXAMPLE_SUFFIXES.get(lang)
    if known:
        return known
    cleaned = re.sub(r"[^a-z0-9]", "", lang.lower())
    return f".{cleaned}" if cleaned else ".txt"


def _example_output_tail(proc):
    """Collapse a failing validator's output into one message-sized line."""
    text = (proc.stderr or "") or (proc.stdout or "")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return f"exit status {proc.returncode}, no output"
    return " | ".join(lines[-_EXAMPLE_STDERR_TAIL_LINES:])


def _validate_example_block(tok, rel_path, command_template, cwd):
    """Execute one ``validate``-marked block; return an EXAMPLE002 or None.

    The block's raw text is written to a scratch file whose suffix names the
    language, ``{file}`` in *command_template* is replaced with that path,
    and the result runs through the effects chokepoint.  Under ``--dry-run``
    the run is recorded rather than executed, so there is no verdict to
    report and the block yields no lint.
    """
    argv_template = shlex.split(command_template)
    body = "\n".join(tok.lines)
    if not body.endswith("\n"):
        body += "\n"

    with tempfile.TemporaryDirectory(prefix="selfdoc-example-") as scratch:
        snippet = os.path.join(scratch, f"example{_example_suffix(tok.lang)}")
        with open(snippet, "w", encoding="utf-8") as fh:  # effects: exempt -- self-owned scratch snippet, created, read by the validator and deleted inside this call
            fh.write(body)
        argv = [part.replace("{file}", snippet) for part in argv_template]
        try:
            proc = effects.run(
                argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=_EXAMPLE_VALIDATE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return LintResult(
                file=rel_path,
                line=tok.start,
                code="EXAMPLE002",
                message=(
                    f"example validator timed out after"
                    f" {_EXAMPLE_VALIDATE_TIMEOUT}s:"
                    f" {command_template}"
                ),
            )
        except OSError as e:
            return LintResult(
                file=rel_path,
                line=tok.start,
                code="EXAMPLE002",
                message=(
                    f"example validator could not be run"
                    f" ({command_template}): {e}"
                ),
            )
        if effects.unsettled(proc) or proc.returncode == 0:
            return None
        return LintResult(
            file=rel_path,
            line=tok.start,
            code="EXAMPLE002",
            message=(
                f"{tok.lang} example failed validation"
                f" (exit {proc.returncode}): {_example_output_tail(proc)}"
            ),
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
            # Hard-error (exit 1) on unknown or missing required attributes.
            # Distinct from resolution failures below, which are warning-level.
            validate_directive_attrs(
                directive.name, directive.attrs,
                file=display_file, line=file_line,
            )
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
            except SchemaDiscoveryError:
                # Schema discovery ambiguity/absence is a hard error (exit 1),
                # not a warning-level resolution failure -- let it propagate.
                raise
            except Exception as exc:
                directive_results.append(DirectiveResult(
                    file=display_file,
                    line=file_line,
                    directive=directive_str,
                    status="FAILED",
                    error=str(exc),
                ))

    return directive_results, resolved_directives


def _resolve_root_templates(config, base_dir="."):
    """Read root-file templates and return a dict in resolve_all_docs format.

    Each root template listed in ``config["root_files"]`` is read, its
    frontmatter parsed and stripped, and the raw body is kept for directive
    validation.  The returned dict maps the template path (e.g.
    ``"docs/_README.md"``) to the same (frontmatter, resolved, raw, fm_lines)
    tuple that resolve_all_docs produces -- except ``resolved`` is set to
    the raw body (no resolution is performed here; _validate_directives
    does its own resolution).

    Root templates that do not exist on disk are silently skipped (they
    will be caught by gen's own validation at gen time).
    """
    root_files = config.get("root_files", [])
    if not root_files:
        return {}

    result = {}
    for template_path in root_files:
        full_path = os.path.join(base_dir, template_path)
        if not os.path.isfile(full_path):
            continue

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        frontmatter, body = parse_frontmatter(content)
        fm_line_count = len(content.split("\n")) - len(body.split("\n"))
        # resolved is unused by _validate_directives, pass raw body
        result[template_path] = (frontmatter, body, body, fm_line_count)

    return result


def _posts_dir(config, dir_path):
    """Return ``(posts_dir_rel, posts_dir_abs)`` for a project with posts.

    The absolute path is None when the project has no posts directory on
    disk.  One resolution for both post surfaces of the check -- the
    validation hook and the lint slice -- so neither can look somewhere the
    other does not, and both look where the build looks.
    """
    posts_dir_rel = (config.get("posts") or {}).get("dir", ".selfdoc/posts/")
    posts_dir = os.path.join(dir_path, posts_dir_rel)
    if not posts_dir_rel or not os.path.isdir(posts_dir):
        return posts_dir_rel, None
    return posts_dir_rel, posts_dir


def _post_lint_docs(config, dir_path, resolver, valid_names):
    """Resolve the project's published posts into the lint rules' slice.

    A post is a page on the site, so every rule that holds a documentation
    page to a standard holds a post to it too -- but no path used to reach
    them.  ``check`` never injected posts into the docs tree, and the
    build's lint pass runs after the injected files have been removed, so a
    post could carry any defect and both surfaces reported nothing.

    The conversion is not repeated here: ``post_docs_payloads`` is the one
    place a post becomes a docs page (the build's injection and the
    in-memory render path both go through it), and this hands it the same
    published set the build would.  Two things are then corrected, because
    a diagnostic has to name something a reader can open:

    - the key is the post's own path, relative to the project root, not the
      ``blog/<slug>.md`` address the docs tree would hold it at;
    - the frontmatter line count is the SOURCE file's, not the rebuilt
      frontmatter's.  The conversion injects, drops and reorders keys, so
      its line count differs from the file on disk while the body below it
      is byte-identical -- taking the source's count makes every reported
      line the post file's real line.

    Drafts are excluded, matching the build: an unpublished draft is not on
    the site, so the check does not judge it.  The generated listing page
    is excluded too -- it has no source file, so a diagnostic about it
    would name nothing anyone can fix.

    Only ever called on a post set that post validation (POST001-POST007)
    accepted: discovery raises on an invalid post, and the caller reports
    that as its own lint rather than asking this to resolve a set that
    does not exist.

    Returns a dict in ``resolve_all_docs`` shape, empty when the project
    has no posts.
    """
    from selfdoc_core import require_post_provider
    from selfdoc_core.build import post_docs_payloads, POSTS_PREFIX
    from selfdoc_core.docs import resolve_markdown

    posts_dir_rel, posts_dir = _posts_dir(config, dir_path)
    if posts_dir is None:
        return {}

    discover_posts = require_post_provider()
    manifest_path = os.path.join(dir_path, ".selfdoc", "manifest.json")
    published = [
        post
        for post in discover_posts(posts_dir, manifest_path=manifest_path)
        if not post["draft"]
    ]
    if not published:
        return {}

    payloads = post_docs_payloads(published)

    result = {}
    for post in published:
        payload = payloads[f"{POSTS_PREFIX}/{post['slug']}.md"]
        frontmatter, resolved, body, _rebuilt_fm_lines = resolve_markdown(
            payload, resolver, valid_names,
        )

        source_rel = os.path.join(posts_dir_rel.rstrip("/"), post["path"])
        with open(os.path.join(dir_path, source_rel), "r", encoding="utf-8") as f:
            raw = f.read()
        _source_fm, source_body = parse_frontmatter(raw)
        fm_line_count = len(raw.split("\n")) - len(source_body.split("\n"))

        result[source_rel] = (frontmatter, resolved, body, fm_line_count)

    return result


def check_docs(dir_path=".", config=None, dry_run=False, version_filter=None,
               version_override=None):
    """Validate all directives in docs templates and report coverage.

    Scans docs/ for .md templates, parses directives, attempts to resolve
    each one, and computes coverage for Python projects.

    Args:
        dir_path: Project root directory.
        config: Pre-loaded config dict (if None, loads from selfdoc.json).
        dry_run: If True, report staleness without writing hashes to disk.
        version_filter: When set, skip multi-version validation (VER001).
            Used by ``build --version`` to check only a single version.
        version_override: Version that version-bearing generated content is
            expected to embed (VER004), overriding the version detected from
            the project manifest.  Release orchestrators pass the
            about-to-be-released version here, matching the value they pass
            to ``selfdoc gen --version-override``.

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
    custom_names = set(config.get("directives", {}).keys())
    validate_directive_names(custom_names)
    valid_names = ALL_BUILTIN_DIRECTIVES | custom_names

    # Resolve all docs via the shared pipeline (provides frontmatter,
    # resolved content, raw content, and frontmatter line count).
    all_docs = resolve_all_docs(config, base_dir=dir_path)

    # Per-directive validation and coverage tracking.
    dir_results, resolved_directives = _validate_directives(
        all_docs, resolver, valid_names, collect_resolved=True,
    )
    result.directive_results.extend(dir_results)

    # Validate directives in root-file templates (docs/_README.md, etc.).
    # These are skipped by resolve_all_docs (underscore-prefix exclusion)
    # but may contain directives that should be checked.
    root_template_docs = _resolve_root_templates(config, base_dir=dir_path)
    if root_template_docs:
        root_results, _root_resolved = _validate_directives(
            root_template_docs, resolver, valid_names,
        )
        result.directive_results.extend(root_results)

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

    # Post validation (POST001-POST007) -- runs via the post-check hook
    # registered by selfblog (post checks moved to selfblog).  Skipped when
    # no posts directory is configured or present; posts present without a
    # registered hook is a hard error naming selfblog.
    #
    # It runs here, before the lint pass, because the lint slice below is
    # only defined for a post set discovery accepts: an invalid post is
    # reported by this hook, and nothing then asks the slice to resolve a
    # set that does not exist.  The diagnostics are appended in their
    # historical position, after the lint pass.
    post_check_lints = []
    if _posts_dir(config, dir_path)[1] is not None:
        from selfdoc_core import require_post_check_hook

        post_check_lints = list(require_post_check_hook()(config, dir_path))

    # Run lint checks (SEO and other diagnostics).  Posts are pages on the
    # site, so they are merged into the slice the rules run over -- keyed by
    # their own path, with their own line numbers.  They are merged here and
    # not into all_docs above: coverage and the staleness baselines are
    # keyed by docs-tree page, and a post is not one of those.
    post_docs = (
        {} if post_check_lints
        else _post_lint_docs(config, dir_path, resolver, valid_names)
    )
    result.lints = _run_lints(
        {**all_docs, **post_docs}, docs_dir, resolver, config,
        resolved_directives,
    )

    # SEARCH001: the indexer every build runs has to be on this machine.
    # Pagefind is the engine, so the check is unconditional -- a build with
    # no indexer produces a site whose search dialog answers nothing.
    _pagefind_available = False
    for _cmd in (
        [sys.executable, "-m", "pagefind", "--version"],
        ["pagefind", "--version"],
    ):
        try:
            _proc = effects.run(
                _cmd, capture_output=True, text=True, timeout=10,
                read=True,
            )
            if _proc.returncode == 0:
                _pagefind_available = True
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    if not _pagefind_available:
        result.lints.append(LintResult(
            file="selfdoc.json",
            line=None,
            code="SEARCH001",
            message=(
                "pagefind is not installed, so the build cannot index this "
                "site. Install with: uv add 'pagefind[bin]'"
            ),
        ))

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
        if resolved_path is None or not (os.path.isfile(resolved_path) or os.path.isdir(resolved_path)):
            result.lints.append(LintResult(
                file=rd.file,
                line=None,
                code="XREF002",
                message=(
                    f"directive path '{path_arg}' resolves but"
                    f" file does not exist on disk"
                ),
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
            ))

    # CLI001: CLI reference completeness for strictcli projects
    from selfdoc.strictcli_support import read_schema_json, expected_cli_page_filenames
    cli_schema = read_schema_json(dir_path)
    if cli_schema is not None:
        expected_pages = expected_cli_page_filenames(cli_schema)
        docs_dir_path = os.path.join(dir_path, config["docs"].rstrip("/"))

        # Check which expected pages exist
        for page_name in expected_pages:
            page_path = os.path.join(docs_dir_path, page_name)
            if not os.path.isfile(page_path):
                # Determine the command name from the filename
                # cli-index.md -> index, cli-foo.md -> foo
                cmd_name = page_name.replace("cli-", "").replace(".md", "")
                result.lints.append(LintResult(
                    file=page_name,
                    line=None,
                    code="CLI001",
                    message=f"missing CLI page for command '{cmd_name}'",
                ))
            else:
                # Page exists -- check if all flags from schema are documented
                with open(page_path, "r", encoding="utf-8") as f:
                    page_content = f.read()

                # Find the command/group in the schema that corresponds
                cmd_name = page_name.replace("cli-", "").replace(".md", "")
                if cmd_name == "index":
                    continue  # index page doesn't document individual flags

                # Look for the command in top-level commands
                flags = []
                for cmd in cli_schema.get("commands", []):
                    if cmd["name"] == cmd_name:
                        flags = cmd.get("flags", [])
                        break
                else:
                    # Check groups
                    for grp in cli_schema.get("groups", []):
                        if grp["name"] == cmd_name:
                            for subcmd in grp.get("commands", []):
                                flags.extend(subcmd.get("flags", []))
                            break

                for flag in flags:
                    flag_name = f"--{flag['name']}"
                    if flag_name not in page_content:
                        result.lints.append(LintResult(
                            file=page_name,
                            line=None,
                            code="CLI001",
                            message=f"flag '{flag_name}' not documented",
                        ))

        # CLI002: minimum help text length
        _MIN_HELP_LEN = 50

        def _check_help_len(element_kind, element_name, help_text, page_file):
            """Emit CLI002 if help_text is shorter than _MIN_HELP_LEN."""
            if help_text and len(help_text) < _MIN_HELP_LEN:
                result.lints.append(LintResult(
                    file=page_file,
                    line=None,
                    code="CLI002",
                    message=(
                        f"{element_kind} '{element_name}' help text too short "
                        f"({len(help_text)} chars, minimum {_MIN_HELP_LEN})"
                    ),
                ))

        for cmd in cli_schema.get("commands", []):
            cmd_name = cmd["name"]
            page_file = f"cli-{cmd_name}.md"
            _check_help_len("command", cmd_name, cmd.get("help", ""), page_file)
            for fl in cmd.get("flags", []):
                _check_help_len(
                    "flag", f"--{fl['name']}", fl.get("help", ""), page_file,
                )
            for ar in cmd.get("args", []):
                _check_help_len(
                    "arg", ar["name"], ar.get("help", ""), page_file,
                )

        for grp in cli_schema.get("groups", []):
            grp_name = grp["name"]
            page_file = f"cli-{grp_name}.md"
            _check_help_len("group", grp_name, grp.get("help", ""), page_file)
            for subcmd in grp.get("commands", []):
                subcmd_name = subcmd["name"]
                _check_help_len(
                    "command", f"{grp_name} {subcmd_name}",
                    subcmd.get("help", ""), page_file,
                )
                for fl in subcmd.get("flags", []):
                    _check_help_len(
                        "flag", f"--{fl['name']}", fl.get("help", ""), page_file,
                    )
                for ar in subcmd.get("args", []):
                    _check_help_len(
                        "arg", ar["name"], ar.get("help", ""), page_file,
                    )

    # Project-level version consistency checks
    result.lints.extend(_check_version_consistency(config, dir_path))
    result.lints.extend(
        _check_version_match(config, dir_path, version_override=version_override)
    )

    # Description staleness and source docstring drift detection.
    # Uses frontmatter and resolved content from resolve_all_docs instead
    # of re-walking docs/ and re-resolving directives.
    # Prefix hash keys with locale code (matching build.py) so that gen
    # and check use the same key space in hashes.json.

    # Build per-page directive lookup for drift detection.
    _drift_directives: dict[str, list] = {}
    for rd in resolved_directives:
        _drift_directives.setdefault(rd.file, []).append(rd)

    # Build per-CLI-page schema hashes from the per-command schema slices.
    _schema_hashes: dict[str, str] = {}
    if cli_schema is not None:
        for cmd in cli_schema.get("commands", []):
            page_key = f"cli-{cmd['name']}.md"
            _schema_hashes[page_key] = compute_schema_hash(cmd)
        for grp in cli_schema.get("groups", []):
            page_key = f"cli-{grp['name']}.md"
            _schema_hashes[page_key] = compute_schema_hash(grp)

    # STALE001/DRIFT001 exemption keys on the ownership predicate (machine-owned
    # state), not the generated+seeded frontmatter flag.  Machine-owned pages
    # cannot be hand-fixed, so a held baseline would deadlock -- they are exempt
    # and their baselines advance.  Hand-described generated pages get full
    # staleness protection.  Computed in the app layer (no upward import into
    # selfdoc_core) and passed down to update_hashes.
    locales = config.get("locales") or []
    locale_prefix = locales[0]["code"] if locales else ""
    exempt_keys = _machine_owned_keys(
        all_docs, dir_path, cli_schema, locale_prefix,
    )

    if locales:
        locale_code = locale_prefix
        prefixed_docs = {f"{locale_code}/{rp}": val for rp, val in all_docs.items()}
        prefixed_directives = {f"{locale_code}/{rp}": v for rp, v in _drift_directives.items()}
        prefixed_schema = {f"{locale_code}/{rp}": v for rp, v in _schema_hashes.items()}
        stale_warnings, drift_warnings = update_hashes(
            prefixed_docs, dir_path, dry_run=dry_run,
            page_directives=prefixed_directives,
            schema_hashes=prefixed_schema,
            skeleton_pages=exempt_keys,
        )
    else:
        stale_warnings, drift_warnings = update_hashes(
            all_docs, dir_path, dry_run=dry_run,
            page_directives=_drift_directives,
            schema_hashes=_schema_hashes,
            skeleton_pages=exempt_keys,
        )
    for rel_path, stale_msg in stale_warnings:
        result.lints.append(LintResult(
            file=rel_path,
            line=None,
            code="STALE001",
            message=stale_msg,
        ))
    for rel_path, drift_msg in drift_warnings:
        result.lints.append(LintResult(
            file=rel_path,
            line=None,
            code="DRIFT001",
            message=drift_msg,
        ))

    # Post validation results, produced above (before the lint pass) so the
    # post lint slice is only built for a post set discovery accepted.
    result.lints.extend(post_check_lints)

    # Manifest freshness (STALE002)
    result.lints.extend(_check_manifest_freshness(config, dir_path))

    # Emitted-reference resolution (LINK001) over the built tree.  Every
    # address the build emits comes from one function, and this is the
    # assertion that the addresses it produced name files that exist: an
    # internal link, a canonical, a sitemap entry or a feed link that
    # resolves to nothing is a broken site.  A project with no build
    # output has nothing to check.
    from selfdoc_core.resolution import check_output_resolution

    result.lints.extend(check_output_resolution(
        os.path.join(dir_path, config.get("output", "docs/_build/").rstrip("/")),
        base_url=config.get("base_url", ""),
    ))

    # Validate old versions when multi-version is configured.
    # The working-tree check above covers the latest version; here we
    # extract each older version from its git tag and run directive
    # validation and lint on it, prefixing results with the version string.
    # When version_filter is set, skip this entirely -- the caller is
    # building a single version and doesn't need cross-version validation.
    versions = config.get("versions") or []
    if len(versions) > 1 and version_filter is None:
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
                ))
                continue

            # Build a resolver against the extracted content
            ver_resolver = make_resolver(config, cache_dir)
            ver_docs = resolve_all_docs(config, base_dir=cache_dir)

            ver_dir_results, ver_resolved = _validate_directives(
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
                    ver_resolved,
                )
                for lint in ver_lints:
                    # LintResult is frozen: a relabelled diagnostic is a new
                    # one, not the same object with its file rewritten.
                    result.lints.append(dataclasses.replace(
                        lint, file=f"[{ver_str}] {lint.file}",
                    ))

    return result


class AcceptError(RuntimeError):
    """Raised when 'selfdoc baseline accept' cannot accept a named page."""


def compute_staleness_state(dir_path=".", config=None):
    """Compute current page hashes and the pages frozen in an error state.

    Runs the same content/description/source-docstring/schema hashing that
    ``check_docs`` uses for STALE001/DRIFT001 detection, but never writes
    ``.selfdoc/hashes/hashes.json``.

    Returns:
        Tuple ``(current_hashes, stored_hashes, error_pages)`` where:
          - ``current_hashes`` maps each page identifier (locale-prefixed
            when locales are configured, matching hashes.json keys) to its
            full current hash dict.
          - ``stored_hashes`` is the loaded baseline (hashes.json contents).
          - ``error_pages`` maps a page identifier to the lint code of its
            outstanding error: ``"STALE001"`` or ``"DRIFT001"``.
    """
    if config is None:
        config = load_config(dir_path)
    if config is None:
        raise RuntimeError(
            "No selfdoc.json found. Run 'selfdoc init' to initialize."
        )

    docs_dir = os.path.join(dir_path, config["docs"].rstrip("/"))
    if not os.path.isdir(docs_dir):
        raise RuntimeError(f"Docs directory '{config['docs']}' not found.")

    from selfdoc.strictcli_support import read_schema_json

    resolver = make_resolver(config, dir_path)
    custom_names = set(config.get("directives", {}).keys())
    validate_directive_names(custom_names)
    valid_names = ALL_BUILTIN_DIRECTIVES | custom_names

    all_docs = resolve_all_docs(config, base_dir=dir_path)
    _dir_results, resolved_directives = _validate_directives(
        all_docs, resolver, valid_names, collect_resolved=True,
    )

    # Per-page directive lookup for source-docstring drift detection.
    drift_directives: dict[str, list] = {}
    for rd in resolved_directives:
        drift_directives.setdefault(rd.file, []).append(rd)

    # Per-CLI-page schema hashes (mirrors check_docs).
    schema_hashes: dict[str, str] = {}
    cli_schema = read_schema_json(dir_path)
    if cli_schema is not None:
        for cmd in cli_schema.get("commands", []):
            schema_hashes[f"cli-{cmd['name']}.md"] = compute_schema_hash(cmd)
        for grp in cli_schema.get("groups", []):
            schema_hashes[f"cli-{grp['name']}.md"] = compute_schema_hash(grp)

    locales = config.get("locales") or []
    if locales:
        locale_code = locales[0]["code"]
        prefixed_docs = {
            f"{locale_code}/{rp}": v for rp, v in all_docs.items()
        }
        prefixed_directives = {
            f"{locale_code}/{rp}": v for rp, v in drift_directives.items()
        }
        prefixed_schema = {
            f"{locale_code}/{rp}": v for rp, v in schema_hashes.items()
        }
    else:
        prefixed_docs = all_docs
        prefixed_directives = drift_directives
        prefixed_schema = schema_hashes

    # Machine-owned pages are exempt from the staleness/drift hold (see
    # check_docs); build the exempt set from the ownership predicate, prefixed
    # to line up with prefixed_docs.
    locale_prefix = locale_code if locales else ""
    skeleton_pages = _machine_owned_keys(
        all_docs, dir_path, cli_schema, locale_prefix,
    )

    current_hashes = compute_current_hashes(
        prefixed_docs, dir_path,
        page_directives=prefixed_directives,
        schema_hashes=prefixed_schema,
    )
    stale_warnings, drift_warnings = update_hashes(
        prefixed_docs, dir_path, dry_run=True,
        page_directives=prefixed_directives,
        schema_hashes=prefixed_schema,
        skeleton_pages=skeleton_pages,
    )

    error_pages: dict[str, str] = {}
    for rel_path, _msg in stale_warnings:
        error_pages[rel_path] = "STALE001"
    for rel_path, _msg in drift_warnings:
        error_pages.setdefault(rel_path, "DRIFT001")

    stored_hashes = load_hashes(dir_path)
    return current_hashes, stored_hashes, error_pages


def accept_baselines(pages, dir_path=".", config=None):
    """Advance the stored baseline for each named page to its current hashes.

    A deliberate, auditable human action meaning "reviewed: the page content
    changed but the existing frontmatter description is still accurate."
    Each named page must currently be frozen in a STALE001/DRIFT001 error
    state; accepting advances its baseline exactly as if the description had
    been rewritten, so the next ``selfdoc check`` passes for that page.

    Args:
        pages: List of page identifiers exactly as shown in ``selfdoc check``
            output (e.g. ``"en/cli-index.md"``).
        dir_path: Project root directory.
        config: Pre-loaded config dict (loaded from selfdoc.json if None).

    Returns:
        List of ``(page, code)`` tuples for the accepted pages, where code
        is the error that was cleared.

    Raises:
        AcceptError: if any named page does not exist, has no baseline, or
            is not currently stale/drifted. Nothing is written when any
            named page is invalid (all-or-nothing).
    """
    # De-duplicate while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for page in pages:
        if page not in seen:
            seen.add(page)
            ordered.append(page)
    if not ordered:
        raise AcceptError("No page named. Name at least one page to accept.")

    current_hashes, stored_hashes, error_pages = compute_staleness_state(
        dir_path, config,
    )

    errors = []
    for page in ordered:
        if page not in current_hashes:
            errors.append(
                f"'{page}': not a documentation page in this project "
                f"(name it exactly as shown in 'selfdoc check' output, "
                f"e.g. 'en/index.md')"
            )
        elif page not in stored_hashes:
            errors.append(
                f"'{page}': has no baseline yet -- run 'selfdoc gen' or "
                f"'selfdoc check' to record one before accepting"
            )
        elif page not in error_pages:
            errors.append(
                f"'{page}': is not stale or drifted -- nothing to accept"
            )
    if errors:
        raise AcceptError(
            "Cannot accept baseline:\n  " + "\n  ".join(errors)
        )

    accepted = []
    for page in ordered:
        stored_hashes[page] = current_hashes[page]
        accepted.append((page, error_pages[page]))
    save_hashes(stored_hashes, dir_path)
    return accepted


def _check_version_consistency(config, dir_path):
    """Check version consistency between config and project manifest.

    VER002: config["version"] differs from detected project version.
    VER003: versions array last entry doesn't match config["version"].
    """
    from selfdoc.utils import detect_project_version

    results = []

    config_version = config.get("version")

    # VER002: config version vs detected project version
    if config_version:
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
            ))

    return results


def _check_version_match(config, dir_path, version_override=None):
    """Check that version-bearing generated content is not stale (VER004).

    Root files generated from a template that interpolates
    ``var key="project.version"`` carry a RESOLVED version literal on disk.
    Generation runs before the version bump in a release, so without
    ``selfdoc gen --version-override`` those committed files end up one
    release behind -- silently.  This check turns that lag into a hard
    failure by requiring the generated file to embed the expected version.

    The expected version is *version_override* when given (the
    about-to-be-released version, matching what the orchestrator passes to
    ``gen``), otherwise the version detected from the project manifest.
    """
    from selfdoc.utils import detect_project_version

    expected = version_override or detect_project_version(dir_path)
    if not expected:
        return []

    results = []

    for template_path in config.get("root_files", []) or []:
        full_template = os.path.join(dir_path, template_path)
        if not os.path.isfile(full_template):
            # Missing templates are reported by gen, not here.
            continue
        with open(full_template, "r", encoding="utf-8") as f:
            template = f.read()
        if not _has_version_var_directive(template):
            continue

        basename = os.path.basename(template_path)
        if not basename.startswith("_"):
            continue
        output_name = basename[1:]
        output_path = os.path.join(dir_path, output_name)
        if not os.path.isfile(output_path):
            # Not generated yet -- gen's concern, not a version mismatch.
            continue

        with open(output_path, "r", encoding="utf-8") as f:
            generated = f.read()

        if expected not in generated:
            results.append(LintResult(
                file=output_name,
                line=None,
                code="VER004",
                message=(
                    f"Generated root file '{output_name}' embeds the project"
                    f" version from '{template_path}' but does not contain the"
                    f" expected version '{expected}'. Regenerate with"
                    f" 'selfdoc gen --version-override {expected}' so the"
                    f" committed file is not one release behind."
                ),
            ))

    return results


def _has_version_var_directive(template):
    """True when *template* interpolates the project version via a var directive."""
    for directive in parse_directives(template):
        if directive.name == "var" and directive.attrs.get("key") == "project.version":
            return True
    return False


def _check_manifest_freshness(config, dir_path):
    """Check manifest pages/posts against files on disk (STALE002)."""
    from selfdoc.manifest import load_manifest

    manifest_path = os.path.join(dir_path, ".selfdoc", "manifest.json")
    if not os.path.isfile(manifest_path):
        return []

    manifest = load_manifest(manifest_path)
    if manifest is None:
        return []

    docs_dir = os.path.join(dir_path, config.get("docs", "docs/"))
    posts_dir = os.path.join(
        dir_path, (config.get("posts") or {}).get("dir", ".selfdoc/posts/"),
    )

    # Collect pages on disk (exclude underscore-prefixed template files)
    disk_pages = set()
    if os.path.isdir(docs_dir):
        for root, _dirs, files in os.walk(docs_dir):
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                if fname.startswith("_"):
                    continue
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, docs_dir)
                disk_pages.add(rel)

    # Collect posts on disk
    disk_posts = set()
    if os.path.isdir(posts_dir):
        for root, _dirs, files in os.walk(posts_dir):
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, posts_dir)
                disk_posts.add(rel)

    manifest_pages = {p["path"] for p in manifest.pages}
    manifest_posts = {p["path"] for p in manifest.posts}

    results = []

    # Pages on disk but not in manifest
    for path in sorted(disk_pages - manifest_pages):
        results.append(LintResult(
            file=path,
            line=None,
            code="STALE002",
            message="page exists on disk but not in manifest (run 'selfdoc gen' to update)",
        ))

    # Manifest pages not on disk
    for path in sorted(manifest_pages - disk_pages):
        results.append(LintResult(
            file=path,
            line=None,
            code="STALE002",
            message=f"manifest lists page '{path}' but file not found on disk",
        ))

    # Posts on disk but not in manifest
    for path in sorted(disk_posts - manifest_posts):
        results.append(LintResult(
            file=path,
            line=None,
            code="STALE002",
            message="post exists on disk but not in manifest (run 'selfdoc gen' to update)",
        ))

    # Manifest posts not on disk
    for path in sorted(manifest_posts - disk_posts):
        results.append(LintResult(
            file=path,
            line=None,
            code="STALE002",
            message=f"manifest lists post '{path}' but file not found on disk",
        ))

    return results


# Wrapping punctuation and markdown emphasis a prose token can carry.  A
# statistic is recognized from the token's core, not from its decoration:
# ``**42**``, ``(0.36.0)`` and ``1999.`` all reduce to their bare form.
_STAT_TRIM = "`*_~\"'“”‘’()[]{}<>,.;:!?…—–-"

# Version-shaped: either a ``v``-prefixed number of any component count
# (``v2``, ``v1.5``, ``v0.36.0``) or a bare dotted triple (``0.36.0``), each
# optionally followed by pre-release or build metadata
# (``1.0.0-alpha.1``, ``2.11.3+build.7``).  A bare two-component number is
# NOT version-shaped: ``3.5`` is far more often a measurement than a release,
# so it keeps counting as a statistic.
_VERSION_SHAPED = re.compile(
    r"^(?:[vV]\d+(?:\.\d+)*|\d+\.\d+\.\d+)(?:[-+][0-9A-Za-z.]+)?$"
)

# A four-digit standalone number in the calendar range.  ``1899`` and ``2100``
# are outside it and stay statistics; ``2026-08-11`` is not standalone.
_BARE_YEAR = re.compile(r"^\d{4}$")


def counts_as_statistic(word):
    """Return True when a prose token is a concrete numeric data point.

    SEO008 measures how many quantities a page offers a citing model.  A
    digit alone does not make a quantity: release versions and calendar
    years appear in almost every documentation page and say nothing about
    magnitude, count or proportion.  Both are refused here, so a page whose
    only digits are ``0.36.0`` and ``2026`` reads as having no statistics --
    which is the truth.

    Args:
        word: A whitespace-delimited token from prose content, with any
            markdown decoration still attached.

    Returns:
        True for genuine quantities (``42``, ``3.5``, ``87%``, ``12ms``),
        False for tokens carrying no digit, version-shaped tokens and
        bare years.
    """
    if not any(c.isdigit() for c in word):
        return False
    core = word.strip(_STAT_TRIM)
    if not core:
        return False
    if _VERSION_SHAPED.match(core):
        return False
    if _BARE_YEAR.match(core) and 1900 <= int(core) <= 2099:
        return False
    return True


def _authored_data_documents(docs_dir, output_dir):
    """Every authored data document in the docs tree, as absolute paths.

    A page whose whole body is a directive -- the CV, the curated project
    listing -- keeps its prose in a TOML document beside the templates.
    Those documents are where a reader edits, so they are where a
    misspelling in the rendered page is reported.  Found by walking rather
    than asked of the directive, because a directive that reads a fixed
    document (``projects-cards``) declares no attributes at all.

    The build output is skipped: it holds copies of the same documents,
    and reporting a word at its line in a generated copy would send a
    reader to a file the next build overwrites.
    """
    skip = os.path.abspath(output_dir)
    found = []
    for root, _dirs, files in os.walk(docs_dir):
        absolute_root = os.path.abspath(root)
        if absolute_root == skip or absolute_root.startswith(skip + os.sep):
            continue
        for name in sorted(files):
            if name.endswith(".toml"):
                found.append(os.path.join(absolute_root, name))
    return found


def _directive_data_files(page_directives, docs_documents, project_root):
    """Documents the content rendered onto one page could have come out of.

    The documents in the docs tree, plus any existing file a directive on
    the page names in ``path``.  A ``path`` that names a module or a
    directory (``ref``, ``list-tree``) is not a document and contributes
    nothing.  Every entry is absolute, so a document reached both ways is
    held once and never reported twice.
    """
    files = list(docs_documents)
    for rd in page_directives:
        declared = (rd.attrs or {}).get("path", "")
        if not declared:
            continue
        full = os.path.abspath(os.path.join(project_root, declared))
        if full not in files and os.path.isfile(full):
            files.append(full)
    return files


def _locate_word(word, data_files, project_root):
    """Every ``(file, line, column)`` *word* occupies in *data_files*.

    Whole-word matches only, so ``ok`` inside ``token`` is not one.  The
    paths come back relative to the project root, which is how every other
    diagnostic names a file.
    """
    pattern = re.compile(rf"(?<![^\W\d_]){re.escape(word)}(?![^\W\d_])")
    hits = []
    for full in data_files:
        try:
            with open(full, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        rel = os.path.relpath(full, project_root).replace(os.sep, "/")
        for lineno, line in enumerate(text.split("\n"), start=1):
            for match in pattern.finditer(line):
                hits.append((rel, lineno, match.start() + 1))
    return hits


def _spell_rendered_directives(
    rel_path, body_content, resolved, raw_misspellings, page_directives,
    docs_documents, project_root, vocab, accepted,
):
    """SPELL001 over prose a directive rendered out of an authored document.

    A page's own prose is scanned from the raw body, where every reported
    column is a real column in the file.  Prose a directive rendered has no
    position in that file at all -- a marker stands in for it -- so the
    resolved body is scanned instead and each finding is reported against
    the document it was written in, at the word's own line and column
    there.

    A word the resolved body carries but no authored document holds came
    out of source code: a module name, a symbol, a type.  Identifiers are
    not prose, and the file to fix would be code rather than a document,
    so those are not this check's findings.
    """
    if not resolved or resolved == body_content:
        return []
    already = {miss.word for miss in raw_misspellings}
    data_files = _directive_data_files(
        page_directives, docs_documents, project_root,
    )
    if not data_files:
        return []

    results = []
    seen = set()
    for miss in spelling.check_text(
        resolved, file=rel_path, vocab=vocab, accepted=accepted,
    ):
        if miss.word in already or miss.word in seen:
            continue
        seen.add(miss.word)
        for source_file, line, column in _locate_word(
            miss.word, data_files, project_root,
        ):
            suffix = (
                f"; did you mean {', '.join(miss.suggestions)}?"
                if miss.suggestions else ""
            )
            results.append(LintResult(
                file=source_file,
                line=line,
                code="SPELL001",
                message=(
                    f"Unrecognized word '{miss.word}' (col {column})"
                    f"{suffix} -- rendered into {rel_path}"
                ),
            ))
    return results


def _run_lints(all_docs, docs_dir, resolver, config, resolved_directives=None):
    """Run lint checks on documentation templates.

    Args:
        all_docs: Dict from resolve_all_docs mapping rel_path to
            (frontmatter, resolved, raw_content, fm_line_count).
        docs_dir: Absolute path to the docs directory.
        resolver: Directive resolver callable.
        config: Project configuration dict.
        resolved_directives: List of ResolvedDirective objects from
            directive validation, or None.

    Returns a list of LintResult diagnostics covering SEO best practices:
    multiple H1s, heading level gaps, empty alt text, title length,
    missing base_url, and missing description.
    """
    results = []

    # Build per-page directive lookup for downstream lint checks.
    page_directives: dict[str, list] = {}
    for rd in (resolved_directives or []):
        page_directives.setdefault(rd.file, []).append(rd)

    project_root = os.path.dirname(os.path.abspath(docs_dir))
    project_name = os.path.basename(project_root)

    # EXAMPLE002/EXAMPLE003 -- validator command templates keyed by fenced
    # language.  Absent config means the feature is off, which turns every
    # 'validate' marker in the tree into an EXAMPLE003.
    example_commands = config.get("examples") or {}

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

    _known_pages = set(all_docs.keys())

    # SPELL001 -- the vocabulary is loaded once for the whole run, not once
    # per page.  A malformed accept list raises here, before any page is
    # judged, so the run stops on the bad list rather than reporting
    # misspellings a fixed list would have accepted.
    _spell_vocab = spelling.load_wordlist()
    _spell_accepted = spelling.load_accept_list()
    # The authored documents a directive can render prose out of, walked
    # once for the whole run rather than once per page.
    _spell_documents = _authored_data_documents(
        docs_dir,
        os.path.join(project_root, config.get("output", "docs/_build/")),
    )

    # DQ001 helpers -- strip common suffixes and normalize for comparison
    _DQ_SUFFIXES = {
        "module", "class", "function", "package",
        "type", "interface", "method",
    }

    def _normalize_dq(text):
        t = text.lower().strip()
        t = t.replace("_", " ").replace("-", " ")
        t = re.sub(r'[^a-z0-9\s]', '', t)
        words = t.split()
        words = [w for w in words if w not in _DQ_SUFFIXES]
        return " ".join(words)

    for rel_path in sorted(all_docs):
        metadata, _resolved, body_content, fm_offset = all_docs[rel_path]
        tokens = tokenize(body_content)

        # Collect heading tokens for reuse across checks
        heading_tokens = [t for t in tokens if isinstance(t, Heading)]
        h1_tokens = [t for t in heading_tokens if t.level == 1]

        # Token types that carry prose content (not code blocks).  Owned by
        # the tokenizer, which also knows how to read each shape's text --
        # headings and table cells included.
        _TEXT_TYPES = TEXT_BEARING

        # SEO001 -- Multiple H1 headings in Markdown source
        # SEO013 -- No title source (neither frontmatter title nor # heading)
        h1_count = len(h1_tokens)
        if h1_count > 1:
            results.append(LintResult(
                file=rel_path,
                line=None,
                code="SEO001",
                message=f"Multiple H1 headings ({h1_count} found); use a single '# ' heading per page",
            ))
        has_frontmatter_title = bool(metadata.get("title"))
        if h1_count == 0 and not has_frontmatter_title:
            results.append(LintResult(
                file=rel_path,
                line=None,
                code="SEO013",
                message="No title source: add a '# Heading' or set 'title:' in frontmatter",
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
                ))
            prev_level = level

        # SEO003 -- Empty alt text (only in text-bearing tokens)
        for tok in tokens:
            if not isinstance(tok, _TEXT_TYPES):
                continue
            # Get text lines from the token
            tok_lines = token_text_lines(tok)
            for offset, line in enumerate(tok_lines):
                if "![](" in line:
                    results.append(LintResult(
                        file=rel_path,
                        line=tok.start + offset + fm_offset,
                        code="SEO003",
                        message="Image with empty alt text",
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
                    ))

        # SEO006 -- Missing description
        if "description" not in metadata:
            results.append(LintResult(
                file=rel_path,
                line=None,
                code="SEO006",
                message="No 'description' in frontmatter",
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
                ))
            effective_desc = str(fm_description)
        else:
            # Auto-extract from first Paragraph token (skipping
            # initial Heading, BlankLine, CodeBlock tokens). The effective
            # description is the complete first sentence of the whole
            # paragraph (soft-wrapped lines joined) -- the same unit the
            # build emits into the meta tag -- not just the first physical
            # line. No character cap here; SEO009/010 remain advisory.
            effective_desc = ""
            for tok in tokens:
                if isinstance(tok, (Heading, BlankLine, CodeBlock)):
                    continue
                if isinstance(tok, Paragraph):
                    effective_desc = first_sentence("\n".join(tok.lines))
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
            ))

        # SEO007 -- Paragraph length after headings.
        # One threshold set applies to every page type: a generated page's
        # lead-in is held to the same band as a hand-written one.  The only
        # suppressions are structural (a directive supplies the content the
        # paragraph would otherwise carry), applied below.
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
                        f" {word_count} words (aim for 30-80 for AI citation)"
                    ),
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
                1 for w in prose_words if counts_as_statistic(w)
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
                        ))
                last_heading_info = (tok.start, level)
            elif not isinstance(tok, (BlankLine, Heading)):
                # Non-blank, non-heading token resets tracking
                last_heading_info = None

        # SEO014 -- Meaningless alt text (only in text-bearing tokens)
        for tok in tokens:
            if not isinstance(tok, _TEXT_TYPES):
                continue
            tok_lines = token_text_lines(tok)
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
                        ))

        # SEO015 -- Generic anchor text (only in text-bearing tokens)
        for tok in tokens:
            if not isinstance(tok, _TEXT_TYPES):
                continue
            tok_lines = token_text_lines(tok)
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
                        ))

        # XREF001 -- Broken internal page links
        # Scan for markdown links to .md files and verify they exist.
        for tok in tokens:
            if not isinstance(tok, _TEXT_TYPES):
                continue
            tok_lines = token_text_lines(tok)
            for offset, line in enumerate(tok_lines):
                for m in re.finditer(r'\[([^\]]*)\]\(([^)]+)\)', line):
                    target = m.group(2)
                    # Skip external links, anchors, and non-.md links
                    if target.startswith(('http://', 'https://', '#', 'mailto:')):
                        continue
                    # Strip anchor fragment
                    target = target.split('#')[0]
                    if not target.endswith('.md'):
                        continue
                    # Resolve relative paths
                    if not target.startswith('/'):
                        page_dir = os.path.dirname(rel_path)
                        target = os.path.normpath(os.path.join(page_dir, target))
                    else:
                        target = target.lstrip('/')
                    # Normalize path separators
                    target = target.replace('\\', '/')
                    if target not in _known_pages:
                        results.append(LintResult(
                            file=rel_path,
                            line=tok.start + offset + fm_offset,
                            code="XREF001",
                            message=f"link to '{target}' resolves to unknown page",
                        ))

        # DQ001 -- Description restates the symbol/page name
        fm_desc = metadata.get("description", "")
        if fm_desc:
            page_title = metadata.get("title")
            if not page_title and h1_tokens:
                page_title = h1_tokens[0].text
            if not page_title:
                page_title = os.path.splitext(os.path.basename(rel_path))[0]
                page_title = page_title.replace("_", " ").replace("-", " ")

            norm_desc = _normalize_dq(fm_desc)
            norm_title = _normalize_dq(page_title)

            if norm_desc and norm_title:
                is_restated = norm_desc == norm_title
                # Substring check: only when the shorter side is at
                # least 50% of the longer, so a 2-word title like
                # "selfdoc build" inside a 20-word description is not
                # considered a restatement.
                if not is_restated:
                    shorter = min(norm_desc, norm_title, key=len)
                    longer = max(norm_desc, norm_title, key=len)
                    if len(shorter.split()) >= 2 and len(shorter) >= len(longer) * 0.5:
                        is_restated = (
                            norm_desc in norm_title
                            or norm_title in norm_desc
                        )
                if not is_restated:
                    # Token overlap check
                    desc_words = set(norm_desc.split())
                    title_words = set(norm_title.split())
                    if desc_words and title_words:
                        overlap = len(desc_words & title_words)
                        max_len = max(len(desc_words), len(title_words))
                        if overlap / max_len > 0.8:
                            is_restated = True

                if is_restated:
                    results.append(LintResult(
                        file=rel_path,
                        line=None,
                        code="DQ001",
                        message="description restates the symbol name",
                    ))

        # DQ002 -- Description too short
        fm_desc_raw = metadata.get("description")
        if fm_desc_raw is not None and len(str(fm_desc_raw)) < 20:
            results.append(LintResult(
                file=rel_path,
                line=None,
                code="DQ002",
                message=(
                    f"description too short ({len(str(fm_desc_raw))} chars,"
                    f" minimum 20)"
                ),
            ))

        # DQ003 -- Function-referencing pages need substantive descriptions
        # If a page contains ref directives and has a short description,
        # it likely needs more detail about the function's purpose.
        if fm_desc_raw is not None:
            has_ref_directive = bool(re.search(r':-:\s*ref\s', body_content))
            if has_ref_directive and len(str(fm_desc_raw)) < 30:
                results.append(LintResult(
                    file=rel_path,
                    line=None,
                    code="DQ003",
                    message=(
                        f"page with ref directive has short description"
                        f" ({len(str(fm_desc_raw))} chars, minimum 30"
                        f" for API reference pages)"
                    ),
                ))

        # EXAMPLE001 -- code block syntax validation
        # EXAMPLE002/EXAMPLE003 -- opt-in semantic validation ('validate')
        for tok in tokens:
            if not isinstance(tok, CodeBlock):
                continue

            # Semantic tier: opted into per block, never inferred.  A block
            # the tier owns is not also parsed below -- the validator's own
            # diagnostic supersedes a second-hand syntax message.  A marker
            # with no configured command owns nothing, so EXAMPLE003 is
            # raised and the block falls through to the syntax tier.
            if tok.validate:
                command_template = example_commands.get(tok.lang)
                if command_template is not None:
                    lint = _validate_example_block(
                        tok, rel_path, command_template, project_root,
                    )
                    if lint is not None:
                        results.append(lint)
                    continue
                results.append(LintResult(
                    file=rel_path,
                    line=tok.start,
                    code="EXAMPLE003",
                    message=(
                        f"code block marked 'validate' but no validator is"
                        f" configured for language '{tok.lang}': add"
                        f" \"examples\": {{\"{tok.lang}\": \"<command>"
                        f" {{file}}\"}} to selfdoc.json, or drop the marker"
                    ),
                ))

            # Python code blocks
            if tok.lang in ("python", "py", "python3"):
                if len(tok.lines) < 3:
                    continue
                if any(
                    marker in line
                    for line in tok.lines
                    for marker in _DIRECTIVE_MARKERS
                ):
                    continue
                try:
                    ast.parse("\n".join(tok.lines))
                except SyntaxError as e:
                    if isinstance(e, IndentationError):
                        continue
                    lineno = e.lineno if e.lineno is not None else 0
                    results.append(LintResult(
                        file=rel_path,
                        line=tok.start + lineno,
                        code="EXAMPLE001",
                        message=f"Python syntax error in code block: {e.msg}",
                    ))
            # JSON code blocks
            elif tok.lang == "json":
                if len(tok.lines) < 1:
                    continue
                if any(
                    marker in line
                    for line in tok.lines
                    for marker in _DIRECTIVE_MARKERS
                ):
                    continue
                try:
                    json.loads("\n".join(tok.lines))
                except json.JSONDecodeError as e:
                    results.append(LintResult(
                        file=rel_path,
                        line=tok.start + e.lineno,
                        code="EXAMPLE001",
                        message=f"JSON syntax error in code block: {e.msg}",
                    ))

        # SPELL001 -- prose spelling.  One engine, shared with
        # ``selfdoc spell-corpus``: this surface only turns its findings
        # into lints.  Posts are in ``all_docs`` by the time the rules run,
        # so they are checked on the same terms as documentation pages.
        raw_misspellings = spelling.check_text(
            body_content,
            file=rel_path,
            vocab=_spell_vocab,
            accepted=_spell_accepted,
            line_offset=fm_offset,
        )
        for miss in raw_misspellings:
            results.append(LintResult(
                file=rel_path,
                line=miss.line,
                code="SPELL001",
                message=miss.describe(),
            ))

        # SPELL001 over what a directive rendered.  The raw body carries a
        # marker where the reader sees text, so prose that came out of a
        # data file -- a CV declared in TOML, a curated listing's blurbs --
        # was never scanned at all and shipped its typos.  The resolved
        # body is scanned too, and anything the raw scan already reported
        # is dropped so a page's own prose is never reported twice.
        results.extend(_spell_rendered_directives(
            rel_path,
            body_content,
            _resolved,
            raw_misspellings,
            page_directives.get(rel_path, ()),
            _spell_documents,
            project_root,
            _spell_vocab,
            _spell_accepted,
        ))

    # SEO012 -- WCAG contrast ratio checks
    _check_contrast(results, config, docs_dir)

    # PARAM001 -- parameter documentation completeness
    # RETURN001 -- return type documentation
    base_dir = os.path.dirname(os.path.abspath(docs_dir))
    for rd in (resolved_directives or []):
        if rd.name != "ref" or rd.source_entry is None:
            continue
        target = rd.attrs.get("target", "")
        if not target:
            continue
        resolved_path = rd.source_entry.extractor.resolve_path(
            rd.attrs.get("path", ""), [rd.source_entry.path], base_dir,
        )
        if resolved_path is None:
            continue
        details = rd.source_entry.extractor.symbol_details(
            resolved_path, target,
        )
        if details is None:
            continue
        for param in details["params"]:
            if not param["documented"]:
                results.append(LintResult(
                    file=rd.file,
                    line=None,
                    code="PARAM001",
                    message=f"parameter '{param['name']}' not documented",
                ))
        # RETURN001 -- return type documentation
        return_type = details["return_type"]
        if (
            return_type is not None
            and return_type not in ("None", "NoneType")
            and not details["return_documented"]
        ):
            results.append(LintResult(
                file=rd.file,
                line=None,
                code="RETURN001",
                message=f"return type '{return_type}' not documented",
            ))

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


def theme_css_path(theme_name):
    """Return the path of the stylesheet the build emits for *theme_name*.

    Resolved through the theme registry rather than built from this
    module's own directory: the themes live in ``selfdoc_core`` and the
    ``selfdoc.themes`` shim points at them, so this is the one file the
    build reads and therefore the one the contrast lint must measure.
    """
    import selfdoc_core.themes as core_themes

    return os.path.join(
        os.path.dirname(core_themes.__file__), f"{theme_name}.css",
    )


def _check_contrast(lints, config, base_dir):
    """Check WCAG 2.1 contrast ratios for theme colors (SEO012).

    Parses the theme CSS for custom properties and verifies critical
    foreground/background pairs meet minimum contrast ratios.
    """
    theme_name = config.get("theme", "minimal")

    css_path = theme_css_path(theme_name)
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
            ))


def _is_skeleton_page(frontmatter):
    """Return True if the page is a skeleton auto-generated page.

    A page is "skeleton" when it has ``generated: true`` AND
    ``seeded: true`` (indicating the description was auto-generated
    and hasn't been hand-edited).  A generated page whose description
    has been customized (seeded removed) counts as documented.
    """
    if frontmatter.get("generated") is not True:
        return False
    return frontmatter.get("seeded") is True


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
                        # Also check the containing package path, mirroring
                        # gen: package-level patterns (e.g. "internal/vendored")
                        # never match the per-file module path, which for Go
                        # carries the file stem.
                        pkg_path = os.path.dirname(rel_to_base).replace(
                            os.sep, "/",
                        )
                        if pkg_path and pkg_path != "." and _is_excluded(
                            pkg_path, gen_excludes,
                        ):
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
                        if symbol_heading_pattern(sym).search(rd.content):
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
                        if symbol_heading_pattern(sym).search(rd.content):
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
                            if symbol_heading_pattern(sym).search(rd.content):
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


def check_result_exit_code(result, config=None):
    """Compute the process exit code for a whole CheckResult.

    Thin adapter over :func:`selfdoc_core.lints.check_exit_code` -- the one
    implementation of the verdict rules -- for callers holding a full
    CheckResult.  Reduced entry points (the post-build lint pass, the
    posts-only check) call the core function directly with just their lints.

    Args:
        result: CheckResult to inspect (lints already filtered).
        config: Project configuration, read for ``coverage_threshold``.

    Returns:
        1 if any directive failed, any lint is an error, or documented
        coverage is below the configured threshold; 0 otherwise.
    """
    return check_exit_code(
        result.lints,
        directive_results=result.directive_results,
        coverage=result.coverage,
        config=config,
    )


def serialize_check_result(result, exit_code):
    """Build the JSON payload emitted by ``selfdoc check --format json``.

    This is the single definition of the machine-readable check contract:
    the CLI and its tests both call it, so the schema in
    ``schemas/check-output.schema.json`` has exactly one producer to stay
    in sync with.

    Args:
        result: CheckResult to serialize (lints already filtered).
        exit_code: Exit code the run will terminate with, from
            check_exit_code().

    Returns:
        JSON-serializable dict conforming to check-output.schema.json.
    """
    output = {
        "directives": [
            {
                "file": dr.file,
                "line": dr.line,
                "directive": dr.directive,
                "status": dr.status,
                "error": dr.error,
            }
            for dr in result.directive_results
        ],
        "coverage": None,
        "lints": [
            {
                "file": lint.file,
                "line": lint.line,
                "code": lint.code,
                "message": lint.message,
                "severity": lint.severity,
            }
            for lint in result.lints
        ],
        "exit_code": exit_code,
    }
    if result.coverage is not None:
        cov = result.coverage
        output["coverage"] = {
            "total_public": cov.total_public,
            "referenced": cov.referenced,
            "documented": cov.documented,
            "referenced_symbols": cov.referenced_symbols,
            "documented_symbols": cov.documented_symbols,
            "unreferenced_symbols": cov.unreferenced_symbols,
        }
    return output


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

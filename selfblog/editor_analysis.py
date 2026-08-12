"""What the editor can say about a buffer that was never saved.

Two lanes, both answered from the machinery the check already owns rather
than from a second opinion written for the editor:

* **spelling** -- :mod:`selfdoc_core.spelling`, the same engine
  ``selfdoc check`` runs (SPELL001) and ``selfdoc spell-corpus`` runs over
  the fleet: the same masks, the same vendored word list, the same
  machine-local accept list.  Its coordinates are line and column, because
  that is what a diagnostic in a terminal needs; the editor's decoration
  interface takes flat character offsets over the buffer, so the one thing
  this module adds is that mapping.
* **lints** -- ``selfdoc.check.lint_post_buffer``, which overlays the
  buffer on the saved post set and runs the project's real lint rules over
  the result.  No rule is restated here, so a mark on screen is a finding
  ``selfdoc check`` will report, worded identically.

Two deliberate decisions about what comes back:

* **Drafts are judged.**  The build excludes a draft because it is not on
  the site; the editor includes it because a draft is what is being
  written, and a defect found after publishing is found too late.
* **SPELL001 is dropped from the lint lane.**  It is the same engine's
  finding, and the spelling lane already carries it with the exact column
  the editor needs.  Reporting it in both lanes would put one misspelling
  in two places -- an inline mark and a gutter marker -- for no added
  information.

A buffer that is not a valid post does not lose its diagnostics: the post
parser's refusal is reported as the POST00x lint the check reports it as,
through the same mapping (:func:`selfblog.check.post_error_lint`).
"""

from __future__ import annotations

from selfblog.editor_server import EditorError, repo_config, require_local
from selfdoc_core import spelling
from selfdoc_core.utils import parse_frontmatter

#: The lint code the spelling lane owns.  Dropped from the lint lane so one
#: misspelling is one finding.
_SPELLING_CODE = "SPELL001"


class AnalysisUnavailable(EditorError):
    """The lint rules cannot run here, and the message says what is missing."""

    status = 501


def _line_starts(text):
    """Offset of the first character of every line (line N is index N-1)."""
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return starts


def spelling_findings(content, file="buffer.md"):
    """Every unrecognized word in *content*, as editor decoration spans.

    Args:
        content: The buffer, frontmatter included.
        file: The name the engine puts on each diagnostic.

    Returns:
        A list of dicts carrying both coordinate systems -- ``line`` and
        ``column`` (1-based, what a diagnostic reads like) and ``from`` /
        ``to`` (half-open character offsets over the whole buffer, what
        the editor's ``setDecorations`` takes).

    Raises:
        RuntimeError: When a reported word is not at the offset the
            mapping computes.  That is a defect in this mapping or in the
            engine's columns, and painting a mark over the wrong word is
            worse than saying so.
    """
    _frontmatter, body = parse_frontmatter(content)
    fm_lines = len(content.split("\n")) - len(body.split("\n"))

    starts = _line_starts(content)
    findings = []
    for miss in spelling.check_text(body, file=file, line_offset=fm_lines):
        if miss.line < 1 or miss.line > len(starts):
            raise RuntimeError(
                f"spelling reported line {miss.line} in a buffer of "
                f"{len(starts)} line(s)"
            )
        start = starts[miss.line - 1] + miss.column - 1
        end = start + len(miss.word)
        if content[start:end] != miss.word:
            raise RuntimeError(
                f"spelling offset {start}..{end} holds "
                f"{content[start:end]!r}, not {miss.word!r} -- the "
                f"line/column to offset mapping is wrong"
            )
        findings.append({
            "from": start,
            "to": end,
            "line": miss.line,
            "column": miss.column,
            "word": miss.word,
            "suggestions": list(miss.suggestions),
            "message": miss.describe(),
        })
    return findings


def lint_findings(entry, rel, content, config=None):
    """Every lint the project's rules report for this buffer.

    Args:
        entry: The local registry entry the post belongs to.
        rel: The post's path relative to the posts directory.
        content: The buffer, frontmatter included.
        config: Pre-loaded project config, or None to load it.

    Returns:
        A list of dicts with ``code``, ``severity``, ``line`` (None for a
        page-level finding) and ``message``.

    Raises:
        AnalysisUnavailable: The selfdoc package is not installed, so the
            lint rules are not on this machine.
    """
    from selfblog.check import post_error_lint
    from selfblog.posts import PostError

    try:
        from selfdoc.check import lint_post_buffer
    except ImportError as exc:
        raise AnalysisUnavailable(
            "The editor's lint marks come from selfdoc's lint rules and the "
            "selfdoc package is not installed in this environment. Install "
            "it with: pip install selfdoc"
        ) from exc

    require_local(entry)
    config = config if config is not None else repo_config(entry)
    posts_dir_rel = (config.get("posts") or {}).get("dir", ".selfdoc/posts/")

    try:
        lints = lint_post_buffer(entry.path, rel, content, config=config)
    except PostError as exc:
        lints = [post_error_lint(exc, posts_dir_rel)]

    return [
        {
            "code": lint.code,
            "severity": lint.severity,
            "line": lint.line,
            "message": lint.message,
        }
        for lint in lints
        if lint.code != _SPELLING_CODE
    ]


def analyze_buffer(entry, rel, content, config=None):
    """Both lanes for one buffer, in the shape the shell renders.

    Args:
        entry: The local registry entry the post belongs to.
        rel: The post's path relative to the posts directory.
        content: The buffer, frontmatter included.
        config: Pre-loaded project config, or None to load it.

    Returns:
        ``{"spelling": [...], "lints": [...]}``.
    """
    require_local(entry)
    config = config if config is not None else repo_config(entry)
    return {
        "spelling": spelling_findings(content, file=rel),
        "lints": lint_findings(entry, rel, content, config=config),
    }

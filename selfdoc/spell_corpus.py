"""The corpus-wide spelling run: the same engine, every sibling project.

``selfdoc check`` spell-checks the project it is run in.  This runs the
identical engine (``selfdoc_core.spelling``) over every selfdoc project that
lives beside it, which is how the shared accept list gets populated: one
sweep surfaces the technical vocabulary the whole fleet uses, and the terms
that are genuine get added once, for everyone.

Strictly read-only over the projects it visits.  Directives are not
resolved -- resolution runs a project's extractors over its source, and a
survey has no business doing that in someone else's repository -- so what
is scanned is the raw Markdown body of every docs template and every post.
Posts are read straight off disk rather than through selfblog's discovery,
which means drafts are surveyed too: a draft's prose is still prose, and a
term it introduces belongs on the accept list before the draft ships.  A
project whose config cannot be loaded is reported and skipped, never fatal.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field

from selfdoc_core import spelling
from selfdoc_core.fleet import discover_fleet, load_docs_bodies


@dataclass
class ProjectSpellReport:
    """What the sweep found in one project."""

    name: str
    path: str
    pages: int = 0
    misspellings: list[spelling.Misspelling] = field(default_factory=list)
    error: str | None = None

    @property
    def unique_words(self) -> list[tuple[str, int]]:
        """Unknown words with their occurrence counts, commonest first."""
        counts = Counter(m.word for m in self.misspellings)
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))


def scan_project(project, vocab, accepted) -> ProjectSpellReport:
    """Spell-check one project's docs tree and its posts.

    Args:
        project: A :class:`selfdoc_core.fleet.FleetProject`.
        vocab: The word list to accept against.
        accepted: The accept list.

    Returns:
        A report; ``error`` is set instead of results when the project could
        not be read.
    """
    if not project.loaded:
        return ProjectSpellReport(
            name=project.name, path=project.path, error=project.error,
        )

    docs_dir = os.path.join(
        project.path, (project.config.get("docs") or "docs/").rstrip("/"),
    )
    if not os.path.isdir(docs_dir):
        return ProjectSpellReport(
            name=project.name, path=project.path,
            error=f"docs directory not found: {docs_dir}",
        )

    posts_rel = (project.config.get("posts") or {}).get(
        "dir", ".selfdoc/posts/",
    )
    posts_dir = os.path.join(project.path, posts_rel) if posts_rel else ""

    try:
        bodies = load_docs_bodies(docs_dir)
        posts = load_docs_bodies(posts_dir) if posts_dir else {}
    except OSError as exc:
        return ProjectSpellReport(
            name=project.name, path=project.path,
            error=f"{type(exc).__name__}: {exc}",
        )

    # Posts are keyed by their own path from the project root, matching what
    # ``selfdoc check`` reports, so a finding names a file a reader can open.
    slice_ = dict(bodies)
    for rel_path, payload in posts.items():
        slice_[os.path.join(posts_rel.rstrip("/"), rel_path)] = payload

    report = ProjectSpellReport(
        name=project.name, path=project.path, pages=len(slice_),
    )
    for rel_path in sorted(slice_):
        _metadata, _resolved, body, fm_offset = slice_[rel_path]
        report.misspellings.extend(spelling.check_text(
            body,
            file=rel_path,
            vocab=vocab,
            accepted=accepted,
            line_offset=fm_offset,
        ))
    return report


def run_spell_corpus(root) -> tuple[dict, int]:
    """Sweep every selfdoc project under *root* and return what it found.

    Args:
        root: Directory whose immediate subdirectories are searched for
            ``selfdoc.json``.

    Returns:
        ``(document, exit_code)``.  The document is the sweep's machine
        payload, declared by ``selfdoc/payload_schemas.py`` and rendered for
        humans by :func:`render_corpus_text`; it is the one computation
        behind both renderings.  The exit code is 1 when any unknown word
        was found (a misspelling is an error, and the accept list is the
        sanctioned answer for a genuine term), 0 on a clean sweep.  A
        project that could not be read is reported but does not by itself
        fail the sweep.
    """
    vocab = spelling.load_wordlist()
    accepted = spelling.load_accept_list()

    reports = [
        scan_project(project, vocab, accepted)
        for project in discover_fleet(root)
    ]

    total = sum(len(r.misspellings) for r in reports)

    document = {
        "root": os.path.abspath(root),
        "accept_list": str(spelling.ACCEPT_LIST_PATH),
        "accepted_terms": len(accepted),
        "wordlist_words": len(vocab),
        "projects": [
            {
                "project": r.name,
                "pages": r.pages,
                "error": r.error,
                "misspellings": [
                    {
                        "file": m.file,
                        "line": m.line,
                        "column": m.column,
                        "word": m.word,
                        "suggestions": list(m.suggestions),
                    }
                    for m in r.misspellings
                ],
            }
            for r in reports
        ],
        "total": total,
    }
    return document, (1 if total else 0)


def _unique_words(misspellings) -> list[tuple[str, int]]:
    """Unknown words with their occurrence counts, commonest first."""
    counts = Counter(m["word"] for m in misspellings)
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))


def render_corpus_text(document, detail=True) -> str:
    """Render a :func:`run_spell_corpus` document as the human report.

    The summary table plus, when *detail*, each project's unknown words with
    a first location and any suggestion.  Reads the same document the
    machine payload carries, so the two renderings can never disagree.
    """
    lines = [
        f"Word list: {document['wordlist_words']} words. "
        f"Accept list: {document['accepted_terms']} terms "
        f"({document['accept_list']}).",
        "",
        f"{'project':28} {'pages':>5} {'flagged':>8} {'unique':>7}",
    ]
    for project in document["projects"]:
        name = project["project"]
        if project["error"]:
            lines.append(
                f"{name:28} {'-':>5} {'-':>8} {'-':>7}  {project['error']}"
            )
            continue
        unique = _unique_words(project["misspellings"])
        lines.append(
            f"{name:28} {project['pages']:5} "
            f"{len(project['misspellings']):8} {len(unique):7}"
        )
    lines.append("")
    lines.append(f"total flagged: {document['total']}")

    if detail:
        for project in document["projects"]:
            misspellings = project["misspellings"]
            if not misspellings:
                continue
            lines.append("")
            lines.append(f"{project['project']}:")
            first: dict[str, dict] = {}
            for m in misspellings:
                first.setdefault(m["word"], m)
            for word, count in _unique_words(misspellings):
                m = first[word]
                where = f"{m['file']}:{m['line']}:{m['column']}"
                hint = (
                    f"  -> {', '.join(m['suggestions'])}"
                    if m["suggestions"] else ""
                )
                lines.append(f"  {word:24} x{count:<4} {where}{hint}")

    return "\n".join(lines)

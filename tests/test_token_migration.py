"""Tests for Phase 2: tokenizer migration of check.py and html.py.

Verifies that code-block content no longer triggers false positives in
SEO lint checks or HTML generation. Each test places a pattern that
would previously cause a false positive inside a fenced code block and
asserts that the relevant check ignores it.
"""

import json
import os
import re

import pytest

from selfdoc.check import _run_lints
from selfdoc.docs import parse_frontmatter as _parse_frontmatter
from selfdoc.html import generate_html, _extract_title
from conftest import TEST_AUTHOR


def _build_all_docs(docs_dir):
    """Build an all_docs dict from docs_dir for lint tests."""
    all_docs = {}
    for root, _dirs, files in os.walk(docs_dir):
        for fname in sorted(files):
            if fname.endswith(".md") and not fname.startswith("_"):
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, docs_dir)
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                metadata, body = _parse_frontmatter(content)
                fm_line_count = len(content.split("\n")) - len(body.split("\n"))
                all_docs[rel_path] = (metadata, "", body, fm_line_count)
    return all_docs


@pytest.fixture()
def lint_project(tmp_path):
    """Create a minimal project with docs dir and config for lint testing."""
    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
        "author": {"name": "Test Author", "url": "https://author.example"},
        "search_engine": "pagefind",
    }
    return tmp_path, docs_dir, config


# -- SEO001: code block H1 should not count --


def test_seo001_h1_in_code_block_ignored(lint_project):
    """SEO001: '# comment' inside a fenced code block does NOT trigger."""
    _, docs_dir, config = lint_project

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n"
            "Some content here.\n\n"
            "```python\n"
            "# This is a comment, not an H1\n"
            "```\n"
        )

    results = _run_lints(_build_all_docs(docs_dir), docs_dir, None, config)
    seo001 = [r for r in results if r.code == "SEO001"]

    assert len(seo001) == 0


def test_seo001_multiple_h1_in_code_block_ignored(lint_project):
    """SEO001: multiple '# comment' lines in code block are not counted."""
    _, docs_dir, config = lint_project

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n"
            "Some content.\n\n"
            "```bash\n"
            "# install dependencies\n"
            "# set up environment\n"
            "# run server\n"
            "```\n"
        )

    results = _run_lints(_build_all_docs(docs_dir), docs_dir, None, config)
    seo001 = [r for r in results if r.code == "SEO001"]

    assert len(seo001) == 0


# -- generate_html: code block H1 should not trigger build error --


def test_generate_html_h1_in_code_block_ignored():
    """H1 inside a code block does NOT trigger the 'multiple H1' build error."""
    # Should not raise -- code block H1 is not a real H1
    html_files = generate_html(
        {"index.md": (
            "# Real Title\n\n"
            "Some text.\n\n"
            "```bash\n"
            "# This is a shell comment\n"
            "```\n"
        )},
        project_name="TestProject",
        author=TEST_AUTHOR,
    )
    assert "index.html" in html_files


def test_generate_html_only_code_block_h1_no_title():
    """When only H1s appear inside code blocks, generate_html treats
    the page as having no H1 and requires a frontmatter title."""
    with pytest.raises(RuntimeError, match="no title source"):
        generate_html(
            {"index.md": (
                "```bash\n"
                "# comment\n"
                "```\n"
            )},
            project_name="TestProject",
            author=TEST_AUTHOR,
        )


# -- _extract_title: code block H1 skipped --


def test_extract_title_skips_code_block_h1():
    """_extract_title ignores H1 headings inside code blocks."""
    md = (
        "```bash\n"
        "# Not the title\n"
        "```\n\n"
        "# Real Title\n\n"
        "Content.\n"
    )
    assert _extract_title(md, "fallback") == "Real Title"


def test_extract_title_only_code_block_h1_returns_fallback():
    """_extract_title returns fallback when the only H1 is in a code block."""
    md = (
        "```python\n"
        "# Just a comment\n"
        "```\n\n"
        "Some paragraph.\n"
    )
    assert _extract_title(md, "fallback") == "fallback"


# -- SEO003: empty alt text in code blocks --


def test_seo003_empty_alt_in_code_block_ignored(lint_project):
    """SEO003: '![](x.png)' inside a fenced code block does NOT trigger."""
    _, docs_dir, config = lint_project

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n"
            "Some content.\n\n"
            "```markdown\n"
            "![](example.png)\n"
            "```\n"
        )

    results = _run_lints(_build_all_docs(docs_dir), docs_dir, None, config)
    seo003 = [r for r in results if r.code == "SEO003"]

    assert len(seo003) == 0


def test_seo003_empty_alt_outside_code_block_still_triggers(lint_project):
    """SEO003: empty alt text outside a code block still triggers."""
    _, docs_dir, config = lint_project

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n"
            "![](real-image.png)\n\n"
            "```markdown\n"
            "![](code-example.png)\n"
            "```\n"
        )

    results = _run_lints(_build_all_docs(docs_dir), docs_dir, None, config)
    seo003 = [r for r in results if r.code == "SEO003"]

    assert len(seo003) == 1


# -- SEO002: heading gaps in code blocks --


def test_seo002_heading_gap_in_code_block_ignored(lint_project):
    """SEO002: heading level gaps inside code blocks don't trigger."""
    _, docs_dir, config = lint_project

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n"
            "## Section\n\n"
            "Some content.\n\n"
            "```markdown\n"
            "#### Deeply nested heading in example\n"
            "```\n"
        )

    results = _run_lints(_build_all_docs(docs_dir), docs_dir, None, config)
    seo002 = [r for r in results if r.code == "SEO002"]

    assert len(seo002) == 0


# -- SEO008: word count excludes code blocks --


def test_seo008_word_count_excludes_code_blocks(lint_project):
    """SEO008: words inside code blocks are not counted for statistics density."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    # Put 200+ words in a code block and only a few outside.
    # The old code would count code block words, trigger SEO008.
    # The new code should only count prose words (< 200), so no trigger.
    code_words = " ".join(["code"] * 250)
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\ndescription: test\n---\n"
            "# Title\n\n"
            "Short paragraph here.\n\n"
            "```\n"
            f"{code_words}\n"
            "```\n"
        )

    results = _run_lints(_build_all_docs(docs_dir), docs_dir, None, config)
    seo008 = [r for r in results if r.code == "SEO008"]

    # Prose word count is well under 200, so SEO008 should NOT fire
    assert len(seo008) == 0


def test_seo008_prose_words_still_counted(lint_project):
    """SEO008: prose words (outside code blocks) are still counted correctly."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    # 250 prose words with no numbers -- should trigger
    prose_words = " ".join(["word"] * 250)
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\ndescription: test\n---\n"
            "# Title\n\n"
            f"{prose_words}\n"
        )

    results = _run_lints(_build_all_docs(docs_dir), docs_dir, None, config)
    seo008 = [r for r in results if r.code == "SEO008"]

    assert len(seo008) == 1


# -- SEO007: headings in code blocks --


def test_seo007_heading_in_code_block_ignored(lint_project):
    """SEO007: headings inside code blocks don't trigger paragraph length check."""
    _, docs_dir, config = lint_project
    config["base_url"] = "https://example.com"

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n"
            "## Real Section\n\n"
            + " ".join(["word"] * 50) + "\n\n"
            "```markdown\n"
            "## Heading in code block\n"
            "\n"
            "Short text.\n"
            "```\n"
        )

    results = _run_lints(_build_all_docs(docs_dir), docs_dir, None, config)
    seo007 = [r for r in results if r.code == "SEO007"]

    # Only the real heading should be checked, and it has 50 words (OK)
    assert len(seo007) == 0


# -- SEO014: meaningless alt in code blocks --


def test_seo014_meaningless_alt_in_code_block_ignored(lint_project):
    """SEO014: meaningless alt text inside a code block does NOT trigger."""
    _, docs_dir, config = lint_project

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n"
            "Some content.\n\n"
            "```markdown\n"
            "![image](photo.png)\n"
            "```\n"
        )

    results = _run_lints(_build_all_docs(docs_dir), docs_dir, None, config)
    seo014 = [r for r in results if r.code == "SEO014"]

    assert len(seo014) == 0


# -- SEO015: generic anchor in code blocks --


def test_seo015_generic_anchor_in_code_block_ignored(lint_project):
    """SEO015: generic anchor text in code block does NOT trigger."""
    _, docs_dir, config = lint_project

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n"
            "Some content.\n\n"
            "```markdown\n"
            "[click here](https://example.com)\n"
            "```\n"
        )

    results = _run_lints(_build_all_docs(docs_dir), docs_dir, None, config)
    seo015 = [r for r in results if r.code == "SEO015"]

    assert len(seo015) == 0


# -- SEO011: empty heading section in code blocks --


def test_seo011_consecutive_headings_in_code_block_ignored(lint_project):
    """SEO011: consecutive headings inside a code block do NOT trigger."""
    _, docs_dir, config = lint_project

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "# Title\n\n"
            "## Real Section\n\n"
            "Some content.\n\n"
            "```markdown\n"
            "## Empty Section\n"
            "## Another Section\n"
            "```\n"
        )

    results = _run_lints(_build_all_docs(docs_dir), docs_dir, None, config)
    seo011 = [r for r in results if r.code == "SEO011"]

    assert len(seo011) == 0


# -- SEO013: H1 in code block does not satisfy title requirement --


def test_seo013_h1_only_in_code_block_triggers(lint_project):
    """SEO013: H1 only inside a code block does not satisfy title requirement."""
    _, docs_dir, config = lint_project

    desc = "A" * 130
    with open(os.path.join(docs_dir, "page.md"), "w", encoding="utf-8") as f:
        f.write(
            f"---\ndescription: {desc}\n---\n"
            "```bash\n"
            "# Shell comment that looks like H1\n"
            "```\n\n"
            "## Only H2\n\nSome content.\n"
        )

    results = _run_lints(_build_all_docs(docs_dir), docs_dir, None, config)
    seo013 = [r for r in results if r.code == "SEO013"]

    assert len(seo013) == 1
    assert seo013[0].severity == "error"

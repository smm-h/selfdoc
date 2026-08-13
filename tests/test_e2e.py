"""End-to-end smoke test for the full selfdoc build pipeline with new directive syntax."""

import json
import os

from selfdoc.build import build
from conftest import default_config, DEFAULT_PREFIX


def test_e2e_build_with_new_directives(tmp_path):
    """Full build with ref, callout, and glossary directives using new syntax."""

    # -- Set up selfdoc.json --
    config = default_config(docs="docs/", output="docs/_build/")
    config_path = os.path.join(tmp_path, "selfdoc.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    # -- Set up src/__init__.py with a module docstring and a public function --
    src_dir = os.path.join(tmp_path, "src")
    os.makedirs(src_dir)
    init_py = os.path.join(src_dir, "__init__.py")
    with open(init_py, "w", encoding="utf-8") as f:
        f.write(
            '"""Example module for testing selfdoc builds."""\n'
            "\n"
            "\n"
            "def calculate_total(items, tax_rate):\n"
            '    """Calculate the total price including tax.\n'
            "\n"
            "    Args:\n"
            "        items: List of item prices.\n"
            "        tax_rate: Tax rate as a decimal.\n"
            "\n"
            "    Returns:\n"
            "        The total price with tax applied.\n"
            '    """\n'
            "    return sum(items) * (1 + tax_rate)\n"
        )

    # -- Set up docs/ directory --
    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)

    # index.md: frontmatter + one-liner ref directive
    index_md = os.path.join(docs_dir, "index.md")
    with open(index_md, "w", encoding="utf-8") as f:
        f.write(
            "---\n"
            "title: API Reference\n"
            "description: Auto-generated API docs\n"
            "date: 2025-01-01\n"
            "---\n"
            "\n"
            "# API Reference\n"
            "\n"
            ':-: ref path="src"\n'
        )

    # notes.md: frontmatter + callout block directive
    notes_md = os.path.join(docs_dir, "notes.md")
    with open(notes_md, "w", encoding="utf-8") as f:
        f.write(
            "---\n"
            "title: Notes\n"
            "description: Important notes\n"
            "date: 2025-01-01\n"
            "---\n"
            "\n"
            "# Notes\n"
            "\n"
            ":<: callout-note\n"
            ":=:\n"
            "::: This is an important note.\n"
            ":>:\n"
        )

    # glossary.md: frontmatter + glossary block directive
    glossary_md = os.path.join(docs_dir, "glossary.md")
    with open(glossary_md, "w", encoding="utf-8") as f:
        f.write(
            "---\n"
            "title: Glossary\n"
            "description: Key terms\n"
            "date: 2025-01-01\n"
            "---\n"
            "\n"
            "# Glossary\n"
            "\n"
            ":<: list-glossary\n"
            ":=:\n"
            "::: **Directive**: A block in Markdown that selfdoc resolves\n"
            "::: **Extractor**: A language-specific module that reads code\n"
            ":>:\n"
        )

    # -- Run the build --
    written = build(str(tmp_path))

    # -- Verify output files exist --
    output_dir = os.path.join(tmp_path, "docs", "_build")

    index_html_path = os.path.join(output_dir, DEFAULT_PREFIX, "index.html")
    notes_html_path = os.path.join(output_dir, DEFAULT_PREFIX, "notes", "index.html")
    glossary_html_path = os.path.join(output_dir, DEFAULT_PREFIX, "glossary", "index.html")
    style_css_path = os.path.join(output_dir, "style.css")

    assert os.path.isfile(index_html_path), "index.html not found"
    assert os.path.isfile(notes_html_path), "notes/index.html not found"
    assert os.path.isfile(glossary_html_path), "glossary/index.html not found"
    assert os.path.isfile(style_css_path), "style.css not found"

    # -- Verify index.html (ref directive resolved) --
    with open(index_html_path, "r", encoding="utf-8") as f:
        index_html = f.read()

    assert "<!DOCTYPE html>" in index_html
    assert "calculate_total" in index_html, (
        "Expected function name from src/__init__.py in resolved ref output"
    )
    assert "selfdoc:" not in index_html, (
        "Found selfdoc: error marker -- directive resolution failed"
    )

    # -- Verify notes/index.html (callout rendered) --
    with open(notes_html_path, "r", encoding="utf-8") as f:
        notes_html = f.read()

    assert '<div class="callout callout-note">' in notes_html
    assert "callout-title" in notes_html
    assert "important note" in notes_html

    # -- Verify glossary/index.html (glossary rendered) --
    with open(glossary_html_path, "r", encoding="utf-8") as f:
        glossary_html = f.read()

    assert "<dl>" in glossary_html
    assert '<dt><dfn id="term-directive">Directive</dfn></dt>' in glossary_html
    assert "<dd>" in glossary_html
    assert "language-specific module" in glossary_html

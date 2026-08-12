"""Where a heading written inside a doc comment ends up on the page.

A doc comment is written as if it owned a document.  Go's own convention
is a bare ``# Usage`` section title, and a docstring, KDoc, JSDoc or
component comment can carry any markdown its author felt like writing.
A generated reference page is not that document: it has exactly one H1,
its title, and the doc comment sits under the heading naming the symbol
it documents.

Emitted verbatim, a package doc with headings puts a second H1 on the
page -- a hard error that stops the whole build -- and detaches the doc's
sections from the symbol they belong to in the outline.  Every extractor
renests them instead: the shallowest heading in the doc becomes the
direct child of the heading it was emitted under, and the doc's own
nesting is preserved beneath it.
"""

from __future__ import annotations

import json
import os

import pytest

from selfdoc.build import build
from selfdoc_core.extractors.go import GoExtractor
from selfdoc_core.extractors.python import PythonExtractor
from selfdoc_core.extractors.svelte import SvelteExtractor
from selfdoc_core.extractors.typescript import TypeScriptExtractor
from conftest import default_config


def _levels(result, title):
    """The heading levels at which *title* appears in *result*."""
    levels = []
    for line in result.split("\n"):
        stripped = line.rstrip()
        if stripped.lstrip("#").strip() == title and stripped.startswith("#"):
            levels.append(len(stripped) - len(stripped.lstrip("#")))
    return levels


# -- Go: the language whose doc convention writes the headings -----------------


@pytest.fixture()
def go_pkg(tmp_path):
    os.makedirs(tmp_path / "x")
    (tmp_path / "go.mod").write_text("module example.com/x\n")
    (tmp_path / "x" / "lib.go").write_text(
        "// Package x does things.\n"
        "//\n"
        "// # Usage\n"
        "//\n"
        "// Call Run.\n"
        "//\n"
        "// ## Detail\n"
        "//\n"
        "// Carefully.\n"
        "package x\n"
        "\n"
        "// Run runs.\n"
        "//\n"
        "// # Caveats\n"
        "//\n"
        "// None.\n"
        "func Run() {}\n"
    )
    return str(tmp_path)


def test_a_go_package_docs_headings_nest_under_the_package(go_pkg):
    result = GoExtractor().extract("ref", {"path": "x"}, [], [go_pkg], go_pkg)
    assert _levels(result, "`x`") == [2]
    assert _levels(result, "Usage") == [3]
    assert _levels(result, "Detail") == [4]


def test_a_go_symbol_docs_headings_nest_under_the_symbol(go_pkg):
    result = GoExtractor().extract("ref", {"path": "x"}, [], [go_pkg], go_pkg)
    assert _levels(result, "`Run`") == [3]
    assert _levels(result, "Caveats") == [4]


def test_no_extracted_go_heading_is_an_h1(go_pkg):
    result = GoExtractor().extract("ref", {"path": "x"}, [], [go_pkg], go_pkg)
    assert _levels(result, "Usage") and 1 not in _levels(result, "Usage")
    for line in result.split("\n"):
        assert not line.startswith("# ")


# -- Python --------------------------------------------------------------------


def test_a_python_module_docstrings_headings_nest_under_the_module(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "core.py").write_text(
        '"""Core module.\n'
        "\n"
        "# Usage\n"
        "\n"
        "Import it.\n"
        '"""\n'
        "\n\n"
        "class Widget:\n"
        '    """A widget.\n'
        "\n"
        "    # Caveats\n"
        "\n"
        "    None.\n"
        '    """\n'
    )
    result = PythonExtractor().extract(
        "ref", {"path": "core"}, [], ["src/"], str(tmp_path),
    )
    assert _levels(result, "Usage") == [3]
    assert _levels(result, "Caveats") == [4]


# -- TypeScript ----------------------------------------------------------------


def test_a_typescript_jsdocs_headings_nest_under_the_module(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "core.ts").write_text(
        "/**\n"
        " * Core module.\n"
        " *\n"
        " * # Usage\n"
        " *\n"
        " * Import it.\n"
        " */\n"
        "\n"
        "/**\n"
        " * Makes a widget.\n"
        " *\n"
        " * # Caveats\n"
        " *\n"
        " * None.\n"
        " */\n"
        "export function makeWidget(): void {}\n"
    )
    result = TypeScriptExtractor().extract(
        "ref", {"path": "core.ts"}, [], ["src/"], str(tmp_path),
    )
    assert _levels(result, "Usage") == [3]
    assert _levels(result, "Caveats") == [4]


# -- Svelte --------------------------------------------------------------------


def test_a_svelte_component_docs_headings_nest_under_the_component(tmp_path):
    comp = tmp_path / "src" / "lib"
    comp.mkdir(parents=True)
    (comp / "Counter.svelte").write_text(
        "<script>\n"
        "  /**\n"
        "   * A counter.\n"
        "   *\n"
        "   * # Usage\n"
        "   *\n"
        "   * Drop it in.\n"
        "   */\n"
        "  export let count = 0;\n"
        "</script>\n"
    )
    result = SvelteExtractor().extract(
        "ref", {"path": "src/lib/Counter.svelte"}, [], [], str(tmp_path),
    )
    assert _levels(result, "`Counter`") == [2]
    assert _levels(result, "Usage") == [3]


# -- The page the build actually writes ----------------------------------------


def test_a_package_doc_with_headings_no_longer_breaks_the_build(tmp_path):
    """End to end: the reason this is a build blocker and not a nicety.

    The build refuses a page carrying more than one H1, and it counts them
    after directives resolve.  A single Go package whose doc comment
    follows Go's own heading convention therefore stopped its project's
    docs build outright, with a message about the *page* having two
    titles -- nothing pointing at the package comment that wrote one.
    """
    project = tmp_path / "proj"
    (project / "x").mkdir(parents=True)
    (project / "go.mod").write_text("module example.com/x\n")
    (project / "x" / "lib.go").write_text(
        "// Package x does things.\n"
        "//\n"
        "// # Usage\n"
        "//\n"
        "// Call it and it runs.\n"
        "package x\n"
    )
    config = default_config(
        docs="docs/",
        output="docs/_build/",
        source=[{"path": ".", "language": "go"}],
    )
    (project / "selfdoc.json").write_text(json.dumps(config))

    docs = project / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("# Test Project\n\nWelcome to the docs.\n")
    (docs / "reference.md").write_text(
        "# Reference\n\nEvery symbol the example package exports.\n\n"
        ':-: ref path="x"\n'
    )

    build(str(project))

    page = (project / "docs" / "_build" / "reference" / "index.html").read_text()
    assert page.count("<h1") == 1

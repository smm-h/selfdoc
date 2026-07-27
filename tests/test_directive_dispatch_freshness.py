"""Dispatch-freshness: the content dispatch stays in sync with the catalogue.

The directive catalogue is now a declarative document (selfdoc_core/directives.toml,
strictspec-governed). The runtime content dispatch -- the ``resolve_content``
if-chain plus the registry that adds ``table-commands`` -- is still Python code.
The honest equivalent of enum-baking here is a freshness test: the set of names
the content dispatch handles must equal exactly the set of content-category
directives in the document. If a content directive is added to the document but
not wired into the dispatch (or vice versa), these tests fail.
"""

# Importing selfdoc.content registers the selfdoc-specific table-commands
# resolver into the directive registry and extends CONTENT_DIRECTIVES with it.
import selfdoc.content as content
from selfdoc.catalog import CORE_DIRECTIVES


def _content_category_names() -> set[str]:
    return {
        name
        for name, spec in CORE_DIRECTIVES.items()
        if spec.category == "content"
    }


def _code_category_names() -> set[str]:
    return {
        name
        for name, spec in CORE_DIRECTIVES.items()
        if spec.category == "code"
    }


def test_content_dispatch_keys_equal_document_content_directives():
    """CONTENT_DIRECTIVES must equal the document's content-category names."""
    assert content.CONTENT_DIRECTIVES == _content_category_names()


def test_no_code_directive_in_content_dispatch():
    """Code-category directives dispatch to extractors, never as content."""
    assert content.CONTENT_DIRECTIVES.isdisjoint(_code_category_names())


def test_every_content_directive_is_actually_dispatched():
    """resolve_content returns non-None (has a branch) for every content name.

    A ``None`` return means the name matched no dispatch branch and no registry
    entry -- i.e. a catalogue directive with no resolver wired. A resolver that
    runs (even to an error string) or raises still proves a branch exists.
    """
    missing = []
    for name in sorted(_content_category_names()):
        try:
            result = content.resolve_content(name, {}, [], ".", config={})
        except Exception:
            # A resolver that raises is still a wired dispatch branch.
            continue
        if result is None:
            missing.append(name)
    assert missing == [], f"content directives with no dispatch branch: {missing}"

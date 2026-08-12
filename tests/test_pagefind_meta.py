"""The Pagefind filter and metadata attributes a built page carries.

The seven facets are the whole faceted-search surface: with no JSON index
to filter client-side, a facet that is not emitted here cannot be selected
anywhere.
"""

from selfdoc.html import _wrap_page
from selfdoc_core.html import PAGEFIND_FACET_KEYS


def _page(**kwargs):
    return _wrap_page(
        "<p>test</p>", "", "Test", "Project", "1.0.0",
        prefix="", **kwargs,
    )


class TestPagefindBody:
    def test_pagefind_body_on_article(self):
        """The article is the indexed region."""
        html = _page()
        idx = html.index("<article")
        article_tag = html[idx:html.index(">", idx) + 1]
        assert "data-pagefind-body" in article_tag

    def test_facets_sit_inside_the_indexed_body(self):
        """A filter outside data-pagefind-body would never be read."""
        html = _page(page_type="guide")
        article_start = html.index("<article")
        article_end = html.index("</article>")
        block = html[article_start:article_end]
        assert 'data-pagefind-filter="type:guide"' in block


class TestSevenFacets:
    """Every facet key the corpus carries is emitted as a filter."""

    def test_facet_key_set(self):
        assert PAGEFIND_FACET_KEYS == (
            "version", "locale", "group", "type", "target", "project", "tags",
        )

    def test_all_seven_emitted(self):
        html = _page(
            page_type="guide",
            current_locale="pt-BR",
            nav_group="Guides",
            deploy_target="cloudflare-pages",
            page_tags=["deploy", "hosting"],
        )
        assert 'data-pagefind-filter="version:1.0.0"' in html
        assert 'data-pagefind-filter="locale:pt-BR"' in html
        assert 'data-pagefind-filter="group:Guides"' in html
        assert 'data-pagefind-filter="type:guide"' in html
        assert 'data-pagefind-filter="target:cloudflare-pages"' in html
        assert 'data-pagefind-filter="project:Project"' in html
        assert 'data-pagefind-filter="tags:deploy"' in html
        assert 'data-pagefind-filter="tags:hosting"' in html

    def test_tags_use_the_repeated_shape(self):
        """Each tag is its own element, so no value is split on a comma."""
        html = _page(page_tags=["a,b", "c"])
        assert 'data-pagefind-filter="tags:a,b"' in html
        assert 'data-pagefind-filter="tags:c"' in html

    def test_empty_facets_are_omitted(self):
        """An empty value would offer a filter group nothing matches."""
        html = _page(page_tags=[])
        assert 'data-pagefind-filter="locale:"' not in html
        assert 'data-pagefind-filter="group:"' not in html
        assert 'data-pagefind-filter="target:"' not in html
        assert 'data-pagefind-filter="tags:' not in html

    def test_locale_falls_back_to_the_mount_locale(self):
        html = _page(mount_locale="fr")
        assert 'data-pagefind-filter="locale:fr"' in html

    def test_one_filter_per_element(self):
        """Two filters on one element would lose one to HTML parsing."""
        html = _page(page_type="guide", nav_group="Guides")
        for span in html.split("<span")[1:]:
            assert span.count("data-pagefind-filter=") <= 1


class TestResultMetadata:
    def test_meta_project(self):
        assert 'data-pagefind-meta="project:MyProject"' in _wrap_page(
            "<p>test</p>", "", "Test", "MyProject", "1.0.0", prefix="",
        )

    def test_meta_type(self):
        assert 'data-pagefind-meta="type:guide"' in _page(page_type="guide")

    def test_meta_type_absent_when_none(self):
        assert 'data-pagefind-meta="type:' not in _page(page_type=None)

    def test_meta_date(self):
        assert 'data-pagefind-meta="date:2024-01-15"' in _page(
            date_published="2024-01-15",
        )

    def test_meta_date_absent_when_none(self):
        assert 'data-pagefind-meta="date:' not in _page(date_published=None)

    def test_one_meta_per_element(self):
        html = _page(page_type="guide", date_published="2024-06-01")
        for span in html.split("<span")[1:]:
            assert span.count("data-pagefind-meta=") <= 1

    def test_html_escaping(self):
        html = _wrap_page(
            "<p>test</p>", "", "Test", 'My "Project" <1>', "1.0.0", prefix="",
        )
        assert (
            'data-pagefind-meta="project:My &quot;Project&quot; &lt;1&gt;"'
            in html
        )

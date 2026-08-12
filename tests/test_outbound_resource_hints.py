"""Resource-hint link elements are not outbound links.

``external_references`` collects what the outbound check will fetch.  A
``rel="preconnect"`` or ``rel="dns-prefetch"`` element names an ORIGIN for
the browser to warm up, not a document anyone navigates to: a GET at a bare
origin like ``https://fonts.googleapis.com`` legitimately answers 404, so
collecting it turned every deploy red for a page that was perfectly fine.

The exemption is exactly those two.  ``preload``, ``prefetch`` and
``modulepreload`` name a real file the browser will actually fetch, so a
dead one is a genuine defect and stays collected.
"""

from __future__ import annotations

from selfdoc_core.resolution import external_references


def _refs(html):
    return list(external_references(html))


class TestOriginOnlyHintsAreSkipped:
    def test_a_preconnect_is_not_collected(self):
        assert _refs(
            '<link rel="preconnect" href="https://fonts.example.net">'
        ) == []

    def test_a_dns_prefetch_is_not_collected(self):
        assert _refs(
            '<link rel="dns-prefetch" href="https://fonts.example.net">'
        ) == []

    def test_the_rel_may_carry_several_tokens(self):
        assert _refs(
            '<link rel="preconnect stylesheet" href="https://x.example.net">'
        ) == []

    def test_the_rel_token_is_matched_case_insensitively(self):
        assert _refs(
            '<link rel="PreConnect" href="https://x.example.net">'
        ) == []

    def test_a_crossorigin_preconnect_is_not_collected(self):
        assert _refs(
            '<link rel="preconnect" href="https://fonts.example.net" '
            'crossorigin>'
        ) == []


class TestRealResourcesStayCollected:
    def test_a_preload_names_a_file_and_is_collected(self):
        assert _refs(
            '<link rel="preload" as="font" href="https://x.example.net/f.woff2">'
        ) == ["https://x.example.net/f.woff2"]

    def test_a_prefetch_is_collected(self):
        assert _refs(
            '<link rel="prefetch" href="https://x.example.net/next.html">'
        ) == ["https://x.example.net/next.html"]

    def test_an_external_stylesheet_is_collected(self):
        assert _refs(
            '<link rel="stylesheet" href="https://x.example.net/s.css">'
        ) == ["https://x.example.net/s.css"]

    def test_an_anchor_is_collected(self):
        assert _refs(
            '<a href="https://x.example.net/page/">page</a>'
        ) == ["https://x.example.net/page/"]

    def test_an_image_source_is_collected(self):
        assert _refs(
            '<img src="https://x.example.net/a.png" alt="a">'
        ) == ["https://x.example.net/a.png"]


class TestTheExemptionIsPerElement:
    def test_the_same_url_reached_by_a_link_is_still_collected(self):
        """The hint is skipped; a real navigation to it is not."""
        html = (
            '<link rel="preconnect" href="https://x.example.net">'
            '<a href="https://x.example.net">visit</a>'
        )
        assert _refs(html) == ["https://x.example.net"]

    def test_neighbouring_references_survive_the_skip(self):
        html = (
            '<a href="https://one.example.net/">one</a>'
            '<link rel="dns-prefetch" href="https://two.example.net">'
            '<a href="https://three.example.net/">three</a>'
        )
        assert _refs(html) == [
            "https://one.example.net/",
            "https://three.example.net/",
        ]

    def test_a_link_element_without_a_rel_is_collected(self):
        assert _refs(
            '<link href="https://x.example.net/s.css">'
        ) == ["https://x.example.net/s.css"]

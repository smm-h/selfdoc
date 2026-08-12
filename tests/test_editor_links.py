"""Cross-repository link targets, and the addresses they insert.

A post is a site citizen: it is emitted at ``blog/<post-slug>/`` on the
site root while a project's documentation is served under that project's
own slug.  So the link a post writes to reach a project page is neither the
link that project's own pages use between themselves nor a site-absolute
path -- it is the project-mounted address, reached from two directories
down, and it has to survive the renderer untouched.

The last assertion here is the one that matters most: an inserted link is
put through the real render path and its target is resolved the way the
deploy's own reference check resolves one.  Anything less would be testing
string concatenation.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import threading

import pytest

from selfblog.editor_links import (
    POST_DEPTH,
    TO_SITE_ROOT,
    ManifestError,
    TargetIndex,
    load_manifest,
    manifest_targets,
    target_href,
)
from selfblog.editor_registry import load_registry
from selfblog.editor_server import EditorState, make_server
from selfblog.shared import page_target, post_target, target_output_path
from selfdoc_core.resolution import reference_target
from conftest import default_config

_DESCRIPTION = (
    "A post written to carry no lint findings at all, with a description "
    "long enough that the description-length rule has nothing to say."
)


def _manifest(slug, name, pages):
    return {
        "schema_version": 1,
        "name": name,
        "slug": slug,
        "version": "1.0.0",
        "description": f"{name} docs",
        "language": "python",
        "base_url": f"https://docs.example.com/{slug}",
        "pages": pages,
        "posts": [],
        "last_gen": "2024-01-01T00:00:00+00:00",
    }


def _page(path, title, headings=()):
    return {
        "path": path,
        "title": title,
        "type": "doc",
        "headings": [
            {"level": level, "text": text, "anchor": anchor}
            for level, text, anchor in headings
        ],
    }


ALPHA = _manifest("alpha", "Alpha", [
    _page("index.md", "Alpha"),
    _page("guide.md", "Alpha Guide", [
        (1, "Alpha Guide", "alpha-guide"),
        (2, "Getting started", "getting-started"),
    ]),
])

BETA = _manifest("beta", "Beta", [
    _page("api/reference.md", "Beta Reference", [
        (2, "Types", "types"),
    ]),
])


def _write_manifest(root, manifest):
    path = os.path.join(root, ".selfdoc", "manifest.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    return path


def _bare_project(root):
    os.makedirs(root, exist_ok=True)
    return root


def _registry_file(tmp_path, entries):
    path = os.path.join(str(tmp_path), "registry.toml")
    with open(path, "w", encoding="utf-8") as f:
        for name, project in entries:
            f.write(
                f'[[repo]]\nname = "{name}"\nkind = "local"\n'
                f'path = "{project}"\n\n'
            )
    return load_registry(path)


@pytest.fixture()
def two_repos(tmp_path):
    alpha = _bare_project(os.path.join(str(tmp_path), "alpha"))
    beta = _bare_project(os.path.join(str(tmp_path), "beta"))
    _write_manifest(alpha, ALPHA)
    _write_manifest(beta, BETA)
    return _registry_file(tmp_path, [("alpha", alpha), ("beta", beta)])


# -- the address ---------------------------------------------------------------


class TestTheHopIsDerived:
    def test_a_post_sits_two_directories_below_the_site_root(self):
        assert POST_DEPTH == 2
        assert TO_SITE_ROOT == "../../"

    def test_the_hop_is_read_off_the_post_address_itself(self):
        emitted = target_output_path(post_target("some-post"))
        assert TO_SITE_ROOT == "../" * (len(emitted.split("/")) - 1)

    def test_a_page_link_is_the_project_mounted_address(self):
        assert target_href("alpha", "guide.md") == "../../alpha/guide/"

    def test_a_projects_index_is_its_own_mount(self):
        assert target_href("alpha", "index.md") == "../../alpha/"

    def test_a_nested_page_keeps_its_directories(self):
        assert target_href("beta", "api/reference.md") == "../../beta/api/reference/"

    def test_a_section_carries_its_anchor(self):
        assert target_href("alpha", "guide.md", "getting-started") == (
            "../../alpha/guide/#getting-started"
        )

    def test_the_address_is_the_one_the_assembly_serves(self):
        assert target_href("alpha", "guide.md") == (
            TO_SITE_ROOT + page_target("alpha", "guide.md")
        )


# -- what a manifest offers -----------------------------------------------------


class TestManifestTargets:
    def test_every_page_is_offered_with_its_title_and_address(self):
        targets = manifest_targets(ALPHA, "alpha-repo")
        pages = [t for t in targets if t["kind"] == "page"]
        assert [(t["title"], t["address"]) for t in pages] == [
            ("Alpha", "alpha/"),
            ("Alpha Guide", "alpha/guide/"),
        ]

    def test_every_heading_is_offered_as_a_section(self):
        targets = manifest_targets(ALPHA, "alpha-repo")
        sections = [t for t in targets if t["kind"] == "section"]
        assert [(t["title"], t["address"]) for t in sections] == [
            ("Alpha Guide", "alpha/guide/#alpha-guide"),
            ("Getting started", "alpha/guide/#getting-started"),
        ]

    def test_a_section_names_the_page_it_is_on(self):
        [section] = [
            t for t in manifest_targets(BETA, "beta-repo")
            if t["kind"] == "section"
        ]
        assert section["page_title"] == "Beta Reference"
        assert section["page"] == "api/reference.md"

    def test_a_target_carries_the_repository_it_came_from(self):
        for target in manifest_targets(BETA, "beta-repo"):
            assert target["repo"] == "beta-repo"
            assert target["slug"] == "beta"

    def test_a_heading_without_an_anchor_is_not_a_target(self):
        manifest = _manifest("gamma", "Gamma", [
            {"path": "g.md", "title": "G", "type": "doc",
             "headings": [{"level": 2, "text": "No anchor", "anchor": ""}]},
        ])
        assert [t["kind"] for t in manifest_targets(manifest, "g")] == ["page"]


class TestLoadingAManifest:
    def test_an_absent_manifest_is_absence_not_an_error(self, tmp_path):
        assert load_manifest(os.path.join(str(tmp_path), "nope.json")) is None

    def test_a_malformed_manifest_is_refused(self, tmp_path):
        path = os.path.join(str(tmp_path), "manifest.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not json")
        with pytest.raises(ManifestError, match="readable manifest"):
            load_manifest(path)


# -- the index across every repository ------------------------------------------


class TestTargetIndex:
    def test_every_registered_repository_contributes(self, two_repos):
        index = TargetIndex(two_repos)
        repos = {t["repo"] for t in index.all_targets()}
        assert repos == {"alpha", "beta"}

    def test_a_query_matches_a_title(self, two_repos):
        index = TargetIndex(two_repos)
        assert [t["title"] for t in index.search("getting")] == ["Getting started"]

    def test_a_query_matches_an_address(self, two_repos):
        index = TargetIndex(two_repos)
        assert all(
            "beta" in t["address"] for t in index.search("beta/api")
        )

    def test_the_match_is_case_insensitive(self, two_repos):
        index = TargetIndex(two_repos)
        assert index.search("GUIDE")

    def test_an_empty_query_offers_everything(self, two_repos):
        index = TargetIndex(two_repos)
        assert len(index.search("")) == len(index.all_targets())

    def test_the_limit_is_honoured(self, two_repos):
        index = TargetIndex(two_repos)
        assert len(index.search("", limit=2)) == 2

    def test_a_repository_with_no_manifest_offers_nothing(self, tmp_path):
        bare = _bare_project(os.path.join(str(tmp_path), "bare"))
        registry = _registry_file(tmp_path, [("bare", bare)])
        assert TargetIndex(registry).all_targets() == []

    def test_a_rewritten_manifest_is_picked_up(self, tmp_path):
        alpha = _bare_project(os.path.join(str(tmp_path), "alpha"))
        _write_manifest(alpha, ALPHA)
        index = TargetIndex(_registry_file(tmp_path, [("alpha", alpha)]))
        assert not index.search("Rebuilt")

        rebuilt = _manifest("alpha", "Alpha", [_page("new.md", "Rebuilt Page")])
        _write_manifest(alpha, rebuilt)
        assert [t["title"] for t in index.search("Rebuilt")] == ["Rebuilt Page"]

    def test_a_remote_entry_contributes_nothing(self, tmp_path):
        path = os.path.join(str(tmp_path), "registry.toml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(
                '[[repo]]\nname = "afar"\nkind = "remote"\n'
                'repo = "smm-h/afar"\nref = "main"\n'
                f'cache = "{os.path.join(str(tmp_path), "cache")}"\n'
                "render = true\n"
            )
        assert TargetIndex(load_registry(path)).all_targets() == []


# -- the endpoint ---------------------------------------------------------------


@pytest.fixture()
def live(tmp_path, two_repos):
    from selfblog.editor_assets import TINYMOON_REQUIRED

    assets = os.path.join(str(tmp_path), "assets")
    for rel in TINYMOON_REQUIRED:
        full = os.path.join(assets, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write("/* stub */\n")

    server = make_server(EditorState(two_repos, assets), 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def _get(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        conn.close()


class TestTheLinkTargetEndpoint:
    def test_it_answers_targets_from_every_repository(self, live):
        status, body = _get(live, "/api/link-targets")
        assert status == 200
        assert {t["repo"] for t in body["targets"]} == {"alpha", "beta"}

    def test_a_link_trigger_offers_pages_and_sections_across_two_repos(
        self, live,
    ):
        """The done-when, at the wire: two repos, both target kinds."""
        _status, body = _get(live, "/api/link-targets")
        by_repo_kind = {(t["repo"], t["kind"]) for t in body["targets"]}
        assert ("alpha", "page") in by_repo_kind
        assert ("alpha", "section") in by_repo_kind
        assert ("beta", "page") in by_repo_kind
        assert ("beta", "section") in by_repo_kind

    def test_the_query_filters(self, live):
        _status, body = _get(live, "/api/link-targets?q=Types")
        assert [t["title"] for t in body["targets"]] == ["Types"]

    def test_the_limit_is_honoured(self, live):
        _status, body = _get(live, "/api/link-targets?limit=1")
        assert len(body["targets"]) == 1

    def test_a_nonsense_limit_is_refused(self, live):
        conn = http.client.HTTPConnection("127.0.0.1", live, timeout=20)
        try:
            conn.request("GET", "/api/link-targets?limit=lots")
            assert conn.getresponse().status == 400
        finally:
            conn.close()


# -- the inserted link, through the renderer ------------------------------------


def _project_with_post(root, content):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "selfdoc.json"), "w", encoding="utf-8") as f:
        json.dump(default_config(docs="docs/", output="docs/_build/"), f)

    src = os.path.join(root, "src")
    os.makedirs(src, exist_ok=True)
    with open(os.path.join(src, "__init__.py"), "w", encoding="utf-8") as f:
        f.write('"""Example package."""\n')

    docs = os.path.join(root, "docs")
    os.makedirs(docs, exist_ok=True)
    with open(os.path.join(docs, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Test Project\n\nWelcome.\n")

    posts = os.path.join(root, ".selfdoc", "posts")
    os.makedirs(posts, exist_ok=True)
    with open(os.path.join(posts, "hello.md"), "w", encoding="utf-8") as f:
        f.write(content)
    return root


def _hrefs(html):
    return [
        match.group(1)
        for match in re.finditer(r'<a [^>]*href="([^"]+)"', html)
    ]


class TestAnInsertedLinkResolves:
    """The done-when: what the completion inserts is what the site serves.

    The link is put through ``render_post`` -- the publish renderer over an
    unsaved buffer, which is exactly what the preview pane shows -- and its
    target is then resolved from the post's OWN emitted address with the
    same function the deploy's reference check uses.  Landing on the file
    the target project's page is emitted at is what "resolves" means.
    """

    def _render(self, tmp_path, targets):
        links = "\n\n".join(
            f"See [{target['title']}]({target['href']})." for target in targets
        )
        content = (
            "---\ntitle: Hello World\ndate: 2024-01-15\nslug: hello-world\n"
            f"description: {_DESCRIPTION}\n"
            "tags: [release]\ndraft: false\ndirectives: false\n---\n"
            f"# Hello World\n\n{links}\n"
        )
        project = _project_with_post(
            os.path.join(str(tmp_path), "writer"), content,
        )

        from selfdoc_core.render import render_post

        return content, render_post(project, "hello.md", content)

    def test_a_page_link_from_two_repositories_resolves(self, tmp_path):
        targets = [
            next(t for t in manifest_targets(ALPHA, "alpha")
                 if t["address"] == "alpha/guide/"),
            next(t for t in manifest_targets(BETA, "beta")
                 if t["address"] == "beta/api/reference/"),
        ]
        _content, html = self._render(tmp_path, targets)
        emitted = _hrefs(html)

        for target in targets:
            assert target["href"] in emitted, (
                f"the renderer did not emit {target['href']} verbatim"
            )
            resolved = reference_target(
                target_output_path(post_target("hello-world")),
                target["href"],
            )
            assert resolved == target_output_path(target["address"])

    def test_a_section_link_resolves_to_the_page_that_carries_the_anchor(
        self, tmp_path,
    ):
        target = next(
            t for t in manifest_targets(ALPHA, "alpha")
            if t["anchor"] == "getting-started"
        )
        _content, html = self._render(tmp_path, [target])
        assert target["href"] in _hrefs(html)

        resolved = reference_target(
            target_output_path(post_target("hello-world")), target["href"],
        )
        # reference_target drops the fragment: an anchor is a position on a
        # page, and the page is what has to exist.
        assert resolved == target_output_path(page_target("alpha", "guide.md"))

    def test_the_link_is_not_rewritten_into_something_else(self, tmp_path):
        """A directory URL is not a `.md` link, so nothing rewrites it."""
        target = next(
            t for t in manifest_targets(ALPHA, "alpha")
            if t["address"] == "alpha/"
        )
        _content, html = self._render(tmp_path, [target])
        assert "../../alpha/" in _hrefs(html)

    def test_the_link_is_never_origin_absolute(self, tmp_path):
        """The site has to resolve under any mount point."""
        targets = manifest_targets(ALPHA, "alpha")
        for target in targets:
            assert not target["href"].startswith("/")
            assert "://" not in target["href"]

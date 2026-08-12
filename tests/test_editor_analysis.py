"""The editor's inline assistance: spelling marks and lint marks on a buffer.

Two properties carry everything here.  The first is that neither lane is a
second opinion: the words come from the shared spelling engine (same masks,
same vendored list, same machine-local accept list) and the marks come from
the project's real lint rules over the check's own post slice, so a finding
on screen is a finding ``selfdoc check`` reports.  The second is the
coordinate change -- the engines answer in lines and columns, the editor
paints flat character offsets over the buffer -- which is the one thing the
editor adds and therefore the one thing that can be wrong.

Analysing a buffer writes nothing, for the same reason previewing one
writes nothing: the buffer is unsaved, and looking at it must not decide
that it is saved.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import threading
from pathlib import Path

import pytest

from selfblog.editor_analysis import (
    analyze_buffer,
    lint_findings,
    spelling_findings,
)
from selfblog.editor_registry import load_registry
from selfblog.editor_server import EditorState, make_server
from conftest import default_config

_POST_NAME = "hello.md"


# Long enough to clear SEO009's 120-character floor, so a post the rules
# have nothing to say about really produces no findings.
_DESCRIPTION = (
    "A post written to carry no lint findings at all, with a description "
    "long enough that the description-length rule has nothing to say about "
    "it either."
)

# Between 30 and 80 words, which is the band SEO007 holds every first
# paragraph to.
_BODY = (
    "This post exists so that the editor has something to analyse, and it "
    "says enough to clear the first-paragraph length rule without saying "
    "anything a reader would have to think about. It is filler, written "
    "plainly, and it is here only to give the lint rules a page shaped "
    "exactly like a real one so that a clean buffer really does come back "
    "with nothing at all to report."
)


def _post(body, *, draft=False, title="Hello World", slug="hello-world"):
    return (
        f"---\ntitle: {title}\ndate: 2024-01-15\nslug: {slug}\n"
        f"description: {_DESCRIPTION}\n"
        f"tags: [release]\ndraft: {'true' if draft else 'false'}\n"
        f"directives: false\n---\n{body}"
    )


_CLEAN = _post(f"# Hello World\n\n{_BODY}\n")


def _make_project(root, posts=((_POST_NAME, _CLEAN),), pages=("index.md",)):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "selfdoc.json"), "w", encoding="utf-8") as f:
        json.dump(default_config(docs="docs/", output="docs/_build/"), f)

    src = os.path.join(root, "src")
    os.makedirs(src, exist_ok=True)
    with open(os.path.join(src, "__init__.py"), "w", encoding="utf-8") as f:
        f.write('"""Example package."""\n')

    docs = os.path.join(root, "docs")
    os.makedirs(docs, exist_ok=True)
    for page in pages:
        full = os.path.join(docs, page)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write("# Test Project\n\nWelcome.\n")

    posts_dir = os.path.join(root, ".selfdoc", "posts")
    os.makedirs(posts_dir, exist_ok=True)
    for name, body in posts:
        with open(os.path.join(posts_dir, name), "w", encoding="utf-8") as f:
            f.write(body)
    return root


def _registry(tmp_path, project):
    path = os.path.join(str(tmp_path), "registry.toml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f'[[repo]]\nname = "proj"\nkind = "local"\npath = "{project}"\n')
    return load_registry(path)


@pytest.fixture()
def project(tmp_path):
    return _make_project(os.path.join(str(tmp_path), "proj"))


@pytest.fixture()
def entry(tmp_path, project):
    return _registry(tmp_path, project).get("proj")


def _tree_fingerprint(root):
    digest = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            stat = os.stat(full)
            with open(full, "rb") as f:
                body = hashlib.sha256(f.read()).hexdigest()
            digest.update(
                repr((os.path.relpath(full, root), stat.st_size,
                      stat.st_mtime_ns, body)).encode()
            )
    return digest.hexdigest()


# -- spelling ------------------------------------------------------------------


class TestSpellingOffsets:
    def test_a_misspelling_is_reported_at_the_offset_of_its_word(self):
        content = _post("# Hello World\n\nThis is teh post content.\n")
        [finding] = [
            f for f in spelling_findings(content) if f["word"] == "teh"
        ]
        assert content[finding["from"]:finding["to"]] == "teh"

    def test_the_offset_accounts_for_the_frontmatter_above_it(self):
        content = _post("# Hello World\n\nThis is teh post content.\n")
        finding = spelling_findings(content)[0]
        # The offset is into the WHOLE buffer, frontmatter included -- which
        # is the text the editor holds.
        assert finding["from"] > content.index("---\n")
        assert finding["line"] == content[:finding["from"]].count("\n") + 1

    def test_every_misspelling_in_a_buffer_maps_to_its_own_word(self):
        content = _post(
            "# Hello World\n\nteh recieve seperate words are all wrong.\n"
        )
        findings = spelling_findings(content)
        assert {f["word"] for f in findings} >= {"teh", "recieve", "seperate"}
        for finding in findings:
            assert content[finding["from"]:finding["to"]] == finding["word"]

    def test_offsets_survive_a_tab_indented_line(self):
        content = _post("# Hello World\n\n- item\n- teh other item\n")
        [finding] = [
            f for f in spelling_findings(content) if f["word"] == "teh"
        ]
        assert content[finding["from"]:finding["to"]] == "teh"

    def test_offsets_survive_non_ascii_text_above_the_word(self):
        content = _post("# Hello World\n\nA naïve — dash — line.\n\nteh end.\n")
        [finding] = [
            f for f in spelling_findings(content) if f["word"] == "teh"
        ]
        assert content[finding["from"]:finding["to"]] == "teh"

    def test_a_clean_buffer_reports_nothing(self):
        assert spelling_findings(_CLEAN) == []

    def test_the_finding_carries_the_engines_own_message(self):
        content = _post("# Hello World\n\nThis is teh post.\n")
        finding = spelling_findings(content)[0]
        assert finding["message"].startswith("Unrecognized word 'teh'")


class TestSpellingIsTheSharedEngine:
    def test_a_word_inside_a_code_span_is_masked(self):
        """The engine's masks, not a second set written for the editor."""
        content = _post("# Hello World\n\nThe `teh` identifier is fine.\n")
        assert [f["word"] for f in spelling_findings(content)] == []

    def test_a_fenced_code_block_is_not_prose(self):
        content = _post("# Hello World\n\n```\nteh recieve\n```\n")
        assert spelling_findings(content) == []

    def test_a_link_target_is_masked_and_its_text_is_not(self):
        content = _post(
            "# Hello World\n\nSee [teh page](../../alpha/guide/).\n"
        )
        assert [f["word"] for f in spelling_findings(content)] == ["teh"]

    def test_the_machine_local_accept_list_is_consulted(self, tmp_path,
                                                        monkeypatch):
        accept = Path(str(tmp_path)) / "spelling-accept.txt"
        accept.write_text("selfblog\n", encoding="utf-8")
        content = _post("# Hello World\n\nThe selfblog editor runs here.\n")

        monkeypatch.setattr(
            "selfdoc_core.spelling.ACCEPT_LIST_PATH",
            Path(str(tmp_path)) / "absent.txt",
        )
        assert [f["word"] for f in spelling_findings(content)] == ["selfblog"]

        monkeypatch.setattr("selfdoc_core.spelling.ACCEPT_LIST_PATH", accept)
        assert spelling_findings(content) == []


# -- lints ---------------------------------------------------------------------


def _codes(lints):
    return [lint["code"] for lint in lints]


class TestLintMarks:
    def test_a_clean_post_reports_nothing(self, entry):
        assert lint_findings(entry, _POST_NAME, _CLEAN) == []

    def test_a_second_h1_is_reported_under_its_registered_code(self, entry):
        content = _post("# Hello World\n\n# Second Title\n\nBody.\n")
        lints = lint_findings(entry, _POST_NAME, content)
        assert "SEO001" in _codes(lints)

    def test_the_severity_comes_from_the_registry(self, entry):
        from selfdoc_core.lints import LINT_REGISTRY

        content = _post("# Hello World\n\n# Second Title\n\nBody.\n")
        [seo001] = [
            lint for lint in lint_findings(entry, _POST_NAME, content)
            if lint["code"] == "SEO001"
        ]
        assert seo001["severity"] == LINT_REGISTRY["SEO001"].severity

    def test_a_line_number_is_a_line_of_the_buffer(self, entry):
        content = _post("# Hello World\n\n## Two\n\n#### Four\n")
        [gap] = [
            lint for lint in lint_findings(entry, _POST_NAME, content)
            if lint["code"] == "SEO002"
        ]
        lines = content.split("\n")
        assert lines[gap["line"] - 1].startswith("#### Four")

    def test_a_draft_buffer_is_judged_too(self, entry):
        """The build skips a draft; the editor is where a draft is written."""
        content = _post(
            "# Hello World\n\n# Second Title\n\nBody.\n", draft=True,
        )
        assert "SEO001" in _codes(lint_findings(entry, _POST_NAME, content))

    def test_the_buffer_is_judged_not_the_saved_file(self, entry):
        """The saved post is clean; only the unsaved buffer has the defect."""
        content = _post("# Hello World\n\n# Second Title\n\nBody.\n")
        assert "SEO001" in _codes(lint_findings(entry, _POST_NAME, content))
        assert lint_findings(entry, _POST_NAME, _CLEAN) == []

    def test_spelling_is_not_reported_twice(self, entry):
        """One misspelling is one finding, in the lane that has its columns."""
        content = _post("# Hello World\n\nThis is teh post content.\n")
        assert "SPELL001" not in _codes(lint_findings(entry, _POST_NAME, content))
        assert [f["word"] for f in spelling_findings(content)] == ["teh"]


class TestTheSliceIsTheUniverseALinkIsJudgedAgainst:
    """XREF001 resolves a link against the page's own directory.

    A post's own directory is the posts directory, so the pages a post's
    ``.md`` link can name are the other posts -- which is exactly the slice
    the rules run over, saved posts and the unsaved buffer alike.
    """

    def _two_post_project(self, tmp_path, name):
        sibling = _post(
            f"# Sibling\n\n{_BODY}\n", title="Sibling", slug="sibling",
        )
        return _make_project(
            os.path.join(str(tmp_path), name),
            posts=((_POST_NAME, _CLEAN), ("sibling.md", sibling)),
        )

    def test_a_link_to_a_sibling_post_resolves(self, tmp_path):
        project = self._two_post_project(tmp_path, "known")
        entry = _registry(tmp_path, project).get("proj")
        content = _post(f"# Hello World\n\n{_BODY}\n\nSee [it](sibling.md).\n")
        assert "XREF001" not in _codes(lint_findings(entry, _POST_NAME, content))

    def test_a_link_to_a_post_that_does_not_exist_is_reported(self, tmp_path):
        project = self._two_post_project(tmp_path, "unknown")
        entry = _registry(tmp_path, project).get("proj")
        content = _post(f"# Hello World\n\n{_BODY}\n\nSee [it](ghost.md).\n")
        assert "XREF001" in _codes(lint_findings(entry, _POST_NAME, content))

    def test_a_site_level_cross_link_is_not_an_md_link_at_all(self, tmp_path):
        """The addresses the completion inserts are directory URLs, not files."""
        project = self._two_post_project(tmp_path, "crosslink")
        entry = _registry(tmp_path, project).get("proj")
        content = _post(
            f"# Hello World\n\n{_BODY}\n\nSee [the guide](../../alpha/guide/).\n"
        )
        assert "XREF001" not in _codes(lint_findings(entry, _POST_NAME, content))


class TestABufferThatIsNotAValidPost:
    def test_a_missing_date_is_the_post_check_s_own_code(self, entry):
        broken = (
            "---\ntitle: No Date\nslug: no-date\ndirectives: false\n---\nBody\n"
        )
        assert _codes(lint_findings(entry, _POST_NAME, broken)) == ["POST001"]

    def test_a_missing_title_is_reported_rather_than_raised(self, entry):
        broken = (
            "---\ndate: 2024-01-15\nslug: no-title\ndirectives: false\n---\nB\n"
        )
        assert _codes(lint_findings(entry, _POST_NAME, broken)) == ["POST002"]

    def test_spelling_still_answers_for_a_buffer_that_is_not_a_post(self):
        """The lanes fail independently, which is why they are two lanes."""
        broken = "---\ntitle: No Date\n---\n\nThis is teh body.\n"
        assert [f["word"] for f in spelling_findings(broken)] == ["teh"]


# -- both lanes, and the tree ---------------------------------------------------


class TestAnalyzeBuffer:
    def test_both_lanes_come_back(self, entry):
        content = _post("# Hello World\n\n# Two\n\nThis is teh body.\n")
        findings = analyze_buffer(entry, _POST_NAME, content)
        assert [f["word"] for f in findings["spelling"]] == ["teh"]
        assert "SEO001" in _codes(findings["lints"])

    def test_analysing_a_buffer_writes_nothing(self, entry, project):
        content = _post("# Hello World\n\n# Two\n\nThis is teh body.\n")
        before = _tree_fingerprint(project)
        analyze_buffer(entry, _POST_NAME, content)
        assert _tree_fingerprint(project) == before

    def test_a_remote_entry_is_refused(self, tmp_path, project):
        path = os.path.join(str(tmp_path), "remote.toml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(
                '[[repo]]\nname = "afar"\nkind = "remote"\n'
                'repo = "smm-h/afar"\nref = "main"\n'
                f'cache = "{os.path.join(str(tmp_path), "cache")}"\n'
                "render = true\n"
            )
        entry = load_registry(path).get("afar")
        from selfblog.editor_server import RemoteNotServed

        with pytest.raises(RemoteNotServed):
            analyze_buffer(entry, _POST_NAME, _CLEAN)


# -- the wire ------------------------------------------------------------------


@pytest.fixture()
def live(tmp_path, project):
    assets = os.path.join(str(tmp_path), "assets")
    from selfblog.editor_assets import TINYMOON_REQUIRED

    for rel in TINYMOON_REQUIRED:
        full = os.path.join(assets, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write("/* stub */\n")

    state = EditorState(_registry(tmp_path, project), assets)
    server = make_server(state, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {"port": server.server_port, "project": project}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def _request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    try:
        payload = body.encode("utf-8") if body is not None else None
        conn.request(method, path, body=payload)
        response = conn.getresponse()
        return response.status, response.read().decode("utf-8")
    finally:
        conn.close()


class TestTheAnalysisEndpoint:
    def test_it_answers_both_lanes(self, live):
        content = _post("# Hello World\n\n# Two\n\nThis is teh body.\n")
        status, text = _request(
            live["port"], "POST",
            f"/api/repos/proj/analysis?path={_POST_NAME}", content,
        )
        assert status == 200
        body = json.loads(text)
        assert body["repo"] == "proj"
        assert body["path"] == _POST_NAME
        assert [f["word"] for f in body["spelling"]] == ["teh"]
        assert "SEO001" in _codes(body["lints"])

    def test_it_writes_nothing(self, live):
        content = _post("# Hello World\n\nThis is teh body.\n")
        before = _tree_fingerprint(live["project"])
        _request(
            live["port"], "POST",
            f"/api/repos/proj/analysis?path={_POST_NAME}", content,
        )
        assert _tree_fingerprint(live["project"]) == before

    def test_a_buffer_the_renderer_would_refuse_still_gets_findings(self, live):
        """The reason analysis is a sibling of the preview, not a passenger."""
        broken = "---\ntitle: No Date\n---\n\nThis is teh body.\n"
        status, text = _request(
            live["port"], "POST",
            f"/api/repos/proj/analysis?path={_POST_NAME}", broken,
        )
        assert status == 200
        body = json.loads(text)
        assert [f["word"] for f in body["spelling"]] == ["teh"]
        assert _codes(body["lints"]) == ["POST001"]

        preview_status, _ = _request(
            live["port"], "POST",
            f"/api/repos/proj/preview?path={_POST_NAME}", broken,
        )
        assert preview_status == 400

    def test_a_path_outside_the_posts_directory_is_refused(self, live):
        status, _ = _request(
            live["port"], "POST",
            "/api/repos/proj/analysis?path=..%2Fescape.md", _CLEAN,
        )
        assert status == 400

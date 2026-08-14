"""The publish surface: the declaration, the plan, and the consent path.

Three properties, and the third is the reason the other two exist.

* The dialog is rendered from the COMMAND's own declaration -- strictcli's
  schema for ``post publish`` -- so it cannot describe an operation the
  command does not perform.  A classification changed in ``cli.py`` changes
  what the surface says with nothing to update in the editor.
* The scope is the repository.  ``post publish`` publishes every non-draft
  post the project declares, so the surface says exactly that and the plan
  carries the actual list, computed server-side.
* A call without consent is refused BY THE FRAMEWORK.  Both halves are
  driven here: the refusal with no consent (and nothing runs), and the
  success with it (and the command really runs).  Everything that would
  leave the machine is replaced -- the test floor forbids a real push --
  but the consent path itself is the real one.
"""

from __future__ import annotations

import http.client
import json
import os
import threading

import pytest

from selfblog.editor_publish import (
    PUBLISH_COMMAND,
    SCOPE,
    PublishFailed,
    PublishRefused,
    publish_descriptor,
    publish_plan,
    run_publish,
)
from selfblog.editor_registry import load_registry
from selfblog.editor_server import EditorState, make_server
from conftest import default_config

_DESCRIPTION = (
    "A post written to carry no lint findings at all, with a description "
    "long enough that the description-length rule has nothing to say."
)


def _post(name, title, slug, *, draft=False, date="2024-01-15"):
    return name, (
        f"---\ntitle: {title}\ndate: {date}\nslug: {slug}\n"
        f"description: {_DESCRIPTION}\n"
        f"tags: [release]\ndraft: {'true' if draft else 'false'}\n"
        f"directives: false\n---\n# {title}\n\nBody of {title}.\n"
    )


LIVE = _post("hello.md", "Hello World", "hello-world")
SECOND = _post("second.md", "Second Post", "second-post", date="2024-02-01")
DRAFT = _post("later.md", "Later", "later", draft=True)


def _make_project(root, posts=(LIVE, SECOND, DRAFT)):
    os.makedirs(root, exist_ok=True)
    config = default_config(docs="docs/", output="docs/_build/")
    config["topology"] = {"slug": "proj"}
    config["assembly"] = {"repo": "owner/assembly"}
    with open(os.path.join(root, "selfdoc.json"), "w", encoding="utf-8") as f:
        json.dump(config, f)

    src = os.path.join(root, "src")
    os.makedirs(src, exist_ok=True)
    with open(os.path.join(src, "__init__.py"), "w", encoding="utf-8") as f:
        f.write('"""Example package."""\n')

    docs = os.path.join(root, "docs")
    os.makedirs(docs, exist_ok=True)
    with open(os.path.join(docs, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Test Project\n\nWelcome.\n")

    posts_dir = os.path.join(root, ".selfdoc", "posts")
    os.makedirs(posts_dir, exist_ok=True)
    for name, body in posts:
        with open(os.path.join(posts_dir, name), "w", encoding="utf-8") as f:
            f.write(body)
    return root


@pytest.fixture()
def project(tmp_path):
    return _make_project(os.path.join(str(tmp_path), "proj"))


@pytest.fixture()
def entry(tmp_path, project):
    path = os.path.join(str(tmp_path), "registry.toml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f'[[repo]]\nname = "proj"\nkind = "local"\npath = "{project}"\n')
    return load_registry(path).get("proj")


class Recorder:
    """Everything the publish would send off the machine, recorded instead."""

    def __init__(self):
        self.pushes = []
        self.dispatches = []

    def install(self, monkeypatch):
        import selfblog.assembly as assembly
        from selfdoc_core import effects

        def _push(repo, files, message, delete_paths=None):
            self.pushes.append({
                "repo": repo, "files": dict(files), "message": message,
                "delete_paths": list(delete_paths or []),
            })
            return {"commit": "0" * 40}

        monkeypatch.setattr(assembly, "push_files_to_repo", _push)
        monkeypatch.setattr(assembly, "load_remote_roster", lambda repo: {})
        monkeypatch.setattr(
            assembly, "remote_post_claims", lambda repo, slug, roster: {},
        )
        monkeypatch.setattr(
            assembly, "refuse_foreign_post_overwrite",
            lambda slug, produced, claims: None,
        )
        monkeypatch.setattr(
            assembly, "stage_published_record",
            lambda repo, slug, owner, produced, files: [],
        )

        class _Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        # Only the network-touching call is replaced. Everything else the
        # publish shells out to -- git, reading the manifest out of HEAD --
        # is left alone, because replacing the whole chokepoint would stub
        # out the parts of the publish this test exists to exercise.
        real_run = effects.run

        def _run(cmd, **kwargs):
            if list(cmd)[:1] == ["gh"]:
                self.dispatches.append({"cmd": list(cmd), **kwargs})
                return _Completed()
            return real_run(cmd, **kwargs)

        monkeypatch.setattr(effects, "run", _run)
        return self


@pytest.fixture()
def recorder(monkeypatch):
    return Recorder().install(monkeypatch)


# -- the declaration ------------------------------------------------------------


class TestTheDescriptorIsTheCommandsOwnDeclaration:
    def _declared(self):
        from selfblog.cli import app

        group, _, name = PUBLISH_COMMAND.partition(".")
        return app.dump_schema_dict()["groups"][group]["commands"][name]

    def test_the_effect_is_the_declared_one(self):
        assert publish_descriptor()["effect"] == self._declared()["effect"]

    def test_it_is_consequential_because_the_command_says_so(self):
        assert self._declared()["consequential"] is True
        assert publish_descriptor()["consequential"] is True

    def test_the_help_is_the_commands_own(self):
        assert publish_descriptor()["help"] == self._declared()["help"]

    def test_every_declared_grant_reaches_the_surface(self):
        declared = self._declared().get("grants") or []
        assert publish_descriptor()["grants"] == [dict(g) for g in declared]
        assert declared, "the publish declares at least one grant"

    def test_the_grant_says_what_it_reaches(self):
        [grant] = publish_descriptor()["grants"]
        assert grant["name"] == "assembly-dispatch"
        assert "rebuilds and republishes" in grant["reason"]

    def test_it_names_the_command_it_will_call(self):
        assert publish_descriptor()["command"] == PUBLISH_COMMAND

    def test_it_names_the_consent_parameter(self):
        assert publish_descriptor()["consent_parameter"] == "approve_consequential"


class TestTheScopeIsTheRepository:
    def test_the_scope_is_declared(self):
        assert publish_descriptor()["scope"] == SCOPE == "repository"

    def test_the_note_says_every_non_draft_post_of_the_repository(self):
        note = publish_descriptor()["scope_note"]
        assert "every non-draft post in this repository" in note

    def test_the_note_never_says_this_post(self):
        note = publish_descriptor()["scope_note"].lower()
        assert "this post" not in note
        assert "publish this post" not in note

    def test_the_note_says_it_cannot_be_taken_back(self):
        assert "cannot be unpublished" in publish_descriptor()["scope_note"]


# -- the plan --------------------------------------------------------------------


class TestThePlanIsComputedHere:
    def test_every_non_draft_post_is_listed(self, entry):
        plan = publish_plan(entry)
        assert sorted(p["slug"] for p in plan["publishing"]) == [
            "hello-world", "second-post",
        ]

    def test_drafts_are_listed_as_withheld(self, entry):
        plan = publish_plan(entry)
        assert [p["slug"] for p in plan["withheld"]] == ["later"]

    def test_the_plan_names_the_repository_and_the_assembly(self, entry):
        plan = publish_plan(entry)
        assert plan["repo"] == "proj"
        assert plan["project"] == "proj"
        assert plan["assembly"] == "owner/assembly"

    def test_a_project_with_only_drafts_publishes_nothing(self, tmp_path):
        project = _make_project(
            os.path.join(str(tmp_path), "drafty"), posts=(DRAFT,),
        )
        path = os.path.join(str(tmp_path), "drafty.toml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f'[[repo]]\nname = "d"\nkind = "local"\npath = "{project}"\n')
        plan = publish_plan(load_registry(path).get("d"))
        assert plan["publishing"] == []
        assert len(plan["withheld"]) == 1


# -- the consent path -------------------------------------------------------------


class TestTheFrameworkRefusesAnUnconsentedCall:
    def test_a_call_without_consent_is_refused(self, entry, recorder):
        with pytest.raises(PublishRefused) as exc:
            run_publish(entry, False)
        # strictcli's own wording, not a message written here.  The framework
        # names the command and says the call has to carry confirmation; the
        # exact phrasing is strictcli's to change, so only those two facts are
        # asserted.
        assert PUBLISH_COMMAND in str(exc.value)
        assert "consequential" in str(exc.value)
        assert "confirmation" in str(exc.value)

    def test_nothing_ran_when_the_call_was_refused(self, entry, recorder):
        with pytest.raises(PublishRefused):
            run_publish(entry, False)
        assert recorder.pushes == []
        assert recorder.dispatches == []

    def test_the_refusal_comes_from_the_framework_not_from_here(
        self, entry, recorder,
    ):
        """The same refusal a direct programmatic call gets, verbatim."""
        import strictcli

        from selfblog.cli import app

        with pytest.raises(strictcli.InvokeError) as direct:
            app.call(PUBLISH_COMMAND)
        with pytest.raises(PublishRefused) as through_editor:
            run_publish(entry, False)
        assert str(through_editor.value) == str(direct.value)

    def test_the_working_directory_survives_a_refusal(self, entry, recorder):
        before = os.getcwd()
        with pytest.raises(PublishRefused):
            run_publish(entry, False)
        assert os.getcwd() == before


class TestAConsentedCallRuns:
    def test_it_succeeds_and_reports_what_it_did(self, entry, recorder):
        result = run_publish(entry, True)
        assert result["ok"] is True
        assert result["exit_code"] == 0
        assert result["command"] == PUBLISH_COMMAND
        assert "Published 2 post(s)" in result["stdout"]

    def test_the_publish_really_pushed_the_posts(self, entry, recorder):
        run_publish(entry, True)
        [push] = recorder.pushes
        assert push["repo"] == "owner/assembly"
        assert any(
            path.startswith("site/blog/hello-world/")
            for path in push["files"]
        )
        assert any(
            path.startswith("site/blog/second-post/")
            for path in push["files"]
        )

    def test_a_draft_is_not_published(self, entry, recorder):
        run_publish(entry, True)
        [push] = recorder.pushes
        assert not any("later" in path for path in push["files"])

    def test_the_assembly_rebuild_is_dispatched(self, entry, recorder):
        run_publish(entry, True)
        [dispatch] = recorder.dispatches
        assert dispatch["grant"] == "assembly-dispatch"
        assert "/repos/owner/assembly/dispatches" in dispatch["cmd"]

    def test_the_working_directory_is_restored(self, entry, recorder):
        before = os.getcwd()
        run_publish(entry, True)
        assert os.getcwd() == before

    def test_a_failing_publish_surfaces_its_own_output(self, entry, recorder,
                                                       monkeypatch):
        import selfblog.assembly as assembly

        def _explode(*args, **kwargs):
            raise RuntimeError("the assembly refused the write")

        monkeypatch.setattr(assembly, "push_files_to_repo", _explode)
        with pytest.raises(RuntimeError, match="the assembly refused"):
            run_publish(entry, True)

    def test_a_nonzero_exit_is_a_failure_carrying_the_reason(
        self, tmp_path, recorder,
    ):
        """A project with no assembly configured refuses, and says so."""
        project = _make_project(os.path.join(str(tmp_path), "unconfigured"))
        with open(os.path.join(project, "selfdoc.json"), encoding="utf-8") as f:
            config = json.load(f)
        del config["assembly"]
        with open(os.path.join(project, "selfdoc.json"), "w", encoding="utf-8") as f:
            json.dump(config, f)

        path = os.path.join(str(tmp_path), "unconfigured.toml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f'[[repo]]\nname = "u"\nkind = "local"\npath = "{project}"\n')

        with pytest.raises(PublishFailed, match="assembly.repo"):
            run_publish(load_registry(path).get("u"), True)


class TestConsentIsNeverRemembered:
    def test_a_second_publish_needs_its_own_consent(self, entry, recorder):
        run_publish(entry, True)
        with pytest.raises(PublishRefused):
            run_publish(entry, False)
        assert len(recorder.pushes) == 1


# -- the wire -----------------------------------------------------------------------


@pytest.fixture()
def live(tmp_path, project):
    from selfblog.editor_assets import TINYMOON_REQUIRED

    assets = os.path.join(str(tmp_path), "assets")
    for rel in TINYMOON_REQUIRED:
        full = os.path.join(assets, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write("/* stub */\n")

    registry_path = os.path.join(str(tmp_path), "registry.toml")
    with open(registry_path, "w", encoding="utf-8") as f:
        f.write(f'[[repo]]\nname = "proj"\nkind = "local"\npath = "{project}"\n')

    server = make_server(EditorState(load_registry(registry_path), assets), 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def _request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        payload = body.encode("utf-8") if body is not None else None
        conn.request(method, path, body=payload)
        response = conn.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        conn.close()


class TestThePublishEndpoint:
    def test_the_surface_carries_the_descriptor_and_the_plan(self, live):
        status, body = _request(live, "GET", "/api/repos/proj/publish")
        assert status == 200
        assert body["descriptor"]["consequential"] is True
        assert body["descriptor"]["scope"] == "repository"
        assert sorted(p["slug"] for p in body["plan"]["publishing"]) == [
            "hello-world", "second-post",
        ]

    def test_a_post_without_consent_is_refused_verbatim(self, live, recorder):
        status, body = _request(
            live, "POST", "/api/repos/proj/publish", json.dumps({}),
        )
        assert status == 403
        # strictcli's refusal, forwarded verbatim: it names the command and
        # says the call has to carry confirmation.
        assert "consequential" in body["error"]
        assert "confirmation" in body["error"]
        assert recorder.pushes == []

    def test_a_post_with_consent_publishes(self, live, recorder):
        status, body = _request(
            live, "POST", "/api/repos/proj/publish",
            json.dumps({"approve_consequential": True}),
        )
        assert status == 200
        assert body["ok"] is True
        assert "Published 2 post(s)" in body["stdout"]
        assert len(recorder.pushes) == 1

    def test_explicit_false_is_still_a_refusal(self, live, recorder):
        status, _body = _request(
            live, "POST", "/api/repos/proj/publish",
            json.dumps({"approve_consequential": False}),
        )
        assert status == 403
        assert recorder.pushes == []

    def test_a_non_boolean_consent_is_refused(self, live, recorder):
        status, body = _request(
            live, "POST", "/api/repos/proj/publish",
            json.dumps({"approve_consequential": "yes"}),
        )
        assert status == 400
        assert "true or false" in body["error"]
        assert recorder.pushes == []

    def test_a_body_that_is_not_json_is_refused(self, live, recorder):
        status, body = _request(
            live, "POST", "/api/repos/proj/publish", "not json",
        )
        assert status == 400
        assert "not JSON" in body["error"]
        assert recorder.pushes == []

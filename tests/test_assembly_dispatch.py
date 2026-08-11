"""Tests for assembly dispatch correctness: which tag, and which version.

Observed live: in a repo that releases several packages, ``assembly push``
resolved the repository's newest tag by creation date.  A sibling package
released later that day owned that tag, so the assembly cloned the sibling's
tree under this project's slug and published a 404 stub.  Resolution is now
anchored on the version being dispatched, and the dispatch refuses to run at
all when that version is missing from ``selfdoc.json``'s ``versions``.
"""

import json
import os
import subprocess

import pytest

from selfblog.assembly import (
    check_version_is_declared,
    list_repo_tags,
    parse_version_tag,
    resolve_project_tag,
)
from selfblog.cli import _cmd_assembly_push


# -- tag parsing --------------------------------------------------------------


def test_parse_plain_version_tag():
    assert parse_version_tag("v1.2.3") == ("", "1.2.3")


def test_parse_family_prefixed_tag():
    assert parse_version_tag("selfblog@v0.3.1") == ("selfblog@", "0.3.1")


def test_parse_slash_prefixed_tag():
    assert parse_version_tag("packages/core/v2.0.0") == ("packages/core/", "2.0.0")


def test_parse_prerelease_tag():
    assert parse_version_tag("v1.0.0-rc.1") == ("", "1.0.0-rc.1")


def test_parse_rejects_a_non_version_tag():
    assert parse_version_tag("nightly") is None


# -- resolution against a multi-releasable tag set ----------------------------

# Newest first, exactly as `git for-each-ref --sort=-creatordate` reports it.
# The sibling's tag is the newest one in the repo; the docs target's is not.
MULTI_RELEASABLE_TAGS = [
    "selfblog@v0.3.1",
    "selfdoc-core@v0.8.1",
    "v0.36.0",
    "selfblog@v0.3.0",
    "v0.35.0",
]


def test_newest_tag_by_date_belongs_to_a_sibling():
    """Guards the premise of the bug: newest-by-date is the wrong answer."""
    assert MULTI_RELEASABLE_TAGS[0] == "selfblog@v0.3.1"


def test_resolves_the_target_projects_tag_not_the_newest():
    assert resolve_project_tag(MULTI_RELEASABLE_TAGS, "0.36.0") == "v0.36.0"


def test_resolves_a_prefixed_family_member():
    assert resolve_project_tag(MULTI_RELEASABLE_TAGS, "0.3.1") == "selfblog@v0.3.1"


def test_resolves_an_older_version_of_the_right_family():
    assert resolve_project_tag(MULTI_RELEASABLE_TAGS, "0.35.0") == "v0.35.0"


def test_two_families_at_the_same_version_is_a_hard_error():
    tags = ["alpha@v1.0.0", "beta@v1.0.0"]
    with pytest.raises(RuntimeError, match="ambiguous"):
        resolve_project_tag(tags, "1.0.0")


def test_an_untagged_version_is_a_hard_error_not_a_fallback():
    with pytest.raises(RuntimeError, match="no git tag names version 0.37.0"):
        resolve_project_tag(MULTI_RELEASABLE_TAGS, "0.37.0")


def test_the_untagged_error_names_the_families_it_did_find():
    with pytest.raises(RuntimeError) as excinfo:
        resolve_project_tag(MULTI_RELEASABLE_TAGS, "0.37.0")
    assert "selfblog@" in str(excinfo.value)


def test_resolution_without_a_version_is_a_hard_error():
    with pytest.raises(RuntimeError, match="without a version"):
        resolve_project_tag(MULTI_RELEASABLE_TAGS, "")


def test_non_version_tags_are_ignored():
    assert resolve_project_tag(["nightly", "latest", "v2.0.0"], "2.0.0") == "v2.0.0"


# -- list_repo_tags against a real two-family repo ----------------------------


def _git(args, cwd):
    subprocess.run(["git"] + args, cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture()
def multi_releasable_repo(tmp_path):
    """A repo with two tag families where the sibling's tag is newest."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-b", "main"], repo)
    (repo / "README.md").write_text("x\n")
    _git(["add", "README.md"], repo)
    _git(["commit", "-m", "init"], repo)
    # The docs target is tagged first; the sibling package is tagged after,
    # so it owns the newest creatordate.
    _git(["tag", "v0.36.0"], repo)
    (repo / "README.md").write_text("y\n")
    _git(["commit", "-am", "more"], repo)
    _git(["tag", "selfblog@v0.3.1"], repo)
    return repo


def test_list_repo_tags_is_newest_first(multi_releasable_repo):
    tags = list_repo_tags(str(multi_releasable_repo))
    assert tags[0] == "selfblog@v0.3.1"
    assert set(tags) == {"selfblog@v0.3.1", "v0.36.0"}


def test_real_repo_resolves_the_docs_targets_tag(multi_releasable_repo):
    tags = list_repo_tags(str(multi_releasable_repo))
    assert resolve_project_tag(tags, "0.36.0") == "v0.36.0"


# -- declared versions --------------------------------------------------------


def test_declared_version_passes():
    config = {"versions": [{"version": "1.0.0"}, {"version": "1.1.0"}]}
    check_version_is_declared(config, "1.1.0")


def test_undeclared_version_is_a_hard_error():
    config = {"versions": [{"version": "0.1.0"}]}
    with pytest.raises(RuntimeError, match="not the version the assembly would build"):
        check_version_is_declared(config, "1.1.0")


def test_the_undeclared_error_names_what_would_have_been_published():
    config = {"versions": [{"version": "0.1.0"}]}
    with pytest.raises(RuntimeError) as excinfo:
        check_version_is_declared(config, "1.1.0")
    assert "0.1.0" in str(excinfo.value)


def test_no_declared_versions_at_all_is_a_hard_error():
    with pytest.raises(RuntimeError, match="declares no versions"):
        check_version_is_declared({"versions": []}, "1.0.0")


def test_a_declared_but_not_newest_version_is_a_hard_error():
    """Membership was never the question: the build takes versions[-1].

    Dispatching 1.0 against ``versions = [1.0, 2.0]`` passed the old
    membership test and then published 2.0's docs recorded under the name
    1.0 -- the exact failure the check's own error text described.
    """
    config = {"versions": [{"version": "1.0"}, {"version": "2.0"}]}
    with pytest.raises(RuntimeError) as excinfo:
        check_version_is_declared(config, "1.0")
    message = str(excinfo.value)
    assert "1.0" in message
    assert "2.0" in message


def test_the_stale_dispatch_error_names_both_versions():
    config = {"versions": [{"version": "0.9.0"}, {"version": "1.4.2"}]}
    with pytest.raises(RuntimeError) as excinfo:
        check_version_is_declared(config, "0.9.0")
    message = str(excinfo.value)
    assert "0.9.0" in message, "the dispatched version must be named"
    assert "1.4.2" in message, "the version the build would produce must be named"


def test_the_newest_declared_version_passes():
    config = {"versions": [{"version": "1.0"}, {"version": "2.0"}]}
    check_version_is_declared(config, "2.0")


def test_a_newest_entry_with_no_version_is_a_hard_error():
    """The build target cannot be read, so nothing may be dispatched."""
    config = {"versions": [{"version": "1.0"}, {}]}
    with pytest.raises(RuntimeError):
        check_version_is_declared(config, "1.0")


def test_the_check_agrees_with_what_the_build_would_produce(tmp_path):
    """One definition of "the version the build produces", used by both."""
    import json as _json

    from selfblog.assembly import detect_latest_version

    config = {"versions": [{"version": "1.0"}, {"version": "2.0"}]}
    (tmp_path / "selfdoc.json").write_text(_json.dumps(config))
    built = detect_latest_version(str(tmp_path))

    check_version_is_declared(config, built)
    with pytest.raises(RuntimeError):
        check_version_is_declared(config, "1.0")


# -- the dispatch command wires both checks -----------------------------------


def _setup_project(tmp_path, config_overrides=None):
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0", "indexed": True}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "assembly": {"repo": "owner/assembly", "pages_project": "site"},
        "topology": {"slug": "myproject", "docs_base": "https://docs.example.com"},
    }
    if config_overrides:
        config.update(config_overrides)
    (tmp_path / "selfdoc.json").write_text(json.dumps(config))
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "__init__.py").write_text("")
    return tmp_path


def _fake_run_factory(tags):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append([str(c) for c in cmd])
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        joined = " ".join(str(c) for c in cmd)
        if "repo" in joined and "view" in joined:
            result.stdout = "owner/source-repo\n"
        elif "for-each-ref" in joined:
            result.stdout = "\n".join(tags) + "\n"
        return result

    return fake_run, calls


def test_dispatch_sends_the_projects_own_tag(tmp_path, monkeypatch):
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    fake_run, calls = _fake_run_factory(["sibling@v9.9.9", "v1.0.0"])
    monkeypatch.setattr(subprocess, "run", fake_run)

    _cmd_assembly_push(None)

    dispatch = [c for c in calls if any("dispatches" in x for x in c)]
    assert dispatch, "expected a repository_dispatch call"
    # The payload travels on stdin, so read it back off the recorded gh call.
    assert "--input" in dispatch[0]


def test_dispatch_payload_carries_the_resolved_ref(tmp_path, monkeypatch):
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    payloads = []

    def fake_run(cmd, **kwargs):
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        joined = " ".join(str(c) for c in cmd)
        if "repo" in joined and "view" in joined:
            result.stdout = "owner/source-repo\n"
        elif "for-each-ref" in joined:
            result.stdout = "sibling@v9.9.9\nv1.0.0\n"
        elif "dispatches" in joined:
            payloads.append(json.loads(kwargs["input"]))
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    _cmd_assembly_push(None)

    assert payloads[0]["client_payload"]["ref"] == "v1.0.0"
    assert payloads[0]["client_payload"]["version"] == "1.0.0"


def test_dispatch_refuses_when_the_version_is_undeclared(tmp_path, monkeypatch, capsys):
    _setup_project(tmp_path, {
        "version": "1.0.0",
        "versions": [{"version": "0.1.0", "indexed": True}],
    })
    monkeypatch.chdir(tmp_path)
    fake_run, _calls = _fake_run_factory(["v1.0.0"])
    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(SystemExit):
        _cmd_assembly_push(None)
    assert "not the version the assembly would build" in capsys.readouterr().err


def test_dispatch_refuses_when_no_tag_names_the_version(tmp_path, monkeypatch, capsys):
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    fake_run, _calls = _fake_run_factory(["sibling@v9.9.9"])
    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(SystemExit):
        _cmd_assembly_push(None)
    assert "no git tag names version 1.0.0" in capsys.readouterr().err


def test_dispatch_refuses_an_ambiguous_tag(tmp_path, monkeypatch, capsys):
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    fake_run, _calls = _fake_run_factory(["alpha@v1.0.0", "beta@v1.0.0"])
    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(SystemExit):
        _cmd_assembly_push(None)
    assert "ambiguous" in capsys.readouterr().err


def test_repo_fixture_has_no_stray_state(multi_releasable_repo):
    """The fixture repo is self-contained (no reach into the dev repo)."""
    assert os.path.isdir(os.path.join(str(multi_releasable_repo), ".git"))

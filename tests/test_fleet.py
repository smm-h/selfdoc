"""Enumerating sibling selfdoc projects.

The enumeration used to live inside ``scripts/measure_lint_fleet.py``, where
the corpus-wide spelling run could not reach it.  It lives in
``selfdoc_core.fleet`` now, and both callers share it.  What is asserted
here is the hardening: a broken neighbour is reported, never fatal, and
nothing is written into a project being enumerated.
"""

from __future__ import annotations

import json
import os

from selfdoc_core.fleet import (
    FleetProject,
    discover_fleet,
    load_docs_bodies,
    project_dirs,
)

from conftest import default_config


def _project(root, name, config=None, docs=None):
    """Create a sibling project directory under *root*."""
    path = os.path.join(root, name)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "selfdoc.json"), "w", encoding="utf-8") as f:
        json.dump(default_config() if config is None else config, f)
    if docs:
        docs_dir = os.path.join(path, "docs")
        os.makedirs(docs_dir, exist_ok=True)
        for rel, content in docs.items():
            full = os.path.join(docs_dir, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
    return path


def test_project_dirs_finds_config_carrying_siblings(tmp_path):
    """A sibling is a directory holding a selfdoc.json, sorted by name."""
    _project(tmp_path, "beta")
    _project(tmp_path, "alpha")
    os.makedirs(tmp_path / "not-a-project", exist_ok=True)
    names = [os.path.basename(p) for p in project_dirs(str(tmp_path))]
    assert names == ["alpha", "beta"]


def test_project_dirs_skips_dot_directories(tmp_path):
    """Archives and caches under a dot-directory are not the fleet."""
    _project(tmp_path, ".archive")
    assert project_dirs(str(tmp_path)) == []


def test_project_dirs_on_a_missing_root_is_empty(tmp_path):
    """'No siblings' is a real answer, not an error."""
    assert project_dirs(str(tmp_path / "nowhere")) == []


def test_discover_fleet_loads_configs(tmp_path):
    """A healthy project comes back loaded and unsanitized."""
    _project(tmp_path, "alpha")
    found = discover_fleet(str(tmp_path))
    assert len(found) == 1
    assert found[0].loaded
    assert found[0].sanitized is False
    assert found[0].error is None


def test_discover_fleet_reports_a_broken_config_without_raising(tmp_path):
    """A broken neighbour must not stop a sweep over the rest of the fleet."""
    _project(tmp_path, "healthy")
    broken = os.path.join(tmp_path, "broken")
    os.makedirs(broken)
    with open(os.path.join(broken, "selfdoc.json"), "w", encoding="utf-8") as f:
        f.write("{ not json")

    found = {p.name: p for p in discover_fleet(str(tmp_path))}
    assert found["healthy"].loaded
    assert not found["broken"].loaded
    assert found["broken"].error


def test_discover_fleet_sanitizes_retired_keys(tmp_path):
    """A retired schema key is stale scaffolding, not a broken project."""
    config = default_config()
    config["versions"] = [{"version": "1.0.0", "indexed": True}]
    _project(tmp_path, "stale", config=config)

    found = discover_fleet(str(tmp_path))[0]
    assert found.loaded
    assert found.sanitized is True


def test_discover_fleet_never_writes_into_the_project(tmp_path):
    """The sanitized copy goes to a scratch directory, never to the project."""
    config = default_config()
    config["versions"] = [{"version": "1.0.0", "indexed": True}]
    path = _project(tmp_path, "stale", config=config)
    before = sorted(os.listdir(path))

    discover_fleet(str(tmp_path))

    assert sorted(os.listdir(path)) == before
    with open(os.path.join(path, "selfdoc.json"), encoding="utf-8") as f:
        assert json.load(f)["versions"][0]["indexed"] is True


def test_load_docs_bodies_returns_the_lint_slice_shape(tmp_path):
    """Frontmatter parsed, body raw, directives deliberately unresolved."""
    path = _project(tmp_path, "alpha", docs={
        "index.md": "---\ntitle: Home\n---\n\nBody text.\n",
    })
    bodies = load_docs_bodies(os.path.join(path, "docs"))
    metadata, resolved, body, fm_lines = bodies["index.md"]
    assert metadata["title"] == "Home"
    assert resolved == ""
    assert "Body text." in body
    # Delimiters plus the blank line separating frontmatter from the body.
    assert fm_lines == 4


def test_load_docs_bodies_skips_partials_and_build_output(tmp_path):
    """Underscore templates and _build artifacts are not pages."""
    path = _project(tmp_path, "alpha", docs={
        "index.md": "# Home\n",
        "_partial.md": "# Partial\n",
        "_build/stale.md": "# Stale\n",
    })
    bodies = load_docs_bodies(os.path.join(path, "docs"))
    assert set(bodies) == {"index.md"}


def test_load_docs_bodies_on_a_missing_tree_is_empty(tmp_path):
    """A project without a docs directory contributes nothing."""
    assert load_docs_bodies(str(tmp_path / "nope")) == {}


def test_fleet_project_loaded_tracks_the_config(tmp_path):
    """``loaded`` is exactly 'the config is present'."""
    assert FleetProject("x", "/x", {"a": 1}).loaded
    assert not FleetProject("x", "/x", None, error="boom").loaded

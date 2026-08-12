"""Tests for prune-instead-of-wipe and the declared roster.

A full project build used to replace its whole subtree in the assembly:
remove everything under ``site/<slug>/``, copy the build in.  Anything
published into that subtree between releases -- a post, a documentation
update -- was destroyed by the next release of the project it belonged to,
which is the reason out-of-band publishing could only ever be a posts-shaped
special case.

The build's output is a manifest now.  Every publisher records the paths it
produced, and removes only the ones it produced before and does not produce
now; everything else in the subtree belongs to somebody else and stays.

Membership went the same way: it used to accumulate as a side effect of
dispatch (``projects.json`` gained a key and nothing could ever remove one).
It is declared in ``roster.toml`` now, and the deploy reconciles to it.
"""

import json
import os

import pytest

from selfblog.assembly import (
    PUBLISH_OWNERS,
    RosterEntry,
    apply_project_files,
    build_output_paths,
    integrate_project,
    load_assembly_manifests,
    load_files_manifest,
    load_roster,
    merge_post_lists,
    parse_roster,
    prune_plan,
    reconcile_membership,
    render_files_manifest,
    render_roster,
)

from tests.test_assembly_integrate import (  # noqa: F401  (fixtures)
    CANONICAL_BASE,
    ROSTER,
    RunRecorder,
    _manifest,
    _page,
    _write,
    assembly_tree,
    runner,
)


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _integrate(root, **overrides):
    kwargs = dict(
        slug="alpha",
        version="1.0.0",
        ref="v1.0.0",
        source_repo="owner/alpha",
        scope="full",
        canonical_base=CANONICAL_BASE,
        assembly_dir=str(root),
        retry_delay=0,
        build=False,
    )
    kwargs.update(overrides)
    return integrate_project(**kwargs)


def _publish_a_post_out_of_band(root, slug="alpha", post="fresh"):
    """Do to the fixture tree what `post publish` does to the assembly repo.

    A post lands at the site level, at ``blog/<post-slug>/``, under no
    project slug -- which is why a release of the project that wrote it can
    reach it at all, and why the claim is what keeps it.
    """
    _write(str(root / "site" / "blog" / post / "index.html"),
           _page(post.title(), f"blog/{post}/", marker=post))
    record = root / "manifests" / f"{slug}-files.json"
    data = _read_json(str(record)) if record.exists() else {
        "schema_version": 2, "slug": slug, "owners": {},
    }
    owners = data.setdefault("owners", {})
    owners.setdefault("posts", []).append(f"blog/{post}/index.html")
    _write(str(record), json.dumps(data))
    _write(str(root / "manifests" / f"{slug}-posts.json"),
           json.dumps(_manifest(slug, slug.title(), "0.9.0", posts=[
               {"slug": post, "title": post.title(), "date": "2026-06-01"},
           ])))


# -- the produced set ---------------------------------------------------------


def test_build_output_paths_is_relative_and_slash_joined(assembly_tree):
    build = str(assembly_tree / "source" / "alpha" / "docs" / "_build")
    assert "guide/index.html" in build_output_paths(build)


def test_build_output_paths_excludes_deploy_artifacts(assembly_tree):
    build = str(assembly_tree / "source" / "alpha" / "docs" / "_build")
    produced = build_output_paths(build)
    assert "_headers" not in produced
    assert "index.html.gz" not in produced
    assert "guide/index.html.br" not in produced


def test_build_output_paths_of_a_missing_directory_is_empty(tmp_path):
    assert build_output_paths(str(tmp_path / "nope")) == set()


# -- the prune plan -----------------------------------------------------------


def test_a_path_the_build_dropped_is_pruned():
    owners = {"release": ["a.html", "gone.html"]}
    removed, updated = prune_plan(owners, "release", {"a.html"})
    assert removed == ["gone.html"]
    assert updated["release"] == ["a.html"]


def test_a_path_nobody_recorded_is_never_pruned():
    """This is the whole difference from a wipe: unknown means not mine."""
    owners = {"release": ["a.html"]}
    removed, _ = prune_plan(owners, "release", {"a.html"})
    assert removed == []


def test_another_publishers_current_path_is_never_pruned():
    owners = {"release": ["blog/x/index.html"], "posts": ["blog/x/index.html"]}
    removed, _ = prune_plan(owners, "release", set())
    assert removed == []


def test_the_pruning_publisher_only_touches_its_own_record():
    owners = {"release": ["a.html"], "docs": ["b.html"]}
    _removed, updated = prune_plan(owners, "release", {"c.html"})
    assert updated["docs"] == ["b.html"]
    assert updated["release"] == ["c.html"]


def test_an_unknown_publisher_is_a_hard_error():
    with pytest.raises(ValueError, match="unknown publisher"):
        prune_plan({}, "somebody", set())


def test_every_publisher_is_a_declared_one():
    assert PUBLISH_OWNERS == ("release", "docs", "posts")


# -- the published-file record ------------------------------------------------


def test_an_absent_record_is_an_empty_mapping(tmp_path):
    assert load_files_manifest(str(tmp_path / "nothing.json")) == {}


def test_a_corrupt_record_is_a_hard_error(tmp_path):
    path = str(tmp_path / "alpha-files.json")
    _write(path, "{not json")
    with pytest.raises(RuntimeError, match="not valid JSON"):
        load_files_manifest(path)


def test_a_record_naming_an_unknown_publisher_is_a_hard_error(tmp_path):
    path = str(tmp_path / "alpha-files.json")
    _write(path, json.dumps({
        "schema_version": 2, "owners": {"whoever": ["a.html"]},
    }))
    with pytest.raises(RuntimeError, match="unknown publisher"):
        load_files_manifest(path)


def test_a_rendered_record_round_trips(tmp_path):
    path = str(tmp_path / "alpha-files.json")
    _write(path, render_files_manifest("alpha", {"release": ["b.html", "a.html"]}))
    assert load_files_manifest(path) == {"release": ["a.html", "b.html"]}


def test_a_rendered_record_omits_publishers_that_published_nothing():
    data = json.loads(render_files_manifest("alpha", {"release": ["a"], "docs": []}))
    assert list(data["owners"]) == ["release"]


# -- a full build against out-of-band content ---------------------------------


def test_a_post_published_out_of_band_survives_a_full_build(assembly_tree):
    """The headline case: a release must not destroy a separately published post."""
    _publish_a_post_out_of_band(assembly_tree)
    apply_project_files(str(assembly_tree), str(assembly_tree / "source" / "alpha"),
                        "alpha", "full")
    survivor = assembly_tree / "site" / "blog" / "fresh" / "index.html"
    assert survivor.exists()
    with open(survivor, encoding="utf-8") as f:
        assert "fresh" in f.read()


def test_a_post_published_out_of_band_keeps_its_claim_after_a_full_build(assembly_tree):
    _publish_a_post_out_of_band(assembly_tree)
    apply_project_files(str(assembly_tree), str(assembly_tree / "source" / "alpha"),
                        "alpha", "full")
    owners = load_files_manifest(str(assembly_tree / "manifests" / "alpha-files.json"))
    assert owners["posts"] == ["blog/fresh/index.html"]


def test_a_page_the_new_build_dropped_is_pruned(assembly_tree):
    apply_project_files(str(assembly_tree), str(assembly_tree / "source" / "alpha"),
                        "alpha", "full")
    assert not (assembly_tree / "site" / "alpha" / "retired").exists()


def test_a_pruned_page_leaves_no_empty_directory_behind(assembly_tree):
    apply_project_files(str(assembly_tree), str(assembly_tree / "source" / "alpha"),
                        "alpha", "full")
    assert "retired" not in os.listdir(assembly_tree / "site" / "alpha")


def test_a_full_build_still_refreshes_the_pages_it_produces(assembly_tree):
    _publish_a_post_out_of_band(assembly_tree)
    apply_project_files(str(assembly_tree), str(assembly_tree / "source" / "alpha"),
                        "alpha", "full")
    with open(assembly_tree / "site" / "alpha" / "index.html", encoding="utf-8") as f:
        assert "new alpha" in f.read()


def test_a_full_integrate_leaves_an_out_of_band_post_alone(assembly_tree, runner):
    _publish_a_post_out_of_band(assembly_tree)
    _integrate(assembly_tree)
    assert (assembly_tree / "site" / "blog" / "fresh" / "index.html").exists()


def test_an_out_of_band_post_still_reaches_the_blog_index(assembly_tree, runner):
    """Surviving on disk is not enough; it has to keep its listing row."""
    _publish_a_post_out_of_band(assembly_tree)
    _integrate(assembly_tree)
    with open(assembly_tree / "site" / "blog" / "index.html", encoding="utf-8") as f:
        assert "Fresh" in f.read()


# -- the posts overlay --------------------------------------------------------


def test_merge_post_lists_keeps_posts_only_the_overlay_carries():
    merged = merge_post_lists([{"slug": "a"}, {"slug": "b"}], [{"slug": "c"}])
    assert [p["slug"] for p in merged] == ["a", "b", "c"]


def test_merge_post_lists_lets_the_build_win_on_a_shared_slug():
    merged = merge_post_lists([{"slug": "a", "title": "rebuilt"}],
                              [{"slug": "a", "title": "older"}])
    assert merged == [{"slug": "a", "title": "rebuilt"}]


def test_a_full_build_folds_its_posts_into_the_overlay(assembly_tree):
    """The overlay used to be deleted, taking out-of-band posts with it."""
    _publish_a_post_out_of_band(assembly_tree)
    apply_project_files(str(assembly_tree), str(assembly_tree / "source" / "alpha"),
                        "alpha", "full")
    overlay = _read_json(str(assembly_tree / "manifests" / "alpha-posts.json"))
    assert {p["slug"] for p in overlay["posts"]} == {"hello", "fresh"}


def test_the_overlay_still_replaces_the_base_post_list_when_read(assembly_tree):
    """Folding happens on write, so republishing can still remove a post."""
    manifests = load_assembly_manifests(str(assembly_tree / "manifests"))
    alpha = [m for m in manifests if m["slug"] == "alpha"][0]
    assert [p["slug"] for p in alpha["posts"]] == ["old-post"]


def test_the_published_file_record_is_not_read_as_a_manifest(assembly_tree):
    """`<slug>-files.json` lives under manifests/ but is not one."""
    slugs = [m["slug"] for m in load_assembly_manifests(str(assembly_tree / "manifests"))]
    assert sorted(slugs) == ["alpha", "beta", "home"]


# -- the roster ---------------------------------------------------------------


def test_a_rendered_roster_round_trips():
    entries = [RosterEntry("alpha", "owner/alpha"), RosterEntry("beta", "owner/beta")]
    roster = parse_roster(render_roster(entries, home="alpha"))
    assert dict(roster) == {"alpha": entries[0], "beta": entries[1]}
    assert roster.home == "alpha"


def test_a_roster_with_no_home_is_refused():
    """A site needs a front page, and no project is picked by default."""
    entries = [RosterEntry("alpha", "owner/alpha")]
    with pytest.raises(RuntimeError, match="carries no top-level 'home' key"):
        parse_roster(render_roster(entries))


def test_a_home_naming_an_undeclared_slug_is_refused():
    with pytest.raises(RuntimeError, match="no \\[\\[project\\]\\] block declares it"):
        parse_roster(
            'home = "ghost"\n[[project]]\nslug = "a"\nrepo = "o/a"\n'
        )


def test_an_empty_roster_declares_nobody_and_is_therefore_homeless():
    """An assembly with no projects cannot name one of them home."""
    with pytest.raises(RuntimeError, match="carries no top-level 'home' key"):
        parse_roster(render_roster([]))


def test_an_unknown_key_on_a_block_is_a_hard_error():
    with pytest.raises(RuntimeError, match="unknown key"):
        parse_roster(
            'home = "a"\n[[project]]\nslug = "a"\nrepo = "o/a"\nrfe = "typo"\n'
        )


def test_an_unknown_top_level_key_is_a_hard_error():
    with pytest.raises(RuntimeError, match="unknown top-level key"):
        parse_roster('projects = []\n')


def test_a_block_missing_a_required_key_is_a_hard_error():
    with pytest.raises(RuntimeError, match="missing repo"):
        parse_roster('home = "a"\n[[project]]\nslug = "a"\n')


def test_an_empty_required_value_is_a_hard_error():
    with pytest.raises(RuntimeError, match="missing repo"):
        parse_roster('home = "a"\n[[project]]\nslug = "a"\nrepo = ""\n')


def test_a_duplicate_slug_is_a_hard_error():
    with pytest.raises(RuntimeError, match="repeats the slug"):
        parse_roster(
            'home = "a"\n'
            '[[project]]\nslug = "a"\nrepo = "o/a"\n'
            '[[project]]\nslug = "a"\nrepo = "o/b"\n'
        )


def test_a_slug_colliding_with_an_assembly_directory_is_a_hard_error():
    with pytest.raises(RuntimeError, match="assembly's own directories"):
        parse_roster('home = "blog"\n[[project]]\nslug = "blog"\nrepo = "o/blog"\n')


def test_invalid_toml_is_a_hard_error():
    with pytest.raises(RuntimeError, match="not valid TOML"):
        parse_roster("[[project]\n")


def test_a_missing_roster_file_is_a_hard_error_with_guidance(tmp_path):
    with pytest.raises(RuntimeError, match=r"\[\[project\]\]"):
        load_roster(str(tmp_path))


def test_the_assembly_scaffold_ships_a_roster():
    from selfblog.assembly import ROSTER_PATH, ToolchainPins, assembly_init

    files = assembly_init(
        "owner/assembly", "pages", "https://docs.example.com", "",
        ToolchainPins(selfblog="1", selfdoc="2", pagefind="3"),
    )
    assert ROSTER_PATH in files
    # The scaffolded roster names no home: a fresh assembly declares no
    # projects, so there is nothing to name, and reading it says exactly
    # that rather than picking one.
    assert 'home = "<slug>"' in files[ROSTER_PATH]
    with pytest.raises(RuntimeError, match="carries no top-level 'home' key"):
        parse_roster(files[ROSTER_PATH])


# -- reconciliation -----------------------------------------------------------


def test_an_undeclared_project_loses_its_subtree(assembly_tree):
    reconcile_membership(str(assembly_tree), {"alpha": ROSTER["alpha"]})
    assert not (assembly_tree / "site" / "beta").exists()
    assert (assembly_tree / "site" / "alpha").exists()


def test_an_undeclared_project_loses_every_manifest_kind(assembly_tree):
    _write(str(assembly_tree / "manifests" / "beta-posts.json"),
           json.dumps(_manifest("beta", "Beta", "2.0.0")))
    _write(str(assembly_tree / "manifests" / "beta-revisions.json"), "{}")
    _write(str(assembly_tree / "manifests" / "beta-files.json"),
           json.dumps({"schema_version": 2, "slug": "beta", "owners": {}}))
    reconcile_membership(str(assembly_tree), {"alpha": ROSTER["alpha"]})
    left = os.listdir(assembly_tree / "manifests")
    assert not [name for name in left if name.startswith("beta")]
    assert "alpha.json" in left


def test_an_undeclared_project_loses_its_membership_record(assembly_tree):
    reconcile_membership(
        str(assembly_tree),
        {"alpha": ROSTER["alpha"], "home": ROSTER["home"]},
    )
    assert list(_read_json(str(assembly_tree / "projects.json"))) == [
        "alpha", "home",
    ]


def test_reconciliation_reports_what_it_retired(assembly_tree):
    summary = reconcile_membership(
        str(assembly_tree),
        {"alpha": ROSTER["alpha"], "home": ROSTER["home"]},
    )
    assert summary["retired"] == ["beta"]
    assert any("site" in path and path.endswith("beta") for path in summary["removed"])


def test_reconciliation_drops_the_stale_search_index(assembly_tree):
    """pagefind keys fragments by hash, so a removed page can linger in it."""
    _write(str(assembly_tree / "site" / "pagefind" / "pagefind.js"), "// index")
    reconcile_membership(str(assembly_tree), {"alpha": ROSTER["alpha"]})
    assert not (assembly_tree / "site" / "pagefind").exists()


def test_reconciliation_keeps_the_index_when_nothing_was_retired(assembly_tree):
    _write(str(assembly_tree / "site" / "pagefind" / "pagefind.js"), "// index")
    reconcile_membership(str(assembly_tree), ROSTER)
    assert (assembly_tree / "site" / "pagefind").exists()


def test_reconciliation_never_mistakes_a_shared_directory_for_a_project(assembly_tree):
    _write(str(assembly_tree / "site" / "blog" / "index.html"), "<html>blog</html>")
    _write(str(assembly_tree / "site" / "projects" / "index.html"), "<html>list</html>")
    reconcile_membership(str(assembly_tree), ROSTER)
    assert (assembly_tree / "site" / "blog" / "index.html").exists()
    assert (assembly_tree / "site" / "projects" / "index.html").exists()


def test_reconciliation_removes_a_manifest_no_declared_project_owns(assembly_tree):
    _write(str(assembly_tree / "manifests" / "ghost.json"),
           json.dumps(_manifest("ghost", "Ghost", "1.0.0")))
    reconcile_membership(str(assembly_tree), ROSTER)
    assert not (assembly_tree / "manifests" / "ghost.json").exists()


def test_reconciliation_is_a_no_op_when_everything_is_declared(assembly_tree):
    before = sorted(os.listdir(assembly_tree / "manifests"))
    summary = reconcile_membership(str(assembly_tree), ROSTER)
    assert summary["retired"] == []
    assert sorted(os.listdir(assembly_tree / "manifests")) == before


# -- reconciliation inside the deploy -----------------------------------------


def test_an_integrate_removes_every_trace_of_a_project_left_off_the_roster(
    assembly_tree, runner,
):
    _write(str(assembly_tree / "roster.toml"),
           render_roster([ROSTER["alpha"], ROSTER["home"]], home="home"))
    _integrate(assembly_tree)
    assert not (assembly_tree / "site" / "beta").exists()
    assert not (assembly_tree / "manifests" / "beta.json").exists()
    assert list(_read_json(str(assembly_tree / "projects.json"))) == [
        "alpha", "home",
    ]


def test_a_retired_project_loses_its_listing_row(assembly_tree, runner):
    _write(str(assembly_tree / "roster.toml"),
           render_roster([ROSTER["alpha"], ROSTER["home"]], home="home"))
    _integrate(assembly_tree)
    nav = _read_json(str(assembly_tree / "site" / "nav.json"))
    assert [p["slug"] for p in nav["projects"]] == ["alpha"]
    with open(assembly_tree / "site" / "index.html", encoding="utf-8") as f:
        assert "Beta" not in f.read()


def test_a_retired_project_is_reindexed_out(assembly_tree, runner):
    _write(str(assembly_tree / "site" / "pagefind" / "pagefind.js"), "// index")
    _write(str(assembly_tree / "roster.toml"),
           render_roster([ROSTER["alpha"], ROSTER["home"]], home="home"))
    _integrate(assembly_tree)
    pagefind = [c for c in runner.calls if "pagefind" in " ".join(c)]
    assert pagefind, "the index has to be rebuilt after a retirement"


def test_a_shared_only_dispatch_reconciles_too(assembly_tree, runner):
    """Retirement lands through the shared-only pass `assembly retire` fires."""
    _write(str(assembly_tree / "roster.toml"),
           render_roster([ROSTER["alpha"], ROSTER["home"]], home="home"))
    _integrate(assembly_tree, scope="shared-only", slug="")
    assert not (assembly_tree / "site" / "beta").exists()


def test_an_integrate_of_an_undeclared_project_is_a_hard_error(assembly_tree, runner):
    _write(str(assembly_tree / "roster.toml"),
           render_roster([ROSTER["beta"], ROSTER["home"]], home="home"))
    with pytest.raises(RuntimeError, match="not declared in roster.toml"):
        _integrate(assembly_tree)


def test_an_integrate_without_a_roster_is_a_hard_error(assembly_tree, runner):
    os.remove(assembly_tree / "roster.toml")
    with pytest.raises(RuntimeError, match="does not exist"):
        _integrate(assembly_tree)


def test_an_undeclared_project_is_not_deleted_before_the_refusal(assembly_tree, runner):
    """The refusal comes first, so a mis-typed dispatch destroys nothing."""
    _write(str(assembly_tree / "roster.toml"),
           render_roster([ROSTER["beta"], ROSTER["home"]], home="home"))
    with pytest.raises(RuntimeError):
        _integrate(assembly_tree)
    assert (assembly_tree / "site" / "alpha" / "index.html").exists()

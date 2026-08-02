from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from migrate_topology import (
    add_cross_links,
    build_projects_map,
    discover_projects,
    main,
    missing_pages_project,
    to_kebab,
    update_config,
)


class TestToKebab:
    def test_simple(self):
        assert to_kebab("MyProject") == "myproject"

    def test_underscores(self):
        assert to_kebab("my_cool_project") == "my-cool-project"

    def test_spaces(self):
        assert to_kebab("My Cool Project") == "my-cool-project"

    def test_special_chars(self):
        assert to_kebab("foo.bar@baz!") == "foobarbaz"

    def test_multiple_hyphens_collapsed(self):
        assert to_kebab("foo---bar") == "foo-bar"

    def test_leading_trailing_hyphens_stripped(self):
        assert to_kebab("-foo-") == "foo"

    def test_mixed(self):
        assert to_kebab("My__Project--Name  v2") == "my-project-name-v2"

    def test_already_kebab(self):
        assert to_kebab("already-kebab") == "already-kebab"

    def test_numbers(self):
        assert to_kebab("project123") == "project123"

    def test_empty(self):
        assert to_kebab("") == ""

    def test_only_special(self):
        assert to_kebab("@#$%") == ""


class TestDiscoverProjects:
    def test_finds_projects(self, tmp_path):
        proj_a = tmp_path / "alpha"
        proj_a.mkdir()
        (proj_a / "selfdoc.json").write_text("{}")

        proj_b = tmp_path / "beta"
        proj_b.mkdir()
        (proj_b / "selfdoc.json").write_text("{}")

        # No selfdoc.json -- should be skipped
        (tmp_path / "gamma").mkdir()

        result = discover_projects(str(tmp_path))
        assert len(result) == 2
        assert str(proj_a) in result
        assert str(proj_b) in result

    def test_ignores_files(self, tmp_path):
        (tmp_path / "not-a-dir").write_text("hello")
        (tmp_path / "not-a-dir-selfdoc.json").write_text("{}")

        result = discover_projects(str(tmp_path))
        assert result == []

    def test_nonexistent_dir(self, tmp_path):
        result = discover_projects(str(tmp_path / "nonexistent"))
        assert result == []

    def test_sorted_order(self, tmp_path):
        for name in ["zebra", "alpha", "middle"]:
            d = tmp_path / name
            d.mkdir()
            (d / "selfdoc.json").write_text("{}")

        result = discover_projects(str(tmp_path))
        basenames = [os.path.basename(p) for p in result]
        assert basenames == ["alpha", "middle", "zebra"]


class TestUpdateConfig:
    def test_adds_topology_to_empty(self):
        config = {}
        result = update_config(config, "my-proj", "https://docs.example.com", None, "org/assembly")

        assert result["topology"]["slug"] == "my-proj"
        assert result["topology"]["docs_base"] == "https://docs.example.com"
        assert "posts_base" not in result["topology"]
        assert "assembly" not in result["topology"]
        assert result["assembly"]["repo"] == "org/assembly"

    def test_adds_posts_base(self):
        config = {}
        result = update_config(
            config, "proj", "https://docs.example.com",
            "https://docs.example.com/blog", "org/asm",
        )

        assert result["topology"]["posts_base"] == "https://docs.example.com/blog"

    def test_preserves_existing_fields(self):
        config = {
            "source": "python",
            "description": "A project",
            "docs": {"input": "docs"},
        }
        result = update_config(config, "proj", "https://d.com", None, "org/a")

        assert result["source"] == "python"
        assert result["description"] == "A project"
        assert result["docs"] == {"input": "docs"}
        assert "topology" in result

    def test_updates_existing_topology(self):
        config = {
            "topology": {
                "slug": "old-slug",
                "docs_base": "https://old.com",
                "extra_field": "preserved",
            }
        }
        result = update_config(config, "new-slug", "https://new.com", None, "org/a")

        assert result["topology"]["slug"] == "new-slug"
        assert result["topology"]["docs_base"] == "https://new.com"
        assert result["topology"]["extra_field"] == "preserved"

    def test_updates_existing_assembly(self):
        config = {"assembly": {"repo": "old/repo", "extra": "kept"}}
        result = update_config(config, "p", "https://d.com", None, "new/repo")

        assert result["assembly"]["repo"] == "new/repo"
        assert result["assembly"]["extra"] == "kept"


class TestMissingPagesProject:
    def test_repo_only_is_missing(self):
        assert missing_pages_project({"assembly": {"repo": "org/asm"}}) is True

    def test_configured_is_not_missing(self):
        config = {"assembly": {"repo": "org/asm", "pages_project": "site"}}
        assert missing_pages_project(config) is False

    def test_empty_value_is_missing(self):
        config = {"assembly": {"repo": "org/asm", "pages_project": ""}}
        assert missing_pages_project(config) is True

    def test_no_assembly_block_is_not_missing(self):
        assert missing_pages_project({}) is False

    def test_non_dict_assembly_is_not_missing(self):
        assert missing_pages_project({"assembly": "org/asm"}) is False

    def test_migrated_config_is_missing(self):
        """update_config alone never produces a complete assembly block."""
        config = update_config({}, "proj", "https://d.com", None, "org/asm")
        assert missing_pages_project(config) is True


class TestMainWarnsAboutPagesProject:
    def test_warns_naming_the_key_and_its_consumers(self, tmp_path, capsys):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "selfdoc.json").write_text(json.dumps({"source": "python"}))

        main([
            "--docs-base", "https://docs.example.com",
            "--assembly-repo", "org/asm",
            "--projects-dir", str(tmp_path),
        ])

        err = capsys.readouterr().err
        assert "assembly.pages_project" in err
        assert "proj" in err
        # Names where the key is consumed, so the reader knows what breaks.
        assert "assembly init" in err
        assert "deploy workflow" in err

    def test_silent_when_pages_project_already_set(self, tmp_path, capsys):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "selfdoc.json").write_text(
            json.dumps({"assembly": {"pages_project": "site"}})
        )

        main([
            "--docs-base", "https://docs.example.com",
            "--assembly-repo", "org/asm",
            "--projects-dir", str(tmp_path),
        ])

        err = capsys.readouterr().err
        assert "pages_project" not in err

    def test_migration_preserves_existing_pages_project(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "selfdoc.json").write_text(
            json.dumps({"assembly": {"repo": "old/repo", "pages_project": "site"}})
        )

        main([
            "--docs-base", "https://docs.example.com",
            "--assembly-repo", "org/asm",
            "--projects-dir", str(tmp_path),
        ])

        config = json.loads((proj / "selfdoc.json").read_text())
        assert config["assembly"] == {"repo": "org/asm", "pages_project": "site"}


class TestBuildProjectsMap:
    def test_builds_map(self):
        projects = [("alpha", "/path/alpha"), ("beta", "/path/beta")]
        result = build_projects_map(projects, "https://docs.example.com")

        assert result == {
            "alpha": "https://docs.example.com/alpha",
            "beta": "https://docs.example.com/beta",
        }

    def test_trailing_slash_on_base(self):
        projects = [("proj", "/p")]
        result = build_projects_map(projects, "https://docs.example.com/")

        assert result["proj"] == "https://docs.example.com/proj"

    def test_empty(self):
        assert build_projects_map([], "https://d.com") == {}


class TestAddCrossLinks:
    def test_excludes_self(self):
        projects_map = {
            "alpha": "https://d.com/alpha",
            "beta": "https://d.com/beta",
            "gamma": "https://d.com/gamma",
        }
        config = {"topology": {"slug": "beta"}}
        result = add_cross_links(config, "beta", projects_map)

        assert "beta" not in result["topology"]["projects"]
        assert result["topology"]["projects"]["alpha"] == "https://d.com/alpha"
        assert result["topology"]["projects"]["gamma"] == "https://d.com/gamma"

    def test_preserves_other_topology_fields(self):
        config = {"topology": {"slug": "a", "docs_base": "https://d.com"}}
        result = add_cross_links(config, "a", {"b": "https://d.com/b"})

        assert result["topology"]["slug"] == "a"
        assert result["topology"]["docs_base"] == "https://d.com"
        assert result["topology"]["projects"] == {"b": "https://d.com/b"}

    def test_creates_topology_if_missing(self):
        config = {}
        result = add_cross_links(config, "x", {"y": "https://d.com/y"})

        assert result["topology"]["projects"] == {"y": "https://d.com/y"}


class TestIdempotency:
    def test_running_twice_produces_same_result(self):
        config = {"source": "python"}
        first = update_config(
            config.copy(), "proj", "https://d.com", "https://d.com/blog", "org/asm"
        )
        second = update_config(
            json.loads(json.dumps(first)), "proj", "https://d.com",
            "https://d.com/blog", "org/asm",
        )
        assert first == second


class TestIntegration:
    def test_full_migration(self, tmp_path):
        # Set up two projects
        proj_a = tmp_path / "project_alpha"
        proj_a.mkdir()
        (proj_a / "selfdoc.json").write_text(json.dumps({"source": "python"}))

        proj_b = tmp_path / "project-beta"
        proj_b.mkdir()
        (proj_b / "selfdoc.json").write_text(json.dumps({"source": "go", "docs": {}}))

        # Discover
        dirs = discover_projects(str(tmp_path))
        assert len(dirs) == 2

        # First pass
        project_info = []
        for proj_dir in dirs:
            with open(os.path.join(proj_dir, "selfdoc.json")) as f:
                config = json.load(f)
            slug = to_kebab(os.path.basename(proj_dir))
            project_info.append((slug, proj_dir))
            update_config(config, slug, "https://docs.test.com", None, "org/docs")
            with open(os.path.join(proj_dir, "selfdoc.json"), "w") as f:
                json.dump(config, f, indent=2)
                f.write("\n")

        # Second pass
        projects_map = build_projects_map(project_info, "https://docs.test.com")
        for slug, proj_dir in project_info:
            with open(os.path.join(proj_dir, "selfdoc.json")) as f:
                config = json.load(f)
            add_cross_links(config, slug, projects_map)
            with open(os.path.join(proj_dir, "selfdoc.json"), "w") as f:
                json.dump(config, f, indent=2)
                f.write("\n")

        # Verify project_alpha
        with open(proj_a / "selfdoc.json") as f:
            cfg_a = json.load(f)
        assert cfg_a["source"] == "python"
        assert cfg_a["topology"]["slug"] == "project-alpha"
        assert cfg_a["topology"]["docs_base"] == "https://docs.test.com"
        assert "posts_base" not in cfg_a["topology"]
        assert "assembly" not in cfg_a["topology"]
        assert cfg_a["assembly"]["repo"] == "org/docs"
        assert "project-alpha" not in cfg_a["topology"]["projects"]
        assert cfg_a["topology"]["projects"]["project-beta"] == "https://docs.test.com/project-beta"

        # Verify project-beta
        with open(proj_b / "selfdoc.json") as f:
            cfg_b = json.load(f)
        assert cfg_b["source"] == "go"
        assert cfg_b["docs"] == {}
        assert cfg_b["topology"]["slug"] == "project-beta"
        assert "project-beta" not in cfg_b["topology"]["projects"]
        assert cfg_b["topology"]["projects"]["project-alpha"] == "https://docs.test.com/project-alpha"

    def test_skips_invalid_json(self, tmp_path):
        bad = tmp_path / "bad-proj"
        bad.mkdir()
        (bad / "selfdoc.json").write_text("not json{{{")

        good = tmp_path / "good-proj"
        good.mkdir()
        (good / "selfdoc.json").write_text(json.dumps({"ok": True}))

        dirs = discover_projects(str(tmp_path))
        assert len(dirs) == 2

        # The migration logic should skip the bad one
        project_info = []
        for proj_dir in dirs:
            config_path = os.path.join(proj_dir, "selfdoc.json")
            try:
                with open(config_path) as f:
                    config = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            slug = to_kebab(os.path.basename(proj_dir))
            project_info.append((slug, proj_dir))
            update_config(config, slug, "https://d.com", None, "org/a")
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
                f.write("\n")

        assert len(project_info) == 1
        assert project_info[0][0] == "good-proj"

    def test_posts_base_optional(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "selfdoc.json").write_text("{}")

        with open(proj / "selfdoc.json") as f:
            config = json.load(f)
        update_config(config, "proj", "https://d.com", None, "org/a")

        assert "posts_base" not in config["topology"]

        # Now with posts_base
        config2 = {}
        update_config(config2, "proj", "https://d.com", "https://d.com/blog", "org/a")
        assert config2["topology"]["posts_base"] == "https://d.com/blog"

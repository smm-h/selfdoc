"""Tests for topology-aware root file generation."""

import json
import os

import pytest

from selfdoc.gen import generate_root_files


def _make_config(tmp_path, root_files=None, topology=None):
    """Create a minimal config with optional topology and root_files."""
    lib_dir = os.path.join(tmp_path, "mylib")
    os.makedirs(lib_dir, exist_ok=True)
    with open(os.path.join(lib_dir, "__init__.py"), "w") as f:
        f.write('"""My library."""\n')

    os.makedirs(os.path.join(tmp_path, "docs"), exist_ok=True)

    config = {
        "source": [{"path": "mylib/", "language": "python"}],
        "docs": "docs/",
        "output": "docs/_build/",
    }
    if root_files is not None:
        config["root_files"] = root_files
    if topology is not None:
        config["topology"] = topology

    config_path = os.path.join(tmp_path, "selfdoc.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    return config


class TestTopologyVarInRootFiles:
    """Topology var directives resolve correctly in root file templates."""

    def test_docs_url_resolved(self, tmp_path):
        """topology.docs_url resolves to docs_base/slug in templates."""
        config = _make_config(
            tmp_path,
            root_files=["docs/_TEST.md"],
            topology={"docs_base": "https://docs.smmh.dev", "slug": "mylib"},
        )

        template = (
            "---\ntitle: Test\n---\n"
            "Docs: :-: var key=\"topology.docs_url\"\n"
        )
        template_path = os.path.join(tmp_path, "docs", "_TEST.md")
        with open(template_path, "w") as f:
            f.write(template)
        generate_root_files(config, base_dir=str(tmp_path))

        output_path = os.path.join(tmp_path, "TEST.md")
        with open(output_path) as f:
            content = f.read()
        assert "https://docs.smmh.dev/mylib" in content

    def test_posts_url_resolved(self, tmp_path):
        """topology.posts_url resolves to posts_base in templates."""
        config = _make_config(
            tmp_path,
            root_files=["docs/_TEST.md"],
            topology={"posts_base": "https://docs.smmh.dev/blog"},
        )

        template = (
            "---\ntitle: Test\n---\n"
            "Blog: :-: var key=\"topology.posts_url\"\n"
        )
        template_path = os.path.join(tmp_path, "docs", "_TEST.md")
        with open(template_path, "w") as f:
            f.write(template)
        generate_root_files(config, base_dir=str(tmp_path))

        output_path = os.path.join(tmp_path, "TEST.md")
        with open(output_path) as f:
            content = f.read()
        assert "https://docs.smmh.dev/blog" in content

    def test_slug_resolved(self, tmp_path):
        """topology.slug resolves to the slug value in templates."""
        config = _make_config(
            tmp_path,
            root_files=["docs/_TEST.md"],
            topology={"slug": "mylib"},
        )

        template = (
            "---\ntitle: Test\n---\n"
            "Slug: :-: var key=\"topology.slug\"\n"
        )
        template_path = os.path.join(tmp_path, "docs", "_TEST.md")
        with open(template_path, "w") as f:
            f.write(template)
        generate_root_files(config, base_dir=str(tmp_path))

        output_path = os.path.join(tmp_path, "TEST.md")
        with open(output_path) as f:
            content = f.read()
        assert "Slug: mylib" in content

    def test_topology_absent_returns_empty(self, tmp_path):
        """Without topology, var keys resolve to empty strings."""
        config = _make_config(tmp_path, root_files=["docs/_TEST.md"])

        template = (
            "---\ntitle: Test\n---\n"
            "Docs: [:-: var key=\"topology.docs_url\"]end\n"
        )
        template_path = os.path.join(tmp_path, "docs", "_TEST.md")
        with open(template_path, "w") as f:
            f.write(template)
        generate_root_files(config, base_dir=str(tmp_path))

        output_path = os.path.join(tmp_path, "TEST.md")
        with open(output_path) as f:
            content = f.read()
        assert "[]end" in content

    def test_multiple_topology_vars(self, tmp_path):
        """Multiple topology var directives in one template all resolve."""
        config = _make_config(
            tmp_path,
            root_files=["docs/_TEST.md"],
            topology={
                "docs_base": "https://docs.smmh.dev",
                "slug": "mylib",
                "posts_base": "https://docs.smmh.dev/blog",
            },
        )

        template = (
            "---\ntitle: Test\n---\n"
            "# Project\n\n"
            "Docs: :-: var key=\"topology.docs_url\"\n\n"
            "Blog: :-: var key=\"topology.posts_url\"\n\n"
            "Slug: :-: var key=\"topology.slug\"\n"
        )
        template_path = os.path.join(tmp_path, "docs", "_TEST.md")
        with open(template_path, "w") as f:
            f.write(template)
        generate_root_files(config, base_dir=str(tmp_path))

        output_path = os.path.join(tmp_path, "TEST.md")
        with open(output_path) as f:
            content = f.read()
        assert "https://docs.smmh.dev/mylib" in content
        assert "https://docs.smmh.dev/blog" in content
        assert "Slug: mylib" in content

    def test_topology_vars_with_existing_project_vars(self, tmp_path):
        """Topology vars work alongside existing project.* vars."""
        config = _make_config(
            tmp_path,
            root_files=["docs/_TEST.md"],
            topology={"docs_base": "https://docs.smmh.dev", "slug": "mylib"},
        )

        # Write a pyproject.toml so project.name resolves
        pyproject = os.path.join(tmp_path, "pyproject.toml")
        with open(pyproject, "w") as f:
            f.write('[project]\nname = "mylib"\nversion = "1.0.0"\n')

        template = (
            "---\ntitle: Test\n---\n"
            "Name: :-: var key=\"project.name\"\n\n"
            "Docs: :-: var key=\"topology.docs_url\"\n"
        )
        template_path = os.path.join(tmp_path, "docs", "_TEST.md")
        with open(template_path, "w") as f:
            f.write(template)
        generate_root_files(config, base_dir=str(tmp_path))

        output_path = os.path.join(tmp_path, "TEST.md")
        with open(output_path) as f:
            content = f.read()
        assert "Name: mylib" in content
        assert "https://docs.smmh.dev/mylib" in content

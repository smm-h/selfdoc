"""Tests for selfdoc.gen -- auto-generating documentation pages."""

import json
import os
import stat

import pytest

from selfdoc.gen import generate_docs, _has_generated_marker


@pytest.fixture()
def python_project(tmp_path):
    """Create a minimal Python project with selfdoc config and source files."""
    config = {
        "language": "python",
        "source": ["mylib/"],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
    }
    config_path = os.path.join(tmp_path, "selfdoc.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    # Source: mylib/__init__.py
    lib_dir = os.path.join(tmp_path, "mylib")
    os.makedirs(lib_dir)
    with open(os.path.join(lib_dir, "__init__.py"), "w") as f:
        f.write('"""My library."""\n')

    # Source: mylib/core.py
    with open(os.path.join(lib_dir, "core.py"), "w") as f:
        f.write('"""Core module."""\ndef main(): pass\n')

    # Source: mylib/utils.py
    with open(os.path.join(lib_dir, "utils.py"), "w") as f:
        f.write('"""Utilities."""\ndef helper(): pass\n')

    # Create docs/ directory
    os.makedirs(os.path.join(tmp_path, "docs"), exist_ok=True)

    return tmp_path


def _load_config(project_dir):
    """Load config from a project directory for testing."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return config


class TestBasicGeneration:
    """Test basic page generation from source files."""

    def test_generates_md_files(self, python_project):
        config = _load_config(python_project)
        generated = generate_docs(config, base_dir=str(python_project))

        assert len(generated) > 0
        docs_dir = os.path.join(python_project, "docs")
        for fname in generated:
            assert os.path.isfile(os.path.join(docs_dir, fname))

    def test_correct_filenames(self, python_project):
        config = _load_config(python_project)
        generated = generate_docs(config, base_dir=str(python_project))

        # Should have pages for mylib.core, mylib.utils, and mylib (__init__)
        # plus gen-index.md
        filenames = set(generated)
        assert "mylib-core.md" in filenames
        assert "mylib-utils.md" in filenames
        assert "mylib.md" in filenames
        assert "gen-index.md" in filenames

    def test_generated_content(self, python_project):
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        with open(os.path.join(docs_dir, "mylib-core.md"), "r") as f:
            content = f.read()

        assert "title: mylib.core" in content
        # Module has a docstring ("Core module."), so it should be used
        assert "Core module." in content
        assert "# mylib.core" in content
        assert ':-: ref path="mylib.core"' in content


class TestFrontmatter:
    """Test generated frontmatter content."""

    def test_has_generated_true(self, python_project):
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        with open(os.path.join(docs_dir, "mylib-core.md"), "r") as f:
            content = f.read()

        assert "generated: true" in content

    def test_generated_marker_detected(self, python_project):
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        assert _has_generated_marker(os.path.join(docs_dir, "mylib-core.md"))

    def test_non_generated_marker_not_detected(self, python_project):
        docs_dir = os.path.join(python_project, "docs")
        handwritten = os.path.join(docs_dir, "manual.md")
        with open(handwritten, "w") as f:
            f.write("---\ntitle: Manual\n---\n# Manual page\n")

        assert not _has_generated_marker(handwritten)

    def test_has_nav_group(self, python_project):
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        with open(os.path.join(docs_dir, "mylib-core.md"), "r") as f:
            content = f.read()

        assert 'nav_group: "API Reference"' in content

    def test_has_nav_order(self, python_project):
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        with open(os.path.join(docs_dir, "mylib-core.md"), "r") as f:
            content = f.read()

        assert "nav_order:" in content

    def test_gen_index_nav_order_zero(self, python_project):
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        with open(os.path.join(docs_dir, "gen-index.md"), "r") as f:
            content = f.read()

        assert 'nav_group: "API Reference"' in content
        assert "nav_order: 0" in content
        assert "order: 90" in content


class TestHtmlComment:
    """Test that generated pages contain the HTML comment marker."""

    def test_comment_present(self, python_project):
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        with open(os.path.join(docs_dir, "mylib-core.md"), "r") as f:
            content = f.read()

        assert "<!-- generated by selfdoc gen, do not edit -->" in content


class TestFilePermissions:
    """Test that generated files have read-only permissions."""

    def test_permissions_are_readonly(self, python_project):
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        core_path = os.path.join(docs_dir, "mylib-core.md")
        mode = os.stat(core_path).st_mode
        assert mode & stat.S_IRUSR  # owner can read
        assert mode & stat.S_IRGRP  # group can read
        assert mode & stat.S_IROTH  # others can read
        assert not (mode & stat.S_IWUSR)  # owner cannot write
        assert not (mode & stat.S_IWGRP)  # group cannot write
        assert not (mode & stat.S_IWOTH)  # others cannot write


class TestExclusions:
    """Test exclusion pattern handling."""

    def test_default_excludes_test_files(self, python_project):
        lib_dir = os.path.join(python_project, "mylib")
        with open(os.path.join(lib_dir, "test_core.py"), "w") as f:
            f.write("def test_something(): pass\n")

        config = _load_config(python_project)
        generated = generate_docs(config, base_dir=str(python_project))

        filenames = set(generated)
        assert "mylib-test_core.md" not in filenames

    def test_default_excludes_pycache(self, python_project):
        cache_dir = os.path.join(python_project, "mylib", "__pycache__")
        os.makedirs(cache_dir)
        with open(os.path.join(cache_dir, "core.cpython-311.pyc"), "w") as f:
            f.write("")

        config = _load_config(python_project)
        generated = generate_docs(config, base_dir=str(python_project))

        # __pycache__ files should not generate any pages
        for fname in generated:
            assert "pycache" not in fname

    def test_user_exclude_patterns(self, python_project):
        # Add a file that would normally be included
        lib_dir = os.path.join(python_project, "mylib")
        with open(os.path.join(lib_dir, "internal.py"), "w") as f:
            f.write("# internal module\n")

        # Configure exclusion
        config = _load_config(python_project)
        config["gen"] = {"exclude": ["**/internal.*"]}
        generated = generate_docs(config, base_dir=str(python_project))

        filenames = set(generated)
        assert "mylib-internal.md" not in filenames


class TestHandwrittenPages:
    """Test that hand-written pages are never overwritten."""

    def test_skip_handwritten(self, python_project):
        docs_dir = os.path.join(python_project, "docs")

        # Create a hand-written page with the same name gen would produce
        handwritten = os.path.join(docs_dir, "mylib-core.md")
        with open(handwritten, "w") as f:
            f.write(
                "---\n"
                "title: Core (hand-written)\n"
                "---\n"
                "# My hand-written core docs\n"
            )

        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        # The hand-written file should be preserved
        with open(handwritten, "r") as f:
            content = f.read()

        assert "hand-written" in content
        assert "generated: true" not in content

    def test_overwrites_previously_generated(self, python_project):
        docs_dir = os.path.join(python_project, "docs")

        # Create a previously generated page
        old_generated = os.path.join(docs_dir, "mylib-core.md")
        with open(old_generated, "w") as f:
            f.write(
                "---\n"
                "title: mylib.core\n"
                "generated: true\n"
                "---\n"
                "# old content\n"
            )

        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        with open(old_generated, "r") as f:
            content = f.read()

        # Should be regenerated with new content
        assert ':-: ref path="mylib.core"' in content


class TestDirectiveSyntax:
    """Test that generated pages use correct directive syntax."""

    def test_ref_directive_format(self, python_project):
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        with open(os.path.join(docs_dir, "mylib-utils.md"), "r") as f:
            content = f.read()

        assert ':-: ref path="mylib.utils"' in content


class TestIndexPage:
    """Test the generated index page."""

    def test_index_generated(self, python_project):
        config = _load_config(python_project)
        generated = generate_docs(config, base_dir=str(python_project))

        assert "gen-index.md" in generated

    def test_index_content(self, python_project):
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        with open(os.path.join(docs_dir, "gen-index.md"), "r") as f:
            content = f.read()

        assert "# API Reference" in content
        assert "generated: true" in content
        assert 'nav_group: "API Reference"' in content
        assert "nav_order: 0" in content
        assert "order: 90" in content
        assert "mylib.core" in content
        assert "mylib-core.html" in content

    def test_index_has_readonly_permissions(self, python_project):
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        mode = os.stat(os.path.join(docs_dir, "gen-index.md")).st_mode
        assert mode & stat.S_IRUSR
        assert not (mode & stat.S_IWUSR)


class TestDescriptionPreservation:
    """Test that user-customized frontmatter descriptions survive regeneration."""

    def _rewrite_description(self, filepath, new_description):
        """Replace the ``description:`` line in a page's frontmatter.

        Handles the read-only permissions selfdoc sets on generated files.
        """
        os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        new_lines = []
        for line in content.split("\n"):
            if line.startswith("description:"):
                new_lines.append(f'description: "{new_description}"')
            else:
                new_lines.append(line)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines))

    def test_preserves_custom_description(self, python_project):
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        core_path = os.path.join(docs_dir, "mylib-core.md")

        custom = "Handwritten one-line description of the core module."
        self._rewrite_description(core_path, custom)

        generate_docs(config, base_dir=str(python_project))

        with open(core_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert f'description: "{custom}"' in content
        assert "auto-generated documentation" not in content

    def test_regenerates_default_description(self, python_project):
        """Modules without a docstring get the default template description."""
        # Create a module with no docstring
        lib_dir = os.path.join(python_project, "mylib")
        with open(os.path.join(lib_dir, "nodoc.py"), "w") as f:
            f.write("def something(): pass\n")

        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        nodoc_path = os.path.join(docs_dir, "mylib-nodoc.md")

        # Do NOT touch the description -- it remains the default template.
        generate_docs(config, base_dir=str(python_project))

        with open(nodoc_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "API reference for the mylib.nodoc module" in content
        assert "auto-generated documentation" in content

    def test_preserves_description_across_multiple_regenerations(self, python_project):
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        utils_path = os.path.join(docs_dir, "mylib-utils.md")

        custom = "Utility helpers shared across mylib."
        self._rewrite_description(utils_path, custom)

        for _ in range(3):
            generate_docs(config, base_dir=str(python_project))

        with open(utils_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert f'description: "{custom}"' in content
        assert "auto-generated documentation" not in content

    def test_empty_existing_file_uses_default(self, python_project):
        """A module with no docstring falls back to the default template."""
        lib_dir = os.path.join(python_project, "mylib")
        # Create a module with no docstring
        with open(os.path.join(lib_dir, "nodoc.py"), "w") as f:
            f.write("def something(): pass\n")

        docs_dir = os.path.join(python_project, "docs")
        nodoc_path = os.path.join(docs_dir, "mylib-nodoc.md")

        # Pre-create a generated-marked file with frontmatter but NO description key.
        with open(nodoc_path, "w", encoding="utf-8") as f:
            f.write(
                "---\n"
                "title: mylib.nodoc\n"
                "generated: true\n"
                'nav_group: "API Reference"\n'
                "nav_order: 1\n"
                "---\n"
                "# mylib.nodoc\n"
            )

        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        with open(nodoc_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "API reference for the mylib.nodoc module" in content
        assert "auto-generated documentation" in content

    def test_docstring_used_as_description(self, python_project):
        """A module with a docstring uses it as the page description."""
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        # mylib/core.py has docstring "Core module."
        core_path = os.path.join(docs_dir, "mylib-core.md")
        with open(core_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert 'description: "Core module."' in content
        assert "auto-generated documentation" not in content

    def test_docstring_truncated_to_155_chars(self, python_project):
        """A module with a very long docstring is truncated to 155 chars."""
        lib_dir = os.path.join(python_project, "mylib")
        long_doc = "A" * 200
        with open(os.path.join(lib_dir, "longdoc.py"), "w") as f:
            f.write(f'"""{long_doc}"""\ndef func(): pass\n')

        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        longdoc_path = os.path.join(docs_dir, "mylib-longdoc.md")
        with open(longdoc_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Description should be truncated (152 chars + "...")
        assert "auto-generated documentation" not in content
        assert "..." in content
        # Extract the description value
        for line in content.split("\n"):
            if line.startswith("description:"):
                desc = line.split(":", 1)[1].strip().strip('"')
                assert len(desc) <= 155

    def test_no_docstring_uses_template(self, python_project):
        """A module with no docstring falls back to the API reference template."""
        lib_dir = os.path.join(python_project, "mylib")
        with open(os.path.join(lib_dir, "bare.py"), "w") as f:
            f.write("x = 1\n")

        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        bare_path = os.path.join(docs_dir, "mylib-bare.md")
        with open(bare_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "API reference for the mylib.bare module" in content
        assert "auto-generated documentation" in content


class TestStaleCleanup:
    """Test that stale generated files are removed on re-run."""

    def test_removes_stale_generated(self, python_project):
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        assert os.path.isfile(os.path.join(docs_dir, "mylib-utils.md"))

        # Remove the source file and re-generate
        os.unlink(os.path.join(python_project, "mylib", "utils.py"))
        generate_docs(config, base_dir=str(python_project))

        # The stale page should be removed
        assert not os.path.isfile(os.path.join(docs_dir, "mylib-utils.md"))

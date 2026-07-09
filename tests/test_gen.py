"""Tests for selfdoc.gen -- auto-generating documentation pages."""

import json
import os
import stat

import pytest

from selfdoc.gen import (
    GenResult,
    generate_docs,
    _has_generated_marker,
    _generate_index_content,
    _read_existing_description,
)


@pytest.fixture()
def python_project(tmp_path):
    """Create a minimal Python project with selfdoc config and source files."""
    config = {
        "source": [{"path": "mylib/", "language": "python"}],
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
        generated = generate_docs(config, base_dir=str(python_project)).written

        assert len(generated) > 0
        docs_dir = os.path.join(python_project, "docs")
        for fname in generated:
            assert os.path.isfile(os.path.join(docs_dir, fname))

    def test_correct_filenames(self, python_project):
        config = _load_config(python_project)
        generated = generate_docs(config, base_dir=str(python_project)).written

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
        assert ':-: ref path="mylib.core" lang="python"' in content


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
        generated = generate_docs(config, base_dir=str(python_project)).written

        filenames = set(generated)
        assert "mylib-test_core.md" not in filenames

    def test_default_excludes_pycache(self, python_project):
        cache_dir = os.path.join(python_project, "mylib", "__pycache__")
        os.makedirs(cache_dir)
        with open(os.path.join(cache_dir, "core.cpython-311.pyc"), "w") as f:
            f.write("")

        config = _load_config(python_project)
        generated = generate_docs(config, base_dir=str(python_project)).written

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
        generated = generate_docs(config, base_dir=str(python_project)).written

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
        assert ':-: ref path="mylib.core" lang="python"' in content


class TestDirectiveSyntax:
    """Test that generated pages use correct directive syntax."""

    def test_ref_directive_format(self, python_project):
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        with open(os.path.join(docs_dir, "mylib-utils.md"), "r") as f:
            content = f.read()

        assert ':-: ref path="mylib.utils" lang="python"' in content


class TestIndexPage:
    """Test the generated index page."""

    def test_index_generated(self, python_project):
        config = _load_config(python_project)
        generated = generate_docs(config, base_dir=str(python_project)).written

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
        Also removes ``seeded: true`` since a hand-edited description is
        no longer auto-generated.
        """
        os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        new_lines = []
        for line in content.split("\n"):
            if line.startswith("description:"):
                new_lines.append(f'description: "{new_description}"')
            elif line.strip() == "seeded: true":
                continue  # remove seeded marker for hand-edited descriptions
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


# ---------------------------------------------------------------------------
# Go generation tests -- per-package (per-directory) pages
# ---------------------------------------------------------------------------


@pytest.fixture()
def go_project(tmp_path):
    """Create a Go project with multiple packages for gen testing.

    Layout:
      go.mod
      main.go              (root package)
      utils.go             (root package, second file)
      internal/models/models.go   (single-file package)
      internal/commit/doc.go      (multi-file package, has package doc)
      internal/commit/commit.go
      internal/commit/types.go
      internal/commit/commit_test.go  (should be excluded)
      cmd/myapp/main.go   (cmd package)
      docs/               (output directory)
    """
    # go.mod
    with open(os.path.join(tmp_path, "go.mod"), "w") as f:
        f.write("module github.com/user/mygoapp\n\ngo 1.21\n")

    # selfdoc.json
    config = {
        "source": [{"path": ".", "language": "go"}],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
    }
    with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
        json.dump(config, f)

    # Root package files
    with open(os.path.join(tmp_path, "main.go"), "w") as f:
        f.write(
            "// mygoapp is the entry point for the application.\n"
            "package main\n\n"
            "func main() {}\n"
        )
    with open(os.path.join(tmp_path, "utils.go"), "w") as f:
        f.write("package main\n\nfunc Helper() {}\n")

    # internal/models -- single-file package
    models_dir = os.path.join(tmp_path, "internal", "models")
    os.makedirs(models_dir)
    with open(os.path.join(models_dir, "models.go"), "w") as f:
        f.write(
            "// Package models defines data structures.\n"
            "package models\n\n"
            "type User struct {\n\tName string\n}\n"
        )

    # internal/commit -- multi-file package with doc.go
    commit_dir = os.path.join(tmp_path, "internal", "commit")
    os.makedirs(commit_dir)
    with open(os.path.join(commit_dir, "doc.go"), "w") as f:
        f.write(
            "// Package commit handles git commit operations.\n"
            "package commit\n"
        )
    with open(os.path.join(commit_dir, "commit.go"), "w") as f:
        f.write("package commit\n\nfunc Create() error { return nil }\n")
    with open(os.path.join(commit_dir, "types.go"), "w") as f:
        f.write("package commit\n\ntype Commit struct {\n\tHash string\n}\n")
    # Test file -- should be excluded
    with open(os.path.join(commit_dir, "commit_test.go"), "w") as f:
        f.write(
            "package commit\n\n"
            "import \"testing\"\n\n"
            "func TestCreate(t *testing.T) {}\n"
        )

    # cmd/myapp
    cmd_dir = os.path.join(tmp_path, "cmd", "myapp")
    os.makedirs(cmd_dir)
    with open(os.path.join(cmd_dir, "main.go"), "w") as f:
        f.write("package main\n\nfunc main() {}\n")

    # docs directory
    os.makedirs(os.path.join(tmp_path, "docs"), exist_ok=True)

    return tmp_path


class TestGoPackageGeneration:
    """Test Go per-package (per-directory) page generation."""

    def test_one_page_per_package(self, go_project):
        """Each directory with .go files produces exactly one page."""
        config = _load_config(go_project)
        generated = generate_docs(config, base_dir=str(go_project)).written

        filenames = set(generated)
        # Should have: root package, internal-models, internal-commit,
        # cmd-myapp, plus gen-index.md
        assert "internal-models.md" in filenames
        assert "internal-commit.md" in filenames
        assert "cmd-myapp.md" in filenames
        assert "gen-index.md" in filenames

    def test_no_per_file_pages(self, go_project):
        """Per-file pages should NOT be generated for Go."""
        config = _load_config(go_project)
        generated = generate_docs(config, base_dir=str(go_project)).written

        filenames = set(generated)
        # These would exist if gen was treating Go as per-file
        assert "internal-commit-commit.md" not in filenames
        assert "internal-commit-types.md" not in filenames
        assert "internal-commit-doc.md" not in filenames
        assert "main.md" not in filenames
        assert "utils.md" not in filenames

    def test_root_package_uses_module_name(self, go_project):
        """Root package page filename comes from go.mod module name."""
        config = _load_config(go_project)
        generated = generate_docs(config, base_dir=str(go_project)).written

        filenames = set(generated)
        # go.mod has "module github.com/user/mygoapp" -> last segment "mygoapp"
        assert "mygoapp.md" in filenames

    def test_root_package_fallback_to_dirname(self, go_project):
        """Root package falls back to directory basename when go.mod is missing."""
        # Remove go.mod
        os.unlink(os.path.join(go_project, "go.mod"))
        # The go extractor detect() checks for go.mod, but gen only uses
        # the config language field, so we need to keep it working.
        # We re-create go.mod without a module line to test the fallback.
        with open(os.path.join(go_project, "go.mod"), "w") as f:
            f.write("go 1.21\n")

        config = _load_config(go_project)
        generated = generate_docs(config, base_dir=str(go_project)).written

        filenames = set(generated)
        # Should use the tmp directory basename
        basename = os.path.basename(str(go_project))
        assert f"{basename}.md" in filenames

    def test_test_files_excluded(self, go_project):
        """_test.go files should not cause packages to appear or affect output."""
        config = _load_config(go_project)
        generated = generate_docs(config, base_dir=str(go_project)).written

        filenames = set(generated)
        # No page named after a test file
        for fname in filenames:
            assert "test" not in fname.lower() or fname == "gen-index.md"

    def test_ref_directive_uses_directory_path(self, go_project):
        """Generated pages use package directory path in ref directive."""
        config = _load_config(go_project)
        generate_docs(config, base_dir=str(go_project))

        docs_dir = os.path.join(go_project, "docs")
        with open(os.path.join(docs_dir, "internal-commit.md"), "r") as f:
            content = f.read()

        assert ':-: ref path="internal/commit" lang="go"' in content

    def test_ref_directive_root_package(self, go_project):
        """Root package ref directive uses the module name as display path."""
        config = _load_config(go_project)
        generate_docs(config, base_dir=str(go_project))

        docs_dir = os.path.join(go_project, "docs")
        with open(os.path.join(docs_dir, "mygoapp.md"), "r") as f:
            content = f.read()

        # Root package uses "." as the ref path with lang qualifier
        assert ':-: ref path="." lang="go"' in content

    def test_package_doc_used_as_description(self, go_project):
        """Package doc comment is extracted and used as page description."""
        config = _load_config(go_project)
        generate_docs(config, base_dir=str(go_project))

        docs_dir = os.path.join(go_project, "docs")
        with open(os.path.join(docs_dir, "internal-commit.md"), "r") as f:
            content = f.read()

        # doc.go has "Package commit handles git commit operations."
        assert "handles git commit operations." in content

    def test_package_without_doc_uses_default(self, go_project):
        """Packages without doc comment get the default description template."""
        config = _load_config(go_project)
        generate_docs(config, base_dir=str(go_project))

        docs_dir = os.path.join(go_project, "docs")
        with open(os.path.join(docs_dir, "cmd-myapp.md"), "r") as f:
            content = f.read()

        # cmd/myapp has no package doc comment
        assert "auto-generated documentation" in content

    def test_generated_marker_present(self, go_project):
        """All generated Go pages have the generated: true marker."""
        config = _load_config(go_project)
        generate_docs(config, base_dir=str(go_project))

        docs_dir = os.path.join(go_project, "docs")
        assert _has_generated_marker(
            os.path.join(docs_dir, "internal-commit.md")
        )
        assert _has_generated_marker(
            os.path.join(docs_dir, "internal-models.md")
        )

    def test_multi_source_path(self, go_project):
        """Go gen works with multiple source paths."""
        # Create an extra source directory
        extra_dir = os.path.join(go_project, "pkg", "extra")
        os.makedirs(extra_dir)
        with open(os.path.join(extra_dir, "extra.go"), "w") as f:
            f.write("package extra\n\nfunc DoExtra() {}\n")

        config = _load_config(go_project)
        config["source"] = [{"path": ".", "language": "go"}, {"path": "pkg/", "language": "go"}]
        generated = generate_docs(config, base_dir=str(go_project)).written

        filenames = set(generated)
        # Sub-package under pkg/ is prefixed with source path name
        assert "pkg-extra.md" in filenames

    def test_user_exclude_patterns_go(self, go_project):
        """User-configured exclude patterns work for Go packages."""
        config = _load_config(go_project)
        config["gen"] = {"exclude": ["cmd/*"]}
        generated = generate_docs(config, base_dir=str(go_project)).written

        filenames = set(generated)
        assert "cmd-myapp.md" not in filenames
        # Other packages still present
        assert "internal-commit.md" in filenames


class TestGenResult:
    def test_default_empty(self):
        result = GenResult()
        assert result.written == []
        assert result.deleted == []

    def test_merge(self):
        a = GenResult(written=["a.md"], deleted=["x.md"])
        b = GenResult(written=["b.md"], deleted=["y.md"])
        merged = GenResult(
            written=a.written + b.written,
            deleted=a.deleted + b.deleted,
        )
        assert merged.written == ["a.md", "b.md"]
        assert merged.deleted == ["x.md", "y.md"]

    def test_generate_docs_returns_gen_result(self, python_project):
        """generate_docs returns a GenResult with the correct written list."""
        config = _load_config(python_project)
        result = generate_docs(config, base_dir=str(python_project))

        assert isinstance(result, GenResult)
        assert len(result.written) > 0
        filenames = set(result.written)
        assert "mylib-core.md" in filenames
        assert "mylib-utils.md" in filenames
        assert "mylib.md" in filenames
        assert "gen-index.md" in filenames

    def test_stale_cleanup_returns_deleted(self, python_project):
        """Removing a source file causes GenResult.deleted to list the stale page."""
        config = _load_config(python_project)
        # First generation creates all pages
        result1 = generate_docs(config, base_dir=str(python_project))
        assert "mylib-utils.md" in result1.written
        assert result1.deleted == []

        # Remove the source file
        os.unlink(os.path.join(python_project, "mylib", "utils.py"))

        # Second generation should report the stale page as deleted
        result2 = generate_docs(config, base_dir=str(python_project))
        assert "mylib-utils.md" in result2.deleted
        assert "mylib-utils.md" not in result2.written

    def test_deleted_files_in_gen_result(self, python_project):
        """Full flow: generate, remove source, re-generate. Verify both written and deleted."""
        config = _load_config(python_project)
        result1 = generate_docs(config, base_dir=str(python_project))

        # All three modules + index should be written
        assert "mylib-core.md" in result1.written
        assert "mylib-utils.md" in result1.written
        assert "mylib.md" in result1.written
        assert "gen-index.md" in result1.written
        assert result1.deleted == []

        # Remove utils.py
        os.unlink(os.path.join(python_project, "mylib", "utils.py"))

        result2 = generate_docs(config, base_dir=str(python_project))

        # utils page should be deleted, not written
        assert "mylib-utils.md" in result2.deleted
        assert "mylib-utils.md" not in result2.written

        # core and init pages should still be written
        assert "mylib-core.md" in result2.written
        assert "mylib.md" in result2.written
        assert "gen-index.md" in result2.written


# ---------------------------------------------------------------------------
# Multi-language generation tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def multi_language_project(tmp_path):
    """Create a project with both Python and Go sources."""
    config = {
        "source": [
            {"path": "pylib/", "language": "python"},
            {"path": "golib/", "language": "go"},
        ],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
    }
    config_path = os.path.join(tmp_path, "selfdoc.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    # Python source: pylib/__init__.py, pylib/core.py
    py_dir = os.path.join(tmp_path, "pylib")
    os.makedirs(py_dir)
    with open(os.path.join(py_dir, "__init__.py"), "w") as f:
        f.write('"""Python library."""\n')
    with open(os.path.join(py_dir, "core.py"), "w") as f:
        f.write('"""Core Python module."""\ndef main(): pass\n')

    # Go source: golib/handler.go (one package)
    go_dir = os.path.join(tmp_path, "golib")
    os.makedirs(go_dir)
    with open(os.path.join(go_dir, "handler.go"), "w") as f:
        f.write(
            "// Package golib provides handlers.\n"
            "package golib\n\n"
            "func Handle() {}\n"
        )

    # go.mod (needed for root package name resolution)
    with open(os.path.join(tmp_path, "go.mod"), "w") as f:
        f.write("module github.com/user/multiproj\n\ngo 1.21\n")

    # Create docs/ directory
    os.makedirs(os.path.join(tmp_path, "docs"), exist_ok=True)

    return tmp_path


class TestMultiLanguageGeneration:
    """Test that multi-language configs generate pages for all languages."""

    def test_multi_language_gen(self, multi_language_project):
        """Config with Python + Go sources generates pages for both."""
        config = _load_config(multi_language_project)
        result = generate_docs(config, base_dir=str(multi_language_project))

        filenames = set(result.written)

        # Python pages: pylib (from __init__), pylib-core
        assert "pylib.md" in filenames
        assert "pylib-core.md" in filenames

        # Go pages: golib is a single package under golib/ source path.
        # The root package gets module_path = "golib" (source-path-qualified).
        docs_dir = os.path.join(multi_language_project, "docs")
        all_md = {
            f for f in os.listdir(docs_dir) if f.endswith(".md")
        }

        # Should have Python pages + Go page(s) + gen-index
        assert "pylib.md" in all_md
        assert "pylib-core.md" in all_md
        assert "gen-index.md" in all_md

        # Go root package uses source path name -> "golib"
        assert "golib.md" in all_md

        # Index should list both Python and Go modules
        with open(os.path.join(docs_dir, "gen-index.md"), "r") as f:
            index_content = f.read()
        assert "pylib.core" in index_content
        assert "golib" in index_content

    def test_stale_cleanup_across_languages(self, multi_language_project):
        """Removing a Python source does not delete Go pages."""
        config = _load_config(multi_language_project)

        # First generation
        result1 = generate_docs(
            config, base_dir=str(multi_language_project),
        )
        assert "pylib-core.md" in result1.written

        docs_dir = os.path.join(multi_language_project, "docs")

        # Find Go page name
        go_pages = [
            f for f in result1.written
            if f not in ("pylib.md", "pylib-core.md", "gen-index.md")
        ]
        assert len(go_pages) == 1
        go_page = go_pages[0]
        assert os.path.isfile(os.path.join(docs_dir, go_page))

        # Remove the Python core source file
        os.unlink(
            os.path.join(multi_language_project, "pylib", "core.py")
        )

        # Second generation
        result2 = generate_docs(
            config, base_dir=str(multi_language_project),
        )

        # Python core page should be deleted
        assert "pylib-core.md" in result2.deleted

        # Go page should still exist and be written (not deleted)
        assert go_page in result2.written
        assert go_page not in result2.deleted
        assert os.path.isfile(os.path.join(docs_dir, go_page))

    def test_single_language_still_works(self, python_project):
        """Single-language config (Python only) works correctly."""
        config = _load_config(python_project)
        result = generate_docs(config, base_dir=str(python_project))

        filenames = set(result.written)
        assert "mylib-core.md" in filenames
        assert "mylib-utils.md" in filenames
        assert "mylib.md" in filenames
        assert "gen-index.md" in filenames

        # Verify content is correct
        docs_dir = os.path.join(python_project, "docs")
        with open(os.path.join(docs_dir, "mylib-core.md"), "r") as f:
            content = f.read()
        assert ':-: ref path="mylib.core" lang="python"' in content
        assert "generated: true" in content


# ---------------------------------------------------------------------------
# Multi-source-path Go root package ambiguity tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def multi_go_source_project(tmp_path):
    """Create a project with two Go source paths, each with a root package."""
    config = {
        "source": [
            {"path": "router/", "language": "go"},
            {"path": "sdk/", "language": "go"},
        ],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
    }
    config_path = os.path.join(tmp_path, "selfdoc.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    # go.mod
    with open(os.path.join(tmp_path, "go.mod"), "w") as f:
        f.write("module github.com/user/myproject\n\ngo 1.21\n")

    # router/ source path with root package
    router_dir = os.path.join(tmp_path, "router")
    os.makedirs(router_dir)
    with open(os.path.join(router_dir, "router.go"), "w") as f:
        f.write(
            "// Package router provides HTTP routing.\n"
            "package router\n\n"
            "func Route() {}\n"
        )

    # sdk/ source path with root package
    sdk_dir = os.path.join(tmp_path, "sdk")
    os.makedirs(sdk_dir)
    with open(os.path.join(sdk_dir, "client.go"), "w") as f:
        f.write(
            "// Package sdk provides the client SDK.\n"
            "package sdk\n\n"
            "func NewClient() {}\n"
        )

    # Create docs/ directory
    os.makedirs(os.path.join(tmp_path, "docs"), exist_ok=True)

    return tmp_path


class TestMultiGoSourcePathAmbiguity:
    """Test that multiple Go source paths with root packages are not ambiguous."""

    def test_both_root_packages_generate_pages(self, multi_go_source_project):
        """Two Go source paths with root packages produce two separate pages."""
        config = _load_config(multi_go_source_project)
        result = generate_docs(
            config, base_dir=str(multi_go_source_project),
        )

        filenames = set(result.written)

        # Both source paths should produce pages, not just the first one
        assert "router.md" in filenames
        assert "sdk.md" in filenames

    def test_ref_paths_are_unique(self, multi_go_source_project):
        """Each root package page has a unique, non-dot ref path."""
        config = _load_config(multi_go_source_project)
        generate_docs(config, base_dir=str(multi_go_source_project))

        docs_dir = os.path.join(multi_go_source_project, "docs")

        with open(os.path.join(docs_dir, "router.md"), "r") as f:
            router_content = f.read()
        with open(os.path.join(docs_dir, "sdk.md"), "r") as f:
            sdk_content = f.read()

        # ref paths should use the source path name, not "."
        assert ':-: ref path="router"' in router_content
        assert ':-: ref path="sdk"' in sdk_content
        # Neither should use "."
        assert 'ref path="."' not in router_content
        assert 'ref path="."' not in sdk_content

    def test_sub_packages_prefixed_with_source_path(
        self, multi_go_source_project,
    ):
        """Sub-packages under a source path are prefixed with the source path."""
        # Add a sub-package under router/
        middleware_dir = os.path.join(
            multi_go_source_project, "router", "middleware",
        )
        os.makedirs(middleware_dir)
        with open(os.path.join(middleware_dir, "auth.go"), "w") as f:
            f.write("package middleware\n\nfunc Auth() {}\n")

        config = _load_config(multi_go_source_project)
        result = generate_docs(
            config, base_dir=str(multi_go_source_project),
        )

        filenames = set(result.written)
        assert "router-middleware.md" in filenames

        docs_dir = os.path.join(multi_go_source_project, "docs")
        with open(os.path.join(docs_dir, "router-middleware.md"), "r") as f:
            content = f.read()

        # The ref path should be prefixed with the source path
        assert ':-: ref path="router/middleware"' in content


# ---------------------------------------------------------------------------
# Directory pruning tests -- .venv, node_modules, etc.
# ---------------------------------------------------------------------------


class TestDirectoryPruning:
    """Test that .venv, node_modules, and other non-source directories are skipped."""

    def test_venv_excluded_from_python_gen(self, python_project):
        """Files inside .venv/ should not produce doc pages."""
        venv_pkg = os.path.join(
            python_project, "mylib", ".venv", "lib", "python3.11",
            "site-packages", "requests",
        )
        os.makedirs(venv_pkg)
        with open(os.path.join(venv_pkg, "__init__.py"), "w") as f:
            f.write('"""HTTP library."""\n')
        with open(os.path.join(venv_pkg, "api.py"), "w") as f:
            f.write('"""API module."""\ndef get(): pass\n')

        config = _load_config(python_project)
        result = generate_docs(config, base_dir=str(python_project))

        # No page should reference anything from .venv
        for fname in result.written:
            assert ".venv" not in fname
            assert "requests" not in fname

    def test_plain_venv_excluded(self, python_project):
        """Files inside venv/ (without dot) should not produce doc pages."""
        venv_pkg = os.path.join(python_project, "mylib", "venv", "lib", "pkg")
        os.makedirs(venv_pkg)
        with open(os.path.join(venv_pkg, "__init__.py"), "w") as f:
            f.write('"""Some package."""\n')

        config = _load_config(python_project)
        result = generate_docs(config, base_dir=str(python_project))

        for fname in result.written:
            assert "venv" not in fname

    def test_node_modules_excluded(self, tmp_path):
        """Files inside node_modules/ should not produce doc pages."""
        config = {
            "source": [{"path": "src/", "language": "typescript"}],
            "docs": "docs/",
            "output": "docs/_build/",
            "base_url": "https://example.com",
        }
        with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
            json.dump(config, f)

        src_dir = os.path.join(tmp_path, "src")
        os.makedirs(src_dir)
        with open(os.path.join(src_dir, "index.ts"), "w") as f:
            f.write("export function main() {}\n")

        # Simulate node_modules inside src/
        nm_dir = os.path.join(src_dir, "node_modules", "some-pkg", "src")
        os.makedirs(nm_dir)
        with open(os.path.join(nm_dir, "index.ts"), "w") as f:
            f.write("export function internal() {}\n")

        os.makedirs(os.path.join(tmp_path, "docs"), exist_ok=True)

        config = _load_config(tmp_path)
        result = generate_docs(config, base_dir=str(tmp_path))

        for fname in result.written:
            assert "node_modules" not in fname
            assert "some-pkg" not in fname

    def test_venv_excluded_from_go_gen(self, go_project):
        """Go walks should skip .venv directories too."""
        venv_go = os.path.join(go_project, ".venv", "govendor")
        os.makedirs(venv_go)
        with open(os.path.join(venv_go, "vendor.go"), "w") as f:
            f.write("package govendor\n\nfunc Vendor() {}\n")

        config = _load_config(go_project)
        result = generate_docs(config, base_dir=str(go_project))

        for fname in result.written:
            assert ".venv" not in fname
            assert "vendor" not in fname.lower() or fname in (
                "gen-index.md",
            )

    def test_venv_at_source_root(self, tmp_path):
        """A .venv at the source path root level is skipped."""
        config = {
            "source": [{"path": ".", "language": "python"}],
            "docs": "docs/",
            "output": "docs/_build/",
            "base_url": "https://example.com",
        }
        with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
            json.dump(config, f)

        # Real source file
        pkg_dir = os.path.join(tmp_path, "mypkg")
        os.makedirs(pkg_dir)
        with open(os.path.join(pkg_dir, "__init__.py"), "w") as f:
            f.write('"""My package."""\n')
        with open(os.path.join(pkg_dir, "core.py"), "w") as f:
            f.write('"""Core."""\ndef run(): pass\n')

        # .venv with third-party packages at project root
        venv_site = os.path.join(
            tmp_path, ".venv", "lib", "python3.11", "site-packages", "flask",
        )
        os.makedirs(venv_site)
        with open(os.path.join(venv_site, "__init__.py"), "w") as f:
            f.write('"""Flask web framework."""\n')
        with open(os.path.join(venv_site, "app.py"), "w") as f:
            f.write('"""Flask app."""\ndef create_app(): pass\n')

        os.makedirs(os.path.join(tmp_path, "docs"), exist_ok=True)

        config = _load_config(tmp_path)
        result = generate_docs(config, base_dir=str(tmp_path))

        # Should have mypkg pages but nothing from .venv
        filenames = set(result.written)
        assert "mypkg.md" in filenames or "mypkg-core.md" in filenames
        for fname in filenames:
            assert ".venv" not in fname
            assert "flask" not in fname


class TestIndexContentAwareDescription:
    """Test that gen-index.md gets a content-aware, seeded description."""

    def test_index_has_seeded_true(self, python_project):
        """Index page should have seeded: true when auto-generated."""
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        with open(os.path.join(docs_dir, "gen-index.md"), "r") as f:
            content = f.read()

        assert "seeded: true" in content

    def test_index_description_includes_project_name(self, python_project):
        """Index description should reference the project name from source."""
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        with open(os.path.join(docs_dir, "gen-index.md"), "r") as f:
            content = f.read()

        # Source path is "mylib/", so project name is "mylib"
        assert "mylib" in content.split("---")[1]  # in frontmatter

    def test_index_description_includes_module_count(self, python_project):
        """Index description should mention how many modules are covered."""
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        docs_dir = os.path.join(python_project, "docs")
        with open(os.path.join(docs_dir, "gen-index.md"), "r") as f:
            content = f.read()

        # 3 modules: mylib, mylib.core, mylib.utils
        assert "3 modules" in content

    def test_index_preserves_hand_edited_description(self, python_project):
        """Hand-edited descriptions on gen-index.md should survive regen."""
        config = _load_config(python_project)
        generate_docs(config, base_dir=str(python_project))

        # Hand-edit the index page description
        index_path = os.path.join(python_project, "docs", "gen-index.md")
        os.chmod(index_path, stat.S_IRUSR | stat.S_IWUSR)
        with open(index_path, "r") as f:
            content = f.read()
        # Replace description and remove seeded marker
        new_lines = []
        for line in content.split("\n"):
            if line.startswith("description:"):
                new_lines.append('description: "My custom index description"')
            elif line.strip() == "seeded: true":
                continue
            else:
                new_lines.append(line)
        with open(index_path, "w") as f:
            f.write("\n".join(new_lines))

        # Regenerate
        generate_docs(config, base_dir=str(python_project))

        with open(index_path, "r") as f:
            content = f.read()

        assert "My custom index description" in content
        assert "seeded: true" not in content

    def test_generate_index_content_unit(self):
        """Unit test for _generate_index_content."""
        pages = [
            ("foo.bar", "foo-bar.md"),
            ("foo.baz", "foo-baz.md"),
        ]
        content = _generate_index_content(pages, "foo")

        assert "seeded: true" in content
        assert "foo" in content.split("---")[1]
        assert "2 modules" in content

    def test_generate_index_content_singular_module(self):
        """Single module should say 'module' not 'modules'."""
        pages = [("foo", "foo.md")]
        content = _generate_index_content(pages, "foo")

        assert "1 module" in content
        # Make sure it doesn't say "1 modules"
        assert "1 modules" not in content

    def test_generate_index_content_preserves_existing(self):
        """Existing description should be preserved, no seeded marker."""
        pages = [("foo.bar", "foo-bar.md")]
        content = _generate_index_content(
            pages, "foo", existing_description="Custom desc"
        )

        assert "Custom desc" in content
        assert "seeded: true" not in content

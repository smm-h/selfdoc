"""Tests for custom directive scripts in scripts/.

These are standalone scripts with resolve(attrs, config, body) functions,
loaded by selfdoc's custom directive system via importlib.util.
"""

import importlib.util
import os

import pytest

from selfdoc.catalog import CORE_DIRECTIVES

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")


def _load_resolve(script_name):
    """Load a script from scripts/ and return its resolve function."""
    path = os.path.join(SCRIPTS_DIR, script_name)
    spec = importlib.util.spec_from_file_location(
        f"selfdoc_test_{script_name}", path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.resolve


# ---------------------------------------------------------------------------
# config-schema-directive.py
# ---------------------------------------------------------------------------


class TestConfigSchemaDirective:
    """Tests for scripts/config-schema-directive.py."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.resolve = _load_resolve("config-schema-directive.py")

    def test_returns_string(self):
        result = self.resolve({}, {}, [])
        assert isinstance(result, str)

    def test_category_headings_present(self):
        """All six category headings appear in the output."""
        result = self.resolve({}, {}, [])
        for category in ("Core", "Features", "SEO", "Deploy", "Branding", "Generation"):
            assert f"### {category}" in result

    def test_category_order(self):
        """Categories appear in the canonical order."""
        result = self.resolve({}, {}, [])
        positions = []
        for category in ("Core", "Features", "SEO", "Deploy", "Branding", "Generation"):
            pos = result.index(f"### {category}")
            positions.append(pos)
        assert positions == sorted(positions)

    def test_table_headers(self):
        """Each category section has the correct table header."""
        result = self.resolve({}, {}, [])
        header = "| Key | Type | Required | Description |"
        separator = "| --- | --- | --- | --- |"
        # At least one occurrence per category (6 categories)
        assert result.count(header) == 6
        assert result.count(separator) == 6

    def test_required_fields_show_yes(self):
        """Required fields (language, source, base_url) show 'Yes'."""
        result = self.resolve({}, {}, [])
        lines = result.split("\n")
        for line in lines:
            if "| `language` |" in line:
                assert "| Yes |" in line
                break
        else:
            pytest.fail("`language` row not found")

    def test_optional_fields_show_no(self):
        """Optional fields show 'No' in the Required column."""
        result = self.resolve({}, {}, [])
        lines = result.split("\n")
        for line in lines:
            if "| `theme` |" in line:
                assert "| No |" in line
                break
        else:
            pytest.fail("`theme` row not found")

    def test_conditional_required_fields(self):
        """Fields with conditional required values show the condition text."""
        result = self.resolve({}, {}, [])
        lines = result.split("\n")
        for line in lines:
            if "| `deploy.provider` |" in line:
                assert "When `deploy` is present" in line
                break
        else:
            pytest.fail("`deploy.provider` row not found")

    def test_key_column_is_backtick_wrapped(self):
        """Key names are wrapped in backticks."""
        result = self.resolve({}, {}, [])
        lines = result.split("\n")
        data_rows = [
            l for l in lines
            if l.startswith("| `") and "Key" not in l
        ]
        assert len(data_rows) > 0
        for row in data_rows:
            # First column after "| " should start with backtick
            cells = [c.strip() for c in row.split("|") if c.strip()]
            assert cells[0].startswith("`") and cells[0].endswith("`")

    def test_type_column_is_backtick_wrapped(self):
        """Type values are wrapped in backticks."""
        result = self.resolve({}, {}, [])
        lines = result.split("\n")
        data_rows = [
            l for l in lines
            if l.startswith("| `") and "Key" not in l
        ]
        for row in data_rows:
            cells = [c.strip() for c in row.split("|") if c.strip()]
            assert cells[1].startswith("`") and cells[1].endswith("`")

    def test_all_schema_entries_appear(self):
        """Every entry in the SCHEMA list produces a row in the output."""
        # Import the SCHEMA to count entries
        spec = importlib.util.spec_from_file_location(
            "config_schema_mod",
            os.path.join(SCRIPTS_DIR, "config-schema-directive.py"),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        schema = module.SCHEMA

        result = self.resolve({}, {}, [])
        for entry in schema:
            assert f"| `{entry['key']}` |" in result

    def test_ignores_attrs_config_body(self):
        """Output is the same regardless of attrs, config, and body."""
        baseline = self.resolve({}, {}, [])
        with_attrs = self.resolve({"path": "foo"}, {"language": "go"}, ["body line"])
        assert baseline == with_attrs

    def test_specific_row_content(self):
        """Spot-check a specific row for exact content."""
        result = self.resolve({}, {}, [])
        lines = result.split("\n")
        for line in lines:
            if "| `source` |" in line:
                assert "| `array` |" in line
                assert "| Yes |" in line
                assert "Non-empty list of source directory paths" in line
                break
        else:
            pytest.fail("`source` row not found")


# ---------------------------------------------------------------------------
# catalog-directive.py
# ---------------------------------------------------------------------------


class TestCatalogDirective:
    """Tests for scripts/catalog-directive.py."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.resolve = _load_resolve("catalog-directive.py")

    def test_returns_string(self):
        result = self.resolve({}, {}, [])
        assert isinstance(result, str)

    def test_category_headings_present(self):
        """Code Extraction and Content Blocks headings appear."""
        result = self.resolve({}, {}, [])
        assert "### Code Extraction" in result
        assert "### Content Blocks" in result

    def test_category_order(self):
        """Code Extraction appears before Content Blocks."""
        result = self.resolve({}, {}, [])
        code_pos = result.index("### Code Extraction")
        content_pos = result.index("### Content Blocks")
        assert code_pos < content_pos

    def test_table_headers(self):
        """Each category section has the correct table header."""
        result = self.resolve({}, {}, [])
        header = "| Directive | Description | Required | Optional |"
        separator = "| --- | --- | --- | --- |"
        # Two categories: code and content
        assert result.count(header) == 2
        assert result.count(separator) == 2

    def test_all_core_directives_appear(self):
        """Every CORE_DIRECTIVES entry appears in the output."""
        result = self.resolve({}, {}, [])
        for name in CORE_DIRECTIVES:
            assert f"| `{name}` |" in result

    def test_code_directives_in_code_section(self):
        """Directives with category='code' appear under Code Extraction."""
        result = self.resolve({}, {}, [])
        code_section_start = result.index("### Code Extraction")
        content_section_start = result.index("### Content Blocks")
        code_section = result[code_section_start:content_section_start]

        code_directives = [
            name for name, spec in CORE_DIRECTIVES.items()
            if spec.category == "code"
        ]
        assert len(code_directives) > 0
        for name in code_directives:
            assert f"| `{name}` |" in code_section

    def test_content_directives_in_content_section(self):
        """Directives with category='content' appear under Content Blocks."""
        result = self.resolve({}, {}, [])
        content_section_start = result.index("### Content Blocks")
        content_section = result[content_section_start:]

        content_directives = [
            name for name, spec in CORE_DIRECTIVES.items()
            if spec.category == "content"
        ]
        assert len(content_directives) > 0
        for name in content_directives:
            assert f"| `{name}` |" in content_section

    def test_required_attrs_formatting(self):
        """Required attrs are backtick-wrapped and comma-separated."""
        result = self.resolve({}, {}, [])
        # 'ref' has required_attrs=["path"]
        lines = result.split("\n")
        for line in lines:
            if "| `ref` |" in line:
                assert "`path`" in line
                break
        else:
            pytest.fail("`ref` row not found")

    def test_optional_attrs_formatting(self):
        """Optional attrs are backtick-wrapped and comma-separated."""
        result = self.resolve({}, {}, [])
        # 'ref' has optional_attrs=["target"]
        lines = result.split("\n")
        for line in lines:
            if "| `ref` |" in line:
                assert "`target`" in line
                break
        else:
            pytest.fail("`ref` row not found")

    def test_em_dash_for_empty_attrs(self):
        """Directives with no required or optional attrs show em dash."""
        result = self.resolve({}, {}, [])
        # callout-note has no required_attrs and no optional_attrs
        lines = result.split("\n")
        for line in lines:
            if "| `callout-note` |" in line:
                cells = [c.strip() for c in line.split("|") if c.strip()]
                # cells: [directive, description, required, optional]
                assert cells[2] == "—"  # em dash for required
                assert cells[3] == "—"  # em dash for optional
                break
        else:
            pytest.fail("`callout-note` row not found")

    def test_examples_sections_present(self):
        """Example subsections appear for both categories."""
        result = self.resolve({}, {}, [])
        assert "#### Code Extraction Examples" in result
        assert "#### Content Blocks Examples" in result

    def test_examples_use_code_fences(self):
        """Examples are wrapped in markdown code fences."""
        result = self.resolve({}, {}, [])
        assert "```markdown" in result
        assert "```" in result

    def test_directives_with_examples_appear_in_examples_section(self):
        """Each directive that has a non-empty example appears in its examples section."""
        result = self.resolve({}, {}, [])
        for name, spec in CORE_DIRECTIVES.items():
            if spec.example:
                assert f"**`{name}`**:" in result
                assert spec.example in result

    def test_directives_sorted_within_categories(self):
        """Directives are sorted alphabetically within each category."""
        result = self.resolve({}, {}, [])
        lines = result.split("\n")

        # Extract directive names from table rows in order
        code_start = result.index("### Code Extraction")
        content_start = result.index("### Content Blocks")

        code_lines = result[code_start:content_start].split("\n")
        code_names = []
        for line in code_lines:
            if line.startswith("| `") and "Directive" not in line:
                name = line.split("|")[1].strip().strip("`")
                code_names.append(name)

        assert code_names == sorted(code_names)

        content_lines = result[content_start:].split("\n")
        content_names = []
        for line in content_lines:
            if line.startswith("| `") and "Directive" not in line:
                name = line.split("|")[1].strip().strip("`")
                content_names.append(name)

        assert content_names == sorted(content_names)

    def test_ignores_attrs_config_body(self):
        """Output is the same regardless of attrs, config, and body."""
        baseline = self.resolve({}, {}, [])
        with_extras = self.resolve(
            {"key": "val"}, {"language": "python"}, ["some body"],
        )
        assert baseline == with_extras

    def test_specific_row_content(self):
        """Spot-check table-schema row for expected content."""
        result = self.resolve({}, {}, [])
        lines = result.split("\n")
        for line in lines:
            if "| `table-schema` |" in line:
                spec = CORE_DIRECTIVES["table-schema"]
                assert spec.description in line
                assert "`path`" in line  # required attr
                break
        else:
            pytest.fail("`table-schema` row not found")

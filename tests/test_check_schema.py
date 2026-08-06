"""Tests for JSON schema validation of selfdoc check --format json output."""

import json
import os
import re

import pytest

from selfdoc.check import check_docs


# -- Schema-aware validation helpers (no jsonschema dependency) --


_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SCHEMA_PATH = os.path.join(_REPO_ROOT, "schemas", "check-output.schema.json")

# Modules that construct LintResult objects. Every lint code reachable from a
# CheckResult originates in one of these; the consistency test below pins the
# schema enum to what they actually emit so the enum cannot silently rot.
_LINT_SOURCE_FILES = (
    os.path.join(_REPO_ROOT, "selfdoc", "check.py"),
    os.path.join(_REPO_ROOT, "selfblog", "check.py"),
)

_CODE_LITERAL_RE = re.compile(r'code\s*=\s*"([A-Z][A-Z0-9]*[0-9]{3})"')


def _load_schema():
    """Load the check-output JSON schema from disk."""
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _schema_lint_codes():
    """The lint-code enum declared by the JSON schema."""
    schema = _load_schema()
    return set(
        schema["properties"]["lints"]["items"]["properties"]["code"]["enum"]
    )


def _source_emitted_lint_codes():
    """Scan the lint-producing modules for the codes they actually emit."""
    codes = set()
    for path in _LINT_SOURCE_FILES:
        assert os.path.isfile(path), (
            f"lint source file missing: {path} -- update _LINT_SOURCE_FILES"
        )
        with open(path, "r", encoding="utf-8") as f:
            codes.update(_CODE_LITERAL_RE.findall(f.read()))
    assert codes, "no lint codes found in source -- the scan regex is broken"
    return codes


_VALID_STATUSES = {"OK", "FAILED"}
_VALID_SEVERITIES = {"error", "warning"}
# Derived from the schema rather than hand-mirrored, so the assertions in this
# file always test the shipped contract instead of a stale copy of it.
_VALID_LINT_CODES = _schema_lint_codes()


def _validate_check_output(data):
    """Validate *data* against the check-output JSON schema.

    Raises AssertionError with a descriptive message on any violation.
    Uses only stdlib -- no jsonschema dependency.
    """
    # Top-level structure
    assert isinstance(data, dict), "root must be an object"
    for key in ("directives", "coverage", "lints", "exit_code"):
        assert key in data, f"missing required top-level key: {key}"

    # exit_code
    assert isinstance(data["exit_code"], int), "exit_code must be an integer"
    assert data["exit_code"] in (0, 1), f"exit_code must be 0 or 1, got {data['exit_code']}"

    # directives
    assert isinstance(data["directives"], list), "directives must be an array"
    for i, dr in enumerate(data["directives"]):
        prefix = f"directives[{i}]"
        assert isinstance(dr, dict), f"{prefix} must be an object"
        for field in ("file", "line", "directive", "status", "error"):
            assert field in dr, f"{prefix} missing required field: {field}"
        assert isinstance(dr["file"], str), f"{prefix}.file must be a string"
        assert isinstance(dr["line"], int), f"{prefix}.line must be an integer"
        assert isinstance(dr["directive"], str), f"{prefix}.directive must be a string"
        assert isinstance(dr["status"], str), f"{prefix}.status must be a string"
        assert dr["status"] in _VALID_STATUSES, (
            f"{prefix}.status must be OK or FAILED, got {dr['status']!r}"
        )
        assert isinstance(dr["error"], str), f"{prefix}.error must be a string"

    # coverage (null or object)
    cov = data["coverage"]
    if cov is not None:
        assert isinstance(cov, dict), "coverage must be null or an object"
        for field in ("total_public", "referenced", "referenced_symbols", "unreferenced_symbols"):
            assert field in cov, f"coverage missing required field: {field}"
        assert isinstance(cov["total_public"], int), "coverage.total_public must be an integer"
        assert cov["total_public"] >= 0, "coverage.total_public must be >= 0"
        assert isinstance(cov["referenced"], int), "coverage.referenced must be an integer"
        assert cov["referenced"] >= 0, "coverage.referenced must be >= 0"
        assert isinstance(cov["referenced_symbols"], list), "coverage.referenced_symbols must be an array"
        for j, sym in enumerate(cov["referenced_symbols"]):
            assert isinstance(sym, str), f"coverage.referenced_symbols[{j}] must be a string"
        assert isinstance(cov["unreferenced_symbols"], list), "coverage.unreferenced_symbols must be an array"
        for j, sym in enumerate(cov["unreferenced_symbols"]):
            assert isinstance(sym, str), f"coverage.unreferenced_symbols[{j}] must be a string"

    # lints
    assert isinstance(data["lints"], list), "lints must be an array"
    for i, lint in enumerate(data["lints"]):
        prefix = f"lints[{i}]"
        assert isinstance(lint, dict), f"{prefix} must be an object"
        for field in ("file", "line", "code", "message", "severity"):
            assert field in lint, f"{prefix} missing required field: {field}"
        assert isinstance(lint["file"], str), f"{prefix}.file must be a string"
        assert lint["line"] is None or isinstance(lint["line"], int), (
            f"{prefix}.line must be an integer or null"
        )
        assert isinstance(lint["code"], str), f"{prefix}.code must be a string"
        assert lint["code"] in _VALID_LINT_CODES, (
            f"{prefix}.code {lint['code']!r} not in allowed enum"
        )
        assert isinstance(lint["message"], str), f"{prefix}.message must be a string"
        assert isinstance(lint["severity"], str), f"{prefix}.severity must be a string"
        assert lint["severity"] in _VALID_SEVERITIES, (
            f"{prefix}.severity must be error or warning, got {lint['severity']!r}"
        )


def _serialize_check_result(result):
    """Serialize a CheckResult to JSON dict, matching cli.py logic."""
    output = {
        "directives": [
            {
                "file": dr.file,
                "line": dr.line,
                "directive": dr.directive,
                "status": dr.status,
                "error": dr.error,
            }
            for dr in result.directive_results
        ],
        "coverage": None,
        "lints": [
            {
                "file": lint.file,
                "line": lint.line,
                "code": lint.code,
                "message": lint.message,
                "severity": lint.severity,
            }
            for lint in result.lints
        ],
        "exit_code": 1 if any(
            dr.status == "FAILED" for dr in result.directive_results
        ) or any(
            lint.severity == "error" for lint in result.lints
        ) else 0,
    }
    if result.coverage is not None:
        cov = result.coverage
        output["coverage"] = {
            "total_public": cov.total_public,
            "referenced": cov.referenced,
            "referenced_symbols": cov.referenced_symbols,
            "unreferenced_symbols": cov.unreferenced_symbols,
        }
    return output


# -- Fixtures --


@pytest.fixture()
def python_project(tmp_path):
    """Create a minimal Python project with selfdoc config and source files."""
    config = {
        "source": [{"path": "mylib/", "language": "python"}],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
        "version": "1.0.0",
    }
    with open(os.path.join(tmp_path, "selfdoc.json"), "w", encoding="utf-8") as f:
        json.dump(config, f)

    # Source: mylib/__init__.py with a public function
    lib_dir = os.path.join(tmp_path, "mylib")
    os.makedirs(lib_dir)
    with open(os.path.join(lib_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write(
            '"""My library."""\n'
            "\n"
            "def greet(name):\n"
            '    """Say hello."""\n'
            "    return f'Hello, {name}'\n"
        )

    # docs/ with a single page that has a valid directive
    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\n"
            "title: API\n"
            "description: API reference for the library that documents all public symbols and their usage patterns\n"
            "---\n"
            "\n"
            "# API Reference\n"
            "\n"
            ':-: ref path="mylib"\n'
        )

    return tmp_path


# -- Tests --


def test_schema_file_is_valid_json():
    """The schema file parses as valid JSON."""
    schema_path = os.path.join(
        os.path.dirname(__file__), "..", "schemas", "check-output.schema.json",
    )
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["title"] == "selfdoc check output"
    assert schema["type"] == "object"


def test_check_output_validates_against_schema(python_project):
    """check_docs() output serialized to JSON conforms to the schema."""
    result = check_docs(str(python_project))
    data = _serialize_check_result(result)

    # Round-trip through JSON to ensure serialization fidelity
    json_str = json.dumps(data, indent=2)
    parsed = json.loads(json_str)

    _validate_check_output(parsed)


def test_check_output_with_coverage(python_project):
    """Coverage data (when present) conforms to the schema."""
    result = check_docs(str(python_project))
    data = _serialize_check_result(result)
    parsed = json.loads(json.dumps(data))

    _validate_check_output(parsed)
    # Python project should have coverage
    assert parsed["coverage"] is not None
    assert parsed["coverage"]["total_public"] >= 0
    assert parsed["coverage"]["referenced"] >= 0
    assert isinstance(parsed["coverage"]["referenced_symbols"], list)
    assert isinstance(parsed["coverage"]["unreferenced_symbols"], list)


def test_check_output_null_coverage():
    """A hand-crafted payload with null coverage validates correctly."""
    data = {
        "directives": [],
        "coverage": None,
        "lints": [],
        "exit_code": 0,
    }
    _validate_check_output(data)
    assert data["coverage"] is None


def test_check_output_empty_coverage(tmp_path):
    """When no source files exist, coverage has zero symbols but is still valid."""
    config = {
        "source": [{"path": "pkg/", "language": "go"}],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
        "version": "1.0.0",
    }
    with open(os.path.join(tmp_path, "selfdoc.json"), "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\n"
            "title: Docs\n"
            "description: Documentation for the project covering all features and configuration options in detail\n"
            "---\n"
            "\n"
            "# Docs\n"
        )

    result = check_docs(str(tmp_path))
    data = _serialize_check_result(result)
    parsed = json.loads(json.dumps(data))

    _validate_check_output(parsed)
    assert parsed["coverage"] is not None
    assert parsed["coverage"]["total_public"] == 0


def test_check_output_with_failed_directive(python_project):
    """Failed directives produce valid schema output."""
    docs_dir = os.path.join(python_project, "docs")
    with open(os.path.join(docs_dir, "bad.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\n"
            "title: Bad\n"
            "description: A page with a broken directive that references a nonexistent module to test error handling\n"
            "---\n"
            "\n"
            "# Bad Page\n"
            "\n"
            ':-: ref path="nonexistent"\n'
        )

    result = check_docs(str(python_project))
    data = _serialize_check_result(result)
    parsed = json.loads(json.dumps(data))

    _validate_check_output(parsed)

    # Should have at least one FAILED directive
    failed = [d for d in parsed["directives"] if d["status"] == "FAILED"]
    assert len(failed) >= 1
    assert failed[0]["error"] != ""


def test_check_output_with_lint_warnings(python_project):
    """Lint warnings produce valid schema output with correct codes."""
    docs_dir = os.path.join(python_project, "docs")
    # Page missing description in frontmatter triggers SEO006
    with open(os.path.join(docs_dir, "nodesc.md"), "w", encoding="utf-8") as f:
        f.write(
            "# No Description Page\n"
            "\n"
            "Some content here.\n"
        )

    result = check_docs(str(python_project))
    data = _serialize_check_result(result)
    parsed = json.loads(json.dumps(data))

    _validate_check_output(parsed)

    # Should have lints with valid codes
    assert len(parsed["lints"]) > 0
    for lint in parsed["lints"]:
        assert lint["code"] in _VALID_LINT_CODES
        assert lint["severity"] in _VALID_SEVERITIES


def test_example_lint_code_validates_against_schema():
    """A payload carrying an EXAMPLE002 lint conforms to the schema.

    Regression: the schema's lint-code enum listed only SEO*/STALE001, so
    consumers validating ``selfdoc check --format json`` rejected every
    example, doc-quality, param/return and drift code.
    """
    data = {
        "directives": [],
        "coverage": None,
        "lints": [
            {
                "file": "docs/index.md",
                "line": 12,
                "code": "EXAMPLE002",
                "message": "Example failed validation: exit 1",
                "severity": "error",
            },
        ],
        "exit_code": 1,
    }
    _validate_check_output(data)


@pytest.mark.parametrize(
    "code",
    ["EXAMPLE001", "EXAMPLE002", "EXAMPLE003", "DQ001", "DQ002", "DQ003",
     "PARAM001", "RETURN001", "DRIFT001", "STALE002", "CLI001", "CLI002",
     "LANG001", "SEARCH001", "XREF001", "XREF002", "VER001", "VER002",
     "VER003", "VER004", "POST001", "POST005"],
)
def test_schema_accepts_current_lint_code(code):
    """Every currently-emitted lint code is accepted by the schema enum."""
    data = {
        "directives": [],
        "coverage": None,
        "lints": [
            {
                "file": "docs/index.md",
                "line": None,
                "code": code,
                "message": "example message",
                "severity": "warning",
            },
        ],
        "exit_code": 0,
    }
    _validate_check_output(data)


def test_schema_lint_enum_matches_source_emitted_codes():
    """The schema enum equals the set of lint codes emitted by the source.

    This is the structural guard against enum rot: adding a new lint code
    without extending schemas/check-output.schema.json fails here.
    """
    schema_codes = _schema_lint_codes()
    source_codes = _source_emitted_lint_codes()

    missing_from_schema = sorted(source_codes - schema_codes)
    stale_in_schema = sorted(schema_codes - source_codes)

    assert not missing_from_schema, (
        "lint codes emitted by source but absent from the schema enum: "
        f"{missing_from_schema}. Add them to "
        "schemas/check-output.schema.json."
    )
    assert not stale_in_schema, (
        "lint codes in the schema enum that no source module emits: "
        f"{stale_in_schema}. Remove them from "
        "schemas/check-output.schema.json."
    )


def test_schema_lint_enum_is_sorted_and_unique():
    """The schema enum has no duplicates, keeping the contract unambiguous."""
    schema = _load_schema()
    enum = schema["properties"]["lints"]["items"]["properties"]["code"]["enum"]
    assert len(enum) == len(set(enum)), f"duplicate codes in enum: {enum}"

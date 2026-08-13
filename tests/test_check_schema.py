"""The declared payload schema of ``selfdoc check``.

Machine output is strictcli's ``--json`` mode: stdout carries the envelope
and the check document is its ``payload`` member. The document's shape is
declared as a JSON Schema literal in ``selfdoc/payload_schemas.py``, the
framework validates every emitted payload against it, and ``--dump-schema``
publishes it -- so the declaration is the single artifact a consumer
generates against, with no second copy to drift.

These tests hold the declaration to three things: it is what the command
actually declares, it accepts what the command actually emits, and its
lint-code enum stays exactly the registry in ``selfdoc_core/lints.toml``.
"""

import json
import os
import re
import subprocess
import sys

import pytest
import strictcli

from selfdoc import payload_schemas
from selfdoc.check import check_docs, check_result_exit_code, serialize_check_result
from selfdoc_core.lints import LINT_REGISTRY


# -- Validation helpers --


_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Modules that construct LintResult objects. Every lint code reachable from a
# CheckResult originates in one of these; the tests below pin both the schema
# enum and these construction sites to the registry in selfdoc_core/lints.toml.
_LINT_SOURCE_FILES = (
    os.path.join(_REPO_ROOT, "selfdoc", "check.py"),
    os.path.join(_REPO_ROOT, "selfblog", "check.py"),
)

_CODE_LITERAL_RE = re.compile(r'code\s*=\s*"([A-Z][A-Z0-9]*[0-9]{3})"')


def _schema():
    """The declared payload schema."""
    return payload_schemas.CHECK


def _schema_lint_codes():
    """The lint-code enum the declaration carries."""
    return set(
        _schema()["properties"]["lints"]["items"]["properties"]["code"]["enum"]
    )


def _schema_coverage():
    """The declaration's ``coverage`` subschema."""
    return _schema()["properties"]["coverage"]


def _cli_check_output(project_dir):
    """Run the real ``selfdoc check --json`` and return the envelope's payload.

    This is the shipped contract as consumers see it -- not a
    reconstruction of it -- so schema-completeness assertions below hold
    against what the CLI actually emits.
    """
    proc = subprocess.run(
        [
            sys.executable, "-m", "selfdoc",
            "check", "--json", "--no-auto-commit",
        ],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.stdout.strip(), (
        f"selfdoc check produced no stdout (exit {proc.returncode}):\n"
        f"{proc.stderr}"
    )
    envelope = json.loads(proc.stdout)
    return envelope["payload"]


def _source_emitted_lint_codes():
    """Scan the lint-producing modules for the code literals they name."""
    codes = set()
    for path in _LINT_SOURCE_FILES:
        assert os.path.isfile(path), (
            f"lint source file missing: {path} -- update _LINT_SOURCE_FILES"
        )
        with open(path, "r", encoding="utf-8") as f:
            codes.update(_CODE_LITERAL_RE.findall(f.read()))
    assert codes, "no lint codes found in source -- the scan regex is broken"
    return codes


_VALID_LINT_CODES = _schema_lint_codes()
_VALID_SEVERITIES = {"error", "warning"}


def _validate_check_output(data):
    """Emit *data* under the declaration, through the framework's validator.

    No hand-rolled mirror of the schema lives here any more: the framework
    validates a payload against its declaration where it writes the
    envelope, so the honest way to ask "does this document satisfy the
    contract" is to have it emitted. A deviation raises.
    """
    app = strictcli.App(name="probe", version="0.0.0", help="schema probe")

    @app.command(
        "emit", effect="read_only", help="emit the document",
        payload_schema=payload_schemas.CHECK,
    )
    def _emit(ctx):
        ctx.payload(data)
        return strictcli.outcome()

    result = app.test(["emit", "--json"])
    assert result.exit_code == 0, result.stderr
    return json.loads(result.stdout)["payload"]


def _serialize_check_result(result):
    """Serialize a CheckResult exactly as the CLI does.

    Delegates to the production serializer -- no reimplementation here.
    A hand-copied mirror of it drifted from cli.py once already (it never
    grew the documented/documented_symbols coverage fields), which is why
    these tests exercise the shipped function instead.

    These fixtures carry no project configuration, so the exit code is
    computed against the default coverage threshold.
    """
    return serialize_check_result(
        result, check_result_exit_code(result, config=None),
    )


# -- Fixtures --


@pytest.fixture()
def python_project(tmp_path):
    """Create a minimal Python project with selfdoc config and source files."""
    config = {
        "source": [{"path": "mylib/", "language": "python"}],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
        "author": {"name": "Test Author", "url": "https://author.example"},
        "search_engine": "pagefind",
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


def test_the_check_command_declares_this_schema():
    """The literal under test is the one the command registered."""
    from selfdoc.cli import app

    declared = app._commands["check"].payload_schema
    assert declared is payload_schemas.CHECK
    assert declared["type"] == "object"


def test_a_document_the_declaration_forbids_is_refused():
    """Enforcement is real: the framework refuses a deviating payload.

    Without this, every assertion below would only be testing that a
    validator accepts things.
    """
    with pytest.raises(RuntimeError, match="payload"):
        _validate_check_output({
            "directives": [],
            "coverage": None,
            "lints": [],
            "exit_code": 0,
            "unexpected": True,
        })


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
        "author": {"name": "Test Author", "url": "https://author.example"},
        "search_engine": "pagefind",
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

    Regression: the lint-code enum once listed only SEO*/STALE001, so
    consumers validating the check document rejected every example,
    doc-quality, param/return and drift code.
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


def test_schema_lint_enum_is_derived_from_the_registry():
    """The declared enum is exactly the registry, in sorted order.

    The declaration is a DERIVED surface: selfdoc_core/lints.toml is the
    single source of truth for which codes exist. Registering a code
    without extending selfdoc/payload_schemas.py fails here, and so does an
    enum entry no longer in the registry.
    """
    enum = _schema()["properties"]["lints"]["items"]["properties"]["code"]["enum"]
    expected = sorted(LINT_REGISTRY)

    assert sorted(enum) == expected, (
        "the declaration's lint-code enum has drifted from the registry in "
        "selfdoc_core/lints.toml. Missing from the declaration: "
        f"{sorted(set(expected) - set(enum))}; stale in the declaration: "
        f"{sorted(set(enum) - set(expected))}."
    )
    assert enum == expected, (
        "the declaration's lint-code enum must be sorted, matching the "
        "derivation order: sorted(LINT_REGISTRY)."
    )


def test_schema_severity_enum_matches_registry_severities():
    """The declared severity enum is exactly the severities the registry uses."""
    declared = (
        _schema()["properties"]["lints"]["items"]["properties"]["severity"]["enum"]
    )
    used = sorted({spec.severity for spec in LINT_REGISTRY.values()})
    assert sorted(declared) == used, (
        f"declared severity enum {sorted(declared)} does not match the "
        f"severities the registry uses ({used})."
    )


def test_every_code_literal_in_the_check_modules_is_registered():
    """No check module names a lint code the registry does not carry.

    LintResult refuses an unregistered code at construction time, so this is
    the static half of the same rule: a code literal on a path no test
    exercises is still caught here.
    """
    unregistered = sorted(_source_emitted_lint_codes() - set(LINT_REGISTRY))
    assert not unregistered, (
        f"lint codes named in the check modules but absent from the "
        f"registry: {unregistered}. Declare them in selfdoc_core/lints.toml."
    )


def test_schema_coverage_properties_match_emitted_fields(python_project):
    """The declared coverage object states exactly the fields the CLI emits.

    Structural guard against schema rot, sibling of the lint-enum test: a
    field the CLI emits but the declaration omits is now a hard emission
    failure, and a field the declaration requires but the CLI never emits is
    the same failure from the other side. This test names which one it is
    instead of leaving a validator message to be decoded.
    """
    data = _cli_check_output(python_project)
    assert data["coverage"] is not None, (
        "fixture project must produce coverage for this test to mean anything"
    )
    emitted = set(data["coverage"])

    coverage_schema = _schema_coverage()
    declared = set(coverage_schema["properties"])
    required = set(coverage_schema["required"])

    missing_from_schema = sorted(emitted - declared)
    stale_in_schema = sorted(declared - emitted)

    assert not missing_from_schema, (
        "coverage fields emitted by selfdoc check but absent from the "
        f"declaration: {missing_from_schema}. Add them to "
        "selfdoc/payload_schemas.py."
    )
    assert not stale_in_schema, (
        "coverage fields declared by the schema that selfdoc check never "
        f"emits: {stale_in_schema}. Remove them from "
        "selfdoc/payload_schemas.py."
    )
    # Every emitted field is unconditional, so all of them are required.
    assert required == emitted, (
        "the declaration's coverage.required must list every emitted field; "
        f"required={sorted(required)} emitted={sorted(emitted)}"
    )
    # Nullability is part of the contract: a project with no source to cover
    # emits null here, so the declaration carries the type list.
    assert coverage_schema["type"] == ["object", "null"]


def test_schema_lint_enum_is_sorted_and_unique():
    """The declared enum has no duplicates, keeping the contract unambiguous."""
    enum = _schema()["properties"]["lints"]["items"]["properties"]["code"]["enum"]
    assert len(enum) == len(set(enum)), f"duplicate codes in enum: {enum}"

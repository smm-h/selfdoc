"""Tests for the strictspec-governed directive catalogue document.

The built-in ``CORE_DIRECTIVES`` catalogue is built at import time from
``selfdoc_core/directives.toml`` -- a declarative descriptor document governed
by ``.strictspec/directive-descriptor.schema.toml`` and validated by the
strictspec-generated ``directive_descriptor_validator``. These tests lock in:

1. The real document loads and validates (the import-time gate is satisfied).
2. A malformed catalogue document is REJECTED with a hard error -- bad name
   grammar, unknown key, missing required field, bad category enum, absent
   format_version gate, and duplicate names each fail. This is behaviour that
   did not exist while the catalogue was a hand-maintained Python dict literal.
3. The loader turns any validation diagnostic into a ``CatalogDocumentError``
   (a hard error at import), never a silent partial catalogue.
"""

import importlib.resources as ir

import pytest

from selfdoc_core import catalog
from selfdoc_core import directive_descriptor_validator as validator


def _diag_codes(toml_text: str) -> list[str]:
    _root, diags = validator.validate_bytes(toml_text.encode(), "toml")
    return [d.code for d in diags]


# -- The real document is valid -----------------------------------------------


def test_real_directives_document_validates():
    raw = ir.files("selfdoc_core").joinpath("directives.toml").read_bytes()
    root, diags = validator.validate_bytes(raw, "toml")
    assert list(diags) == [], f"directives.toml is not valid: {[d.code for d in diags]}"
    assert root is not None
    # Every shipped core directive is present.
    assert len(root.directives) == len(catalog.CORE_DIRECTIVES) == 21


def test_loaded_catalogue_matches_document_order():
    raw = ir.files("selfdoc_core").joinpath("directives.toml").read_bytes()
    root, _ = validator.validate_bytes(raw, "toml")
    doc_names = [d.name for d in root.directives]
    assert list(catalog.CORE_DIRECTIVES) == doc_names


# -- A well-formed minimal document -------------------------------------------

_VALID = (
    "format_version = 1\n"
    "[[directives]]\n"
    'name = "ref"\n'
    'description = "Extract module docstring"\n'
    'category = "code"\n'
    'required_attrs = ["path"]\n'
    'optional_attrs = ["target", "lang"]\n'
    'example = ":::ref path=\\"m\\""\n'
)


def test_minimal_valid_document_has_no_diagnostics():
    assert _diag_codes(_VALID) == []


# -- Malformed documents are rejected -----------------------------------------


def test_bad_name_grammar_rejected():
    doc = _VALID.replace('name = "ref"', 'name = "1bad"')
    assert "STRICTSPEC_VALUE_STRING_REGEX" in _diag_codes(doc)


def test_name_with_illegal_char_rejected():
    doc = _VALID.replace('name = "ref"', 'name = "my.directive"')
    assert "STRICTSPEC_VALUE_STRING_REGEX" in _diag_codes(doc)


def test_unknown_key_rejected():
    doc = _VALID + 'extra_junk = "x"\n'
    assert "STRICTSPEC_KEY_UNKNOWN" in _diag_codes(doc)


def test_missing_required_field_rejected():
    doc = _VALID.replace('description = "Extract module docstring"\n', "")
    assert "STRICTSPEC_TYPE_MISSING_REQUIRED" in _diag_codes(doc)


def test_bad_category_enum_rejected():
    doc = _VALID.replace('category = "code"', 'category = "sideways"')
    assert "STRICTSPEC_TYPE_NOT_ENUM_MEMBER" in _diag_codes(doc)


def test_absent_format_version_gate_rejected():
    doc = _VALID.replace("format_version = 1\n", "")
    assert "STRICTSPEC_GATE_ABSENT" in _diag_codes(doc)


def test_duplicate_names_rejected():
    doc = _VALID + (
        "[[directives]]\n"
        'name = "ref"\n'
        'description = "dup"\n'
        'category = "code"\n'
        'required_attrs = ["path"]\n'
        'optional_attrs = []\n'
        'example = ":::ref"\n'
    )
    assert "STRICTSPEC_INTRA_UNIQUE_BY" in _diag_codes(doc)


# -- The loader turns diagnostics into a hard error ---------------------------


def test_build_catalogue_raises_on_malformed_document():
    bad = _VALID.replace('name = "ref"', 'name = "1bad"').encode()
    with pytest.raises(catalog.CatalogDocumentError) as exc:
        catalog._build_catalogue(bad)
    # The error surfaces the offending diagnostic for actionability.
    assert "STRICTSPEC_VALUE_STRING_REGEX" in str(exc.value)


def test_build_catalogue_binds_valid_document():
    built = catalog._build_catalogue(_VALID.encode())
    assert set(built) == {"ref"}
    spec = built["ref"]
    assert spec.category == "code"
    assert spec.required_attrs == ["path"]
    assert spec.optional_attrs == ["target", "lang"]

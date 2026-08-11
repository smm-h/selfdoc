# strictspec generated validator. DO NOT EDIT.
#
# strictspec generator: 0.1.0
# schema:              selfdoc-lint-registry (format_version 1)
# regenerate:          strictspec gen --manifest strictspec.toml
#
# Released under the MIT license (unencumbered). This file is machine-generated;
# edit the schema and regenerate, never this file.
# ruff: noqa
from __future__ import annotations

from dataclasses import dataclass, replace

import strictspec
from strictspec import Diagnostic, Value

# GENERATED_BY is the strictspec release that produced this file. The runtime
# pairing guard hard-errors unless it matches the linked runtime exactly.
GENERATED_BY = "0.1.0"
SCHEMA_FORMAT_VERSION = 1

# _EMBEDDED_SCHEMA carries the compiled schema (and its imported type-definition
# files and scalar manifest) so the validator is self-contained and does no IO.
_EMBEDDED_SCHEMA = {
    "lint-registry.schema.toml": "# strictspec schema -- selfdoc lint-code registry.\n#\n# Governs selfdoc_core/lints.toml: the declarative document that is the single\n# source of truth for every lint code selfdoc and selfblog can emit, with its\n# severity and its one-line description. The generated validator\n# (lint_registry_validator.py) validates the document at load time in\n# selfdoc_core.lints; a malformed registry is a hard error at import, before\n# any check runs.\n#\n# SCOPE (honest subset): this schema owns the raw DOCUMENT SHAPE of the registry\n# -- the code grammar, the severity enum, per-entry required fields,\n# unknown-key rejection, and unique codes. It does NOT model where a code is\n# emitted from, which condition raises it, or whether the JSON output schema\n# and the documentation table agree with it. Those are selfdoc-native: the\n# emission side is enforced structurally (LintResult derives severity from this\n# registry and refuses an unregistered code), and the two derived surfaces are\n# pinned to the registry by tests.\n\nname = \"selfdoc-lint-registry\"\nmeta_version = 1\nformat_version = 1\ndocument_syntax = \"toml\"\nrole = \"schema\"\nroot = \"LintRegistry\"\ndescription = \"The selfdoc lint-code registry: one entry per emittable lint code (code, severity, description).\"\n\n[types.LintRegistry]\ntype = \"record\"\n\n[types.LintRegistry.fields.format_version]\ntype = \"integer\"\nrequired = true\ndescription = \"Document format-version gate. v1 documents carry 1.\"\n\n[types.LintRegistry.fields.lints]\ntype = \"array\"\nrequired = true\nmin_len = 1\ndescription = \"The registered lint codes, in documentation order.\"\n[types.LintRegistry.fields.lints.item]\ntype = \"LintDescriptor\"\n\n# Codes are unique across the registry (the loader keys a dict by them).\n[[types.LintRegistry.constraints]]\nform = \"unique-by\"\ncollection = \"lints\"\nfield = \"code\"\nnormalization = \"none\"\n\n# --- named types ---\n\n[types.LintDescriptor]\ntype = \"record\"\ndescription = \"Registry entry for a single lint code.\"\n\n[types.LintDescriptor.fields.code]\ntype = \"string\"\nrequired = true\nnon_empty = true\nregex = '^[A-Z][A-Z0-9]*[0-9]{3}$'\ndescription = \"Lint code. Grammar: an uppercase family name followed by a three-digit number (SEO001, DRIFT001, POST005).\"\n\n[types.LintDescriptor.fields.severity]\ntype = \"enum\"\nrequired = true\nvalues = [\"error\", \"warning\"]\ndescription = \"\\\"error\\\" fails the check run; \\\"warning\\\" is informational and never changes the exit code.\"\n\n[types.LintDescriptor.fields.description]\ntype = \"string\"\nrequired = true\nnon_empty = true\ndescription = \"One-line description of what the rule checks, rendered verbatim into the documentation's lint-rule table.\"\n",
}
_EMBEDDED_MAIN_FILE = "lint-registry.schema.toml"

# Version pairing: generated code and runtime must be the same release. This runs
# at import, so a skewed runtime hard-errors before any validation is attempted.
strictspec.require_runtime_version(GENERATED_BY)
_program = strictspec.compile_embedded(_EMBEDDED_SCHEMA, _EMBEDDED_MAIN_FILE)


def validate_bytes(input: bytes, syntax: str) -> tuple[LintRegistry | None, tuple[Diagnostic, ...]]:
    """RAW-BYTES entry point: lossless parse of input in the given syntax
    ("json" | "toml" | "jsonl"), then validate. Returns the typed root value
    (None when any diagnostic fired) and the ordered diagnostics.
    """
    return validate_bytes_with_evidence(input, syntax, None)


def validate_bytes_with_evidence(input: bytes, syntax: str, evidence: dict | None) -> tuple[LintRegistry | None, tuple[Diagnostic, ...]]:
    """validate_bytes plus cross-document resolver evidence for the phase-2
    constraint vocabulary.
    """
    result = _program.validate_with_evidence(input, syntax, evidence)
    if not result.valid:
        return None, result.diagnostics
    v = strictspec.load_value(input, syntax)
    return _bind_LintRegistry(v), result.diagnostics


def validate_value(v: Value) -> tuple[LintRegistry | None, tuple[Diagnostic, ...]]:
    """TAGGED-VALUE entry point: validate an already-parsed tagged document value
    (from strictspec.load_value or a typed constructor). Raw untagged dicts are
    never accepted.
    """
    result = _program.validate_value(v)
    if not result.valid:
        return None, result.diagnostics
    return _bind_LintRegistry(v), result.diagnostics


@dataclass(frozen=True, kw_only=True)
class LintRegistry:
    """Frozen typed binding of the "LintRegistry" record. Immutable; use with_* for
    copy-on-write.
    """

    format_version: int
    lints: list[LintDescriptor]

    def with_format_version(self, v: int) -> LintRegistry:
        return replace(self, format_version=v)

    def with_lints(self, v: list[LintDescriptor]) -> LintRegistry:
        return replace(self, lints=v)


def _bind_LintRegistry(v: Value) -> LintRegistry | None:
    if v.kind() != strictspec.Kind.RECORD:
        return None
    f_format_version = v.field("format_version")
    f_lints = v.field("lints")
    return LintRegistry(
        format_version=(f_format_version[0].int()[0] if f_format_version[1] else 0),
        lints=([_bind_LintDescriptor(e) for e in f_lints[0].items()] if f_lints[1] else []),
    )


@dataclass(frozen=True, kw_only=True)
class LintDescriptor:
    """Frozen typed binding of the "LintDescriptor" record. Immutable; use with_* for
    copy-on-write.
    """

    code: str
    severity: str
    description: str

    def with_code(self, v: str) -> LintDescriptor:
        return replace(self, code=v)

    def with_severity(self, v: str) -> LintDescriptor:
        return replace(self, severity=v)

    def with_description(self, v: str) -> LintDescriptor:
        return replace(self, description=v)


def _bind_LintDescriptor(v: Value) -> LintDescriptor | None:
    if v.kind() != strictspec.Kind.RECORD:
        return None
    f_code = v.field("code")
    f_severity = v.field("severity")
    f_description = v.field("description")
    return LintDescriptor(
        code=(f_code[0].string()[0] if f_code[1] else ""),
        severity=(f_severity[0].string()[0] if f_severity[1] else ""),
        description=(f_description[0].string()[0] if f_description[1] else ""),
    )



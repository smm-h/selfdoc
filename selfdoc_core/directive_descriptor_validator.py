# strictspec generated validator. DO NOT EDIT.
#
# strictspec generator: 0.1.0
# schema:              selfdoc-directive-catalogue (format_version 1)
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
    "directive-descriptor.schema.toml": "# strictspec schema -- selfdoc built-in directive catalogue.\n#\n# Governs selfdoc_core/directives.toml: the declarative descriptor document that\n# is the single source of truth for the ~20 shipped (\"core\") built-in directives.\n# The generated validator (directive_descriptor_validator.py) gates the document\n# at load time in selfdoc_core.catalog; a malformed catalogue is a hard error at\n# import, before any directive is dispatched.\n#\n# SCOPE (honest subset): this schema owns the raw DOCUMENT SHAPE of the catalogue\n# -- the name grammar, the code/content category enum, required/optional attr\n# lists, per-descriptor required fields, unknown-key rejection, and unique names.\n# It does NOT model the RUNTIME couplings selfdoc keeps native: which resolver\n# runs for which name (the resolve_content dispatch + extractor path), custom and\n# future directive names (which carry no descriptor and skip attr enforcement by\n# design), and the catalog-vs-resolver attribute-consistency oracle (a curated\n# test). Those remain selfdoc-native by declaration.\n\nname = \"selfdoc-directive-catalogue\"\nmeta_version = 1\nformat_version = 1\ndocument_syntax = \"toml\"\nrole = \"schema\"\nroot = \"DirectiveCatalogue\"\ndescription = \"The selfdoc built-in directive catalogue: one descriptor per shipped directive (name, description, category, required/optional attributes, example).\"\n\n[types.DirectiveCatalogue]\ntype = \"record\"\n\n[types.DirectiveCatalogue.fields.format_version]\ntype = \"integer\"\nrequired = true\ndescription = \"Document format-version gate. v1 documents carry 1.\"\n\n[types.DirectiveCatalogue.fields.directives]\ntype = \"array\"\nrequired = true\nmin_len = 1\ndescription = \"The shipped built-in directives, in catalogue order.\"\n[types.DirectiveCatalogue.fields.directives.item]\ntype = \"DirectiveDescriptor\"\n\n# Directive names are unique across the catalogue (the loader keys a dict by them).\n[[types.DirectiveCatalogue.constraints]]\nform = \"unique-by\"\ncollection = \"directives\"\nfield = \"name\"\nnormalization = \"none\"\n\n# --- named types ---\n\n[types.DirectiveDescriptor]\ntype = \"record\"\ndescription = \"Metadata for a single built-in directive.\"\n\n[types.DirectiveDescriptor.fields.name]\ntype = \"string\"\nrequired = true\nnon_empty = true\nregex = '^[a-zA-Z][\\w-]*$'\ndescription = \"Directive name. Grammar: starts with a letter, then word chars or hyphens (the directive-name PATTERN).\"\n\n[types.DirectiveDescriptor.fields.description]\ntype = \"string\"\nrequired = true\nnon_empty = true\ndescription = \"One-line human description shown in the directive reference table.\"\n\n[types.DirectiveDescriptor.fields.category]\ntype = \"enum\"\nrequired = true\nvalues = [\"code\", \"content\"]\ndescription = \"\\\"code\\\" directives dispatch to a language extractor (path-based); \\\"content\\\" directives resolve language-agnostically.\"\n\n[types.DirectiveDescriptor.fields.required_attrs]\ntype = \"array\"\nrequired = true\ndescription = \"Attribute names the directive requires (may be empty).\"\n[types.DirectiveDescriptor.fields.required_attrs.item]\ntype = \"string\"\n\n[types.DirectiveDescriptor.fields.optional_attrs]\ntype = \"array\"\nrequired = true\ndescription = \"Attribute names the directive optionally accepts (may be empty).\"\n[types.DirectiveDescriptor.fields.optional_attrs.item]\ntype = \"string\"\n\n[types.DirectiveDescriptor.fields.example]\ntype = \"string\"\nrequired = true\nnon_empty = true\ndescription = \"A representative usage example.\"\n",
}
_EMBEDDED_MAIN_FILE = "directive-descriptor.schema.toml"

# Version pairing: generated code and runtime must be the same release. This runs
# at import, so a skewed runtime hard-errors before any validation is attempted.
strictspec.require_runtime_version(GENERATED_BY)
_program = strictspec.compile_embedded(_EMBEDDED_SCHEMA, _EMBEDDED_MAIN_FILE)


def validate_bytes(input: bytes, syntax: str) -> tuple[DirectiveCatalogue | None, tuple[Diagnostic, ...]]:
    """RAW-BYTES entry point: lossless parse of input in the given syntax
    ("json" | "toml" | "jsonl"), then validate. Returns the typed root value
    (None when any diagnostic fired) and the ordered diagnostics.
    """
    return validate_bytes_with_evidence(input, syntax, None)


def validate_bytes_with_evidence(input: bytes, syntax: str, evidence: dict | None) -> tuple[DirectiveCatalogue | None, tuple[Diagnostic, ...]]:
    """validate_bytes plus cross-document resolver evidence for the phase-2
    constraint vocabulary.
    """
    result = _program.validate_with_evidence(input, syntax, evidence)
    if not result.valid:
        return None, result.diagnostics
    v = strictspec.load_value(input, syntax)
    return _bind_DirectiveCatalogue(v), result.diagnostics


def validate_value(v: Value) -> tuple[DirectiveCatalogue | None, tuple[Diagnostic, ...]]:
    """TAGGED-VALUE entry point: validate an already-parsed tagged document value
    (from strictspec.load_value or a typed constructor). Raw untagged dicts are
    never accepted.
    """
    result = _program.validate_value(v)
    if not result.valid:
        return None, result.diagnostics
    return _bind_DirectiveCatalogue(v), result.diagnostics


@dataclass(frozen=True, kw_only=True)
class DirectiveCatalogue:
    """Frozen typed binding of the "DirectiveCatalogue" record. Immutable; use with_* for
    copy-on-write.
    """

    format_version: int
    directives: list[DirectiveDescriptor]

    def with_format_version(self, v: int) -> DirectiveCatalogue:
        return replace(self, format_version=v)

    def with_directives(self, v: list[DirectiveDescriptor]) -> DirectiveCatalogue:
        return replace(self, directives=v)


def _bind_DirectiveCatalogue(v: Value) -> DirectiveCatalogue | None:
    if v.kind() != strictspec.Kind.RECORD:
        return None
    f_format_version = v.field("format_version")
    f_directives = v.field("directives")
    return DirectiveCatalogue(
        format_version=(f_format_version[0].int()[0] if f_format_version[1] else 0),
        directives=([_bind_DirectiveDescriptor(e) for e in f_directives[0].items()] if f_directives[1] else []),
    )


@dataclass(frozen=True, kw_only=True)
class DirectiveDescriptor:
    """Frozen typed binding of the "DirectiveDescriptor" record. Immutable; use with_* for
    copy-on-write.
    """

    name: str
    description: str
    category: str
    required_attrs: list[str]
    optional_attrs: list[str]
    example: str

    def with_name(self, v: str) -> DirectiveDescriptor:
        return replace(self, name=v)

    def with_description(self, v: str) -> DirectiveDescriptor:
        return replace(self, description=v)

    def with_category(self, v: str) -> DirectiveDescriptor:
        return replace(self, category=v)

    def with_required_attrs(self, v: list[str]) -> DirectiveDescriptor:
        return replace(self, required_attrs=v)

    def with_optional_attrs(self, v: list[str]) -> DirectiveDescriptor:
        return replace(self, optional_attrs=v)

    def with_example(self, v: str) -> DirectiveDescriptor:
        return replace(self, example=v)


def _bind_DirectiveDescriptor(v: Value) -> DirectiveDescriptor | None:
    if v.kind() != strictspec.Kind.RECORD:
        return None
    f_name = v.field("name")
    f_description = v.field("description")
    f_category = v.field("category")
    f_required_attrs = v.field("required_attrs")
    f_optional_attrs = v.field("optional_attrs")
    f_example = v.field("example")
    return DirectiveDescriptor(
        name=(f_name[0].string()[0] if f_name[1] else ""),
        description=(f_description[0].string()[0] if f_description[1] else ""),
        category=(f_category[0].string()[0] if f_category[1] else ""),
        required_attrs=([e.string()[0] for e in f_required_attrs[0].items()] if f_required_attrs[1] else []),
        optional_attrs=([e.string()[0] for e in f_optional_attrs[0].items()] if f_optional_attrs[1] else []),
        example=(f_example[0].string()[0] if f_example[1] else ""),
    )



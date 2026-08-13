"""Declared payload schemas for selfdoc's machine-mode commands.

strictcli's machine mode (``--json``) writes one document to stdout -- the
envelope -- and a command's machine output is the envelope's ``payload``
member.  Every such command declares that payload's JSON Schema at
registration time, and the framework validates the value against the
declaration where it writes the envelope: a deviating document fails the run
instead of reaching a consumer.

The declarations live here, apart from the code that produces the documents,
for one reason: they are read at import time by ``selfdoc/cli.py`` when it
registers its commands, and the check module they would otherwise sit beside
costs a tenth of a second to import.  A module of literals with no imports
keeps every command's startup free of it.

The literals are written in the framework's closed subset (``type`` including
type lists, ``properties``, ``required``, ``items``, ``enum``, ``const``,
``additionalProperties``), so an unknown keyword is rejected at registration
time.  ``--dump-schema`` publishes them verbatim, which makes each one the
single artifact a consumer generates against.
"""

#: Lint codes ``selfdoc check`` can emit.  This list is the shipped contract;
#: ``selfdoc_core/lints.toml`` is where codes are actually declared, and
#: ``tests/test_check_schema.py`` fails when the two drift apart.
_LINT_CODES = [
    "CLI001", "CLI002",
    "DQ001", "DQ002", "DQ003",
    "DRIFT001",
    "EXAMPLE001", "EXAMPLE002", "EXAMPLE003",
    "LANG001",
    "LINK001",
    "PARAM001",
    "POST001", "POST002", "POST003", "POST004", "POST005",
    "POST006", "POST007",
    "RETURN001",
    "SEARCH001",
    "SEO001", "SEO002", "SEO003", "SEO004", "SEO006", "SEO007",
    "SEO008", "SEO009", "SEO010", "SEO011", "SEO012", "SEO013",
    "SEO014", "SEO015",
    "SPELL001",
    "STALE001", "STALE002",
    "UNIFIED001", "UNIFIED002",
    "VER001", "VER002", "VER003", "VER004",
    "XREF001", "XREF002",
]

#: ``selfdoc check`` -- one directive result per directive found, the coverage
#: block (null when the project has no source to cover), every lint the run
#: kept after suppression, and the exit code the command will terminate with.
CHECK = {
    "type": "object",
    "properties": {
        "directives": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "directive": {"type": "string"},
                    "status": {"type": "string", "enum": ["OK", "FAILED"]},
                    "error": {"type": "string"},
                },
                "required": ["file", "line", "directive", "status", "error"],
                "additionalProperties": False,
            },
        },
        "coverage": {
            "type": ["object", "null"],
            "properties": {
                "total_public": {"type": "integer"},
                "referenced": {"type": "integer"},
                "documented": {"type": "integer"},
                "referenced_symbols": {"type": "array", "items": {"type": "string"}},
                "documented_symbols": {"type": "array", "items": {"type": "string"}},
                "unreferenced_symbols": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "total_public", "referenced", "documented",
                "referenced_symbols", "documented_symbols",
                "unreferenced_symbols",
            ],
            "additionalProperties": False,
        },
        "lints": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": ["integer", "null"]},
                    "code": {"type": "string", "enum": _LINT_CODES},
                    "message": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["error", "warning"],
                    },
                },
                "required": ["file", "line", "code", "message", "severity"],
                "additionalProperties": False,
            },
        },
        "exit_code": {"type": "integer", "enum": [0, 1]},
    },
    "required": ["directives", "coverage", "lints", "exit_code"],
    "additionalProperties": False,
}

#: ``selfdoc spell-corpus`` -- the sweep's inputs (which accept list and how
#: many terms and words it holds), one entry per project visited, and the
#: corpus-wide flagged total.  ``error`` is set instead of results for a
#: project that could not be read.
SPELL_CORPUS = {
    "type": "object",
    "properties": {
        "root": {"type": "string"},
        "accept_list": {"type": "string"},
        "accepted_terms": {"type": "integer"},
        "wordlist_words": {"type": "integer"},
        "projects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                    "pages": {"type": "integer"},
                    "error": {"type": ["string", "null"]},
                    "misspellings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "file": {"type": "string"},
                                "line": {"type": "integer"},
                                "column": {"type": "integer"},
                                "word": {"type": "string"},
                                "suggestions": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": [
                                "file", "line", "column", "word", "suggestions",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["project", "pages", "error", "misspellings"],
                "additionalProperties": False,
            },
        },
        "total": {"type": "integer"},
    },
    "required": [
        "root", "accept_list", "accepted_terms", "wordlist_words",
        "projects", "total",
    ],
    "additionalProperties": False,
}

#: ``selfdoc quality`` -- one project's score.  ``doc_ratio`` is null when
#: there is no source to divide by, and ``next_step`` is null at tier 5 where
#: nothing is left to do.  The ``selfdoc`` block carries only ``has_selfdoc``
#: for a project that has no readable selfdoc.json.
QUALITY = {
    "type": "object",
    "properties": {
        "project": {"type": "string"},
        "path": {"type": "string"},
        "tier": {"type": "integer", "enum": [0, 1, 2, 3, 4, 5]},
        "tier_name": {"type": "string"},
        "code_loc": {"type": "integer"},
        "test_loc": {"type": "integer"},
        "source_loc": {"type": "integer"},
        "doc_loc": {"type": "integer"},
        "doc_files": {"type": "integer"},
        "doc_ratio": {"type": ["number", "null"]},
        # "-" is the grade of a project with no source to compare against,
        # which is not the same answer as failing.
        "content_grade": {
            "type": "string",
            "enum": ["A", "B", "C", "D", "F", "-"],
        },
        "selfdoc": {
            "type": "object",
            "properties": {
                "has_selfdoc": {"type": "boolean"},
                "auto_readme": {"type": "boolean"},
                "auto_claude": {"type": "boolean"},
                "custom_directives": {"type": "integer"},
                "has_posts": {"type": "boolean"},
                "directive_count": {"type": "integer"},
            },
            "required": ["has_selfdoc"],
            "additionalProperties": False,
        },
        "next_step": {"type": ["string", "null"]},
    },
    "required": [
        "project", "path", "tier", "tier_name", "code_loc", "test_loc",
        "source_loc", "doc_loc", "doc_files", "doc_ratio", "content_grade",
        "selfdoc", "next_step",
    ],
    "additionalProperties": False,
}

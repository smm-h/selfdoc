"""SQL schema extractor for selfdoc -- parses PostgreSQL DDL files to extract table definitions, views, types, functions, and COMMENT ON documentation.

Uses regex-based parsing (no database connection required). Handles:
- :::ref         -- list all CREATE objects with comments, grouped by type
- :::prose-desc  -- extract COMMENT ON TABLE text for a specific table
- :::table-schema -- extract table columns as a markdown table
- :::table-config -- extract config file contents as tables (JSON/TOML)
"""

import os
import re

from selfdoc.extractors.base import (
    BaseExtractor,
    format_error,
    handle_table_config,
    read_source,
)
from selfdoc.tables import render_markdown_table

# Regex for CREATE statements (case-insensitive).
# Matches: CREATE [OR REPLACE] [TABLE|VIEW|TYPE|FUNCTION] [IF NOT EXISTS] [schema.]name
_CREATE_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?"
    r"(?:TABLE|VIEW|TYPE|FUNCTION)\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?:(\w+)\.)?(\w+)",
    re.IGNORECASE,
)


class SqlExtractor(BaseExtractor):
    """SQL schema extractor implementing LanguageExtractor protocol."""

    @property
    def name(self) -> str:
        return "sql"

    def detect(self, dir_path: str) -> bool:
        # SQL is declared explicitly in selfdoc.json, never auto-detected.
        return False

    def resolve_path(
        self, path_arg: str, source_paths: list[str], base_dir: str
    ) -> str | None:
        return _resolve_sql_path(path_arg, source_paths, base_dir)

    def file_extensions(self) -> list[str]:
        return [".sql"]

    def public_symbols(self, file_path: str) -> list[str]:
        """Extract CREATE TABLE/VIEW/TYPE/FUNCTION names from a SQL file.

        Handles schema-qualified names (extracts the unqualified name only),
        OR REPLACE, and IF NOT EXISTS. Skips comment lines.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return []

        source = _strip_sql_comments(source)
        symbols = []
        for m in _CREATE_RE.finditer(source):
            sym_name = m.group(2)
            if sym_name not in symbols:
                symbols.append(sym_name)
        return symbols

    def symbol_details(self, file_path: str, symbol_name: str) -> dict | None:
        """Return parameter and return type details for a CREATE FUNCTION.

        Returns None for non-function symbols (tables, views, types) or
        if the symbol is not found.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return None

        clean = _strip_sql_comments(source)
        comments = _parse_comments(source)
        return _function_symbol_details(clean, symbol_name, comments)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def _resolve_sql_path(path_arg, source_paths, base_dir):
    """Resolve a path argument to a SQL file.

    Tries each source_path prefix, then the base_dir directly.
    Appends .sql extension if the path has no match.
    """
    candidates = []
    for sp in source_paths:
        candidates.append(os.path.join(base_dir, sp, path_arg))
    candidates.append(os.path.join(base_dir, path_arg))

    for candidate in candidates:
        if os.path.isdir(candidate):
            if any(f.endswith(".sql") for f in os.listdir(candidate)):
                return candidate
        if os.path.isfile(candidate):
            return candidate
        sql_candidate = candidate + ".sql"
        if os.path.isfile(sql_candidate):
            return sql_candidate

    return None


# ---------------------------------------------------------------------------
# Comment stripping
# ---------------------------------------------------------------------------


def _strip_sql_comments(source):
    """Remove SQL line comments (--) and block comments (/* */) from source.

    Preserves string literals (single-quoted and dollar-quoted) so that
    comment markers inside strings are not stripped.
    """
    result = []
    i = 0
    n = len(source)

    while i < n:
        # Single-quoted string literal
        if source[i] == "'":
            end = _skip_single_quoted(source, i)
            result.append(source[i:end])
            i = end
        # Dollar-quoted string literal
        elif source[i] == "$":
            tag_match = re.match(r"\$(\w*)\$", source[i:])
            if tag_match:
                tag = tag_match.group(0)
                end_pos = source.find(tag, i + len(tag))
                if end_pos >= 0:
                    end = end_pos + len(tag)
                    result.append(source[i:end])
                    i = end
                else:
                    result.append(source[i])
                    i += 1
            else:
                result.append(source[i])
                i += 1
        # Line comment
        elif source[i : i + 2] == "--":
            # Skip to end of line
            eol = source.find("\n", i)
            if eol < 0:
                break
            i = eol  # keep the newline
        # Block comment
        elif source[i : i + 2] == "/*":
            end = source.find("*/", i + 2)
            if end < 0:
                break
            i = end + 2
        else:
            result.append(source[i])
            i += 1

    return "".join(result)


def _skip_single_quoted(source, start):
    """Skip past a single-quoted string starting at start.

    Handles '' escape for embedded quotes. Returns the index after the
    closing quote.
    """
    i = start + 1
    n = len(source)
    while i < n:
        if source[i] == "'":
            if i + 1 < n and source[i + 1] == "'":
                i += 2  # escaped quote
            else:
                return i + 1  # end of string
        else:
            i += 1
    return n  # unterminated string


# ---------------------------------------------------------------------------
# Parsing: CREATE TABLE
# ---------------------------------------------------------------------------

_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?:(\w+)\.)?(\w+)\s*\(",
    re.IGNORECASE,
)


def _split_column_defs(columns_text):
    """Split column definitions by commas, respecting parenthesis nesting.

    Returns a list of column definition strings.
    """
    parts = []
    depth = 0
    current = []

    for ch in columns_text:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)

    trailing = "".join(current).strip()
    if trailing:
        parts.append(trailing)
    return parts


# Table-level constraint prefixes to skip
_TABLE_CONSTRAINT_PREFIXES = (
    "CHECK",
    "CONSTRAINT",
    "PRIMARY KEY",
    "UNIQUE",
    "FOREIGN KEY",
    "EXCLUDE",
)


def _parse_column_def(col_text):
    """Parse a single column definition into a dict.

    Returns {name, type, nullable, default, constraints, description} or
    None if this is a table-level constraint.
    """
    col_text = col_text.strip()
    if not col_text:
        return None

    upper = col_text.strip().upper()
    for prefix in _TABLE_CONSTRAINT_PREFIXES:
        if upper.startswith(prefix):
            return None

    # Extract the column name (first word)
    tokens = col_text.split()
    if not tokens:
        return None
    col_name = tokens[0]

    # The rest is type + constraints
    rest = col_text[len(col_name):].strip()

    nullable = True
    default = ""
    constraints = []

    # Extract type: everything before the first recognized constraint keyword
    # at the top level (not inside parentheses)
    type_str, remainder = _extract_type(rest)

    # Parse remainder for constraints
    remainder_upper = remainder.upper()

    # NOT NULL
    if re.search(r"\bNOT\s+NULL\b", remainder_upper):
        nullable = False
        remainder = re.sub(r"\bNOT\s+NULL\b", "", remainder, flags=re.IGNORECASE).strip()

    # NULL (explicit)
    if re.search(r"(?<!\bNOT\s)\bNULL\b", remainder_upper):
        nullable = True
        remainder = re.sub(r"(?<!\bNOT\s)\bNULL\b", "", remainder, flags=re.IGNORECASE).strip()

    # GENERATED ALWAYS AS IDENTITY / GENERATED BY DEFAULT AS IDENTITY
    identity_match = re.search(
        r"\bGENERATED\s+(ALWAYS|BY\s+DEFAULT)\s+AS\s+IDENTITY\b",
        remainder,
        re.IGNORECASE,
    )
    if identity_match:
        default = identity_match.group(0).upper()
        remainder = remainder[:identity_match.start()] + remainder[identity_match.end():]
        remainder = remainder.strip()

    # GENERATED ALWAYS AS (expr) STORED
    generated_match = re.search(
        r"\bGENERATED\s+ALWAYS\s+AS\s*\(",
        remainder,
        re.IGNORECASE,
    )
    if generated_match and not default:
        # Find the matching closing paren
        start = generated_match.start()
        paren_start = remainder.index("(", generated_match.start())
        depth = 0
        end = paren_start
        for idx in range(paren_start, len(remainder)):
            if remainder[idx] == "(":
                depth += 1
            elif remainder[idx] == ")":
                depth -= 1
                if depth == 0:
                    end = idx
                    break
        # Check for STORED after the closing paren
        after_paren = remainder[end + 1:].strip()
        if after_paren.upper().startswith("STORED"):
            stored_len = len("STORED")
            full_expr = remainder[start:end + 1 + len(remainder[end + 1:]) - len(after_paren[stored_len:])]
            full_expr = remainder[start:end + 1] + " STORED"
            default = full_expr.strip()
            remainder = remainder[:start] + remainder[end + 1 + len(after_paren[:stored_len]):].lstrip()
            remainder = remainder.strip()
        else:
            full_expr = remainder[start:end + 1]
            default = full_expr.strip()
            remainder = remainder[:start] + remainder[end + 1:].strip()

    # DEFAULT value
    if not default:
        default_match = re.search(r"\bDEFAULT\s+", remainder, re.IGNORECASE)
        if default_match:
            default_start = default_match.end()
            default_val = _extract_default_value(remainder[default_start:])
            default = default_val
            # Remove the DEFAULT clause from remainder
            remainder = remainder[:default_match.start()] + remainder[default_start + len(default_val):].strip()
            remainder = remainder.strip()

    # PRIMARY KEY
    if re.search(r"\bPRIMARY\s+KEY\b", remainder, re.IGNORECASE):
        constraints.append("PRIMARY KEY")
        remainder = re.sub(r"\bPRIMARY\s+KEY\b", "", remainder, flags=re.IGNORECASE).strip()

    # UNIQUE
    if re.search(r"\bUNIQUE\b", remainder, re.IGNORECASE):
        constraints.append("UNIQUE")
        remainder = re.sub(r"\bUNIQUE\b", "", remainder, flags=re.IGNORECASE).strip()

    # REFERENCES
    ref_match = re.search(
        r"\bREFERENCES\s+(\w+(?:\.\w+)?)\s*(\([^)]*\))?",
        remainder,
        re.IGNORECASE,
    )
    if ref_match:
        ref_str = "REFERENCES " + ref_match.group(1)
        if ref_match.group(2):
            ref_str += ref_match.group(2)
        constraints.append(ref_str)
        remainder = remainder[:ref_match.start()] + remainder[ref_match.end():].strip()

    # CHECK constraint
    check_match = re.search(r"\bCHECK\s*\(", remainder, re.IGNORECASE)
    if check_match:
        paren_start = remainder.index("(", check_match.start())
        depth = 0
        end = paren_start
        for idx in range(paren_start, len(remainder)):
            if remainder[idx] == "(":
                depth += 1
            elif remainder[idx] == ")":
                depth -= 1
                if depth == 0:
                    end = idx
                    break
        check_str = remainder[check_match.start():end + 1]
        constraints.append(check_str)
        remainder = remainder[:check_match.start()] + remainder[end + 1:].strip()

    return {
        "name": col_name,
        "type": type_str,
        "nullable": nullable,
        "default": default,
        "constraints": constraints,
        "description": "",
    }


def _extract_type(rest):
    """Extract the SQL type from the beginning of a column definition remainder.

    Returns (type_string, remaining_text). Handles types with parentheses
    like NUMERIC(10,2) and array syntax like text[].
    """
    # Constraint keywords that signal end of type
    constraint_keywords = {
        "NOT", "NULL", "DEFAULT", "PRIMARY", "UNIQUE", "REFERENCES",
        "CHECK", "GENERATED", "CONSTRAINT", "COLLATE",
    }

    tokens = []
    i = 0
    n = len(rest)

    while i < n:
        # Skip whitespace
        while i < n and rest[i].isspace():
            i += 1
        if i >= n:
            break

        # Check for parenthesized expression (part of type like NUMERIC(10,2))
        if rest[i] == "(":
            depth = 0
            start = i
            while i < n:
                if rest[i] == "(":
                    depth += 1
                elif rest[i] == ")":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            paren_text = rest[start:i]
            if tokens:
                tokens[-1] += paren_text
            # Check for array brackets after parens
            while i < n and rest[i] == "[":
                bracket_start = i
                while i < n and rest[i] != "]":
                    i += 1
                if i < n:
                    i += 1
                tokens[-1] += rest[bracket_start:i]
            continue

        # Check for array brackets (text[])
        if rest[i] == "[":
            bracket_start = i
            while i < n and rest[i] != "]":
                i += 1
            if i < n:
                i += 1
            if tokens:
                tokens[-1] += rest[bracket_start:i]
            continue

        # Read a word
        word_start = i
        while i < n and not rest[i].isspace() and rest[i] not in "([":
            i += 1
        word = rest[word_start:i]

        if not word:
            break

        # Check if this word is a constraint keyword
        if word.upper() in constraint_keywords:
            # Put the cursor back; this word is not part of the type
            i = word_start
            break

        tokens.append(word)

    type_str = " ".join(tokens)
    remaining = rest[i:].strip()
    return type_str, remaining


def _extract_default_value(text):
    """Extract a DEFAULT value expression from text.

    Handles simple values, function calls with parentheses, and
    quoted strings. Stops at the next constraint keyword or comma.
    """
    text = text.strip()
    if not text:
        return ""

    # Single-quoted string
    if text[0] == "'":
        end = _skip_single_quoted(text, 0)
        # Check for type cast after string
        rest = text[end:]
        cast_match = re.match(r"\s*::\s*\w+(\[\])?", rest)
        if cast_match:
            end += cast_match.end()
        return text[:end].strip()

    # Parenthesized expression or function call
    end_keywords = {
        "NOT", "NULL", "PRIMARY", "UNIQUE", "REFERENCES", "CHECK",
        "CONSTRAINT", "GENERATED", "COLLATE",
    }
    i = 0
    n = len(text)
    depth = 0

    while i < n:
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "'" and depth == 0:
            end = _skip_single_quoted(text, i)
            i = end
            continue
        elif depth == 0 and ch.isspace():
            # Check if the next word is an end keyword
            rest = text[i:].lstrip()
            for kw in end_keywords:
                if rest.upper().startswith(kw) and (
                    len(rest) == len(kw) or not rest[len(kw)].isalnum()
                ):
                    return text[:i].strip()
        i += 1

    return text.strip()


def _parse_create_table(source):
    """Parse CREATE TABLE statements from SQL source.

    Returns a list of dicts: {name, schema, columns} where columns is a
    list of {name, type, nullable, default, constraints, description}.
    """
    tables = []
    # Work on comment-stripped source for structure parsing
    clean = _strip_sql_comments(source)

    for m in _CREATE_TABLE_RE.finditer(clean):
        schema = m.group(1) or ""
        table_name = m.group(2)

        # Find the matching closing paren for the column definitions
        paren_start = m.end() - 1  # the opening (
        depth = 0
        end = paren_start
        for idx in range(paren_start, len(clean)):
            if clean[idx] == "(":
                depth += 1
            elif clean[idx] == ")":
                depth -= 1
                if depth == 0:
                    end = idx
                    break

        columns_text = clean[paren_start + 1 : end]
        col_defs = _split_column_defs(columns_text)

        columns = []
        for col_text in col_defs:
            col = _parse_column_def(col_text)
            if col is not None:
                columns.append(col)

        tables.append({
            "name": table_name,
            "schema": schema,
            "columns": columns,
        })

    return tables


# ---------------------------------------------------------------------------
# Parsing: CREATE VIEW
# ---------------------------------------------------------------------------

_CREATE_VIEW_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+"
    r"(?:(\w+)\.)?(\w+)\s+AS\b",
    re.IGNORECASE,
)


def _parse_create_view(source):
    """Parse CREATE VIEW statements from SQL source.

    Returns a list of dicts: {name, schema}.
    """
    clean = _strip_sql_comments(source)
    views = []
    for m in _CREATE_VIEW_RE.finditer(clean):
        views.append({
            "name": m.group(2),
            "schema": m.group(1) or "",
        })
    return views


# ---------------------------------------------------------------------------
# Parsing: CREATE TYPE
# ---------------------------------------------------------------------------

_CREATE_TYPE_ENUM_RE = re.compile(
    r"CREATE\s+TYPE\s+(?:(\w+)\.)?(\w+)\s+AS\s+ENUM\s*\(",
    re.IGNORECASE,
)

_CREATE_TYPE_COMPOSITE_RE = re.compile(
    r"CREATE\s+TYPE\s+(?:(\w+)\.)?(\w+)\s+AS\s*\(",
    re.IGNORECASE,
)


def _parse_create_type(source):
    """Parse CREATE TYPE statements from SQL source.

    Returns a list of dicts: {name, schema, kind, values, fields} where:
    - ENUM: kind="enum", values is list of enum value strings, fields is empty
    - Composite: kind="composite", fields is list of {name, type}, values is empty
    """
    clean = _strip_sql_comments(source)
    types = []
    seen = set()

    # Enums
    for m in _CREATE_TYPE_ENUM_RE.finditer(clean):
        schema = m.group(1) or ""
        type_name = m.group(2)
        key = (schema, type_name)
        if key in seen:
            continue
        seen.add(key)

        # Find the closing paren
        paren_start = m.end() - 1
        depth = 0
        end = paren_start
        for idx in range(paren_start, len(clean)):
            if clean[idx] == "(":
                depth += 1
            elif clean[idx] == ")":
                depth -= 1
                if depth == 0:
                    end = idx
                    break

        values_text = clean[paren_start + 1 : end]
        # Extract quoted values
        values = re.findall(r"'([^']*(?:''[^']*)*)'", values_text)
        # Unescape '' -> '
        values = [v.replace("''", "'") for v in values]

        types.append({
            "name": type_name,
            "schema": schema,
            "kind": "enum",
            "values": values,
            "fields": [],
        })

    # Composites (AS ( ... ) without ENUM keyword)
    for m in _CREATE_TYPE_COMPOSITE_RE.finditer(clean):
        schema = m.group(1) or ""
        type_name = m.group(2)
        key = (schema, type_name)
        if key in seen:
            continue
        seen.add(key)

        paren_start = m.end() - 1
        depth = 0
        end = paren_start
        for idx in range(paren_start, len(clean)):
            if clean[idx] == "(":
                depth += 1
            elif clean[idx] == ")":
                depth -= 1
                if depth == 0:
                    end = idx
                    break

        fields_text = clean[paren_start + 1 : end]
        fields = []
        for field_def in fields_text.split(","):
            field_def = field_def.strip()
            if not field_def:
                continue
            parts = field_def.split(None, 1)
            if len(parts) == 2:
                fields.append({"name": parts[0], "type": parts[1].rstrip(");").strip()})
            elif len(parts) == 1:
                fields.append({"name": parts[0], "type": ""})

        types.append({
            "name": type_name,
            "schema": schema,
            "kind": "composite",
            "values": [],
            "fields": fields,
        })

    return types


# ---------------------------------------------------------------------------
# Parsing: CREATE FUNCTION
# ---------------------------------------------------------------------------

_CREATE_FUNCTION_RE = re.compile(
    r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+"
    r"(?:(\w+)\.)?(\w+)\s*\(",
    re.IGNORECASE,
)


def _parse_create_function(source):
    """Parse CREATE FUNCTION statements from SQL source.

    Returns a list of dicts: {name, schema}.
    """
    clean = _strip_sql_comments(source)
    functions = []
    seen = set()
    for m in _CREATE_FUNCTION_RE.finditer(clean):
        schema = m.group(1) or ""
        func_name = m.group(2)
        key = (schema, func_name)
        if key not in seen:
            seen.add(key)
            functions.append({
                "name": func_name,
                "schema": schema,
            })
    return functions


# ---------------------------------------------------------------------------
# symbol_details for functions
# ---------------------------------------------------------------------------

# Mode keywords that can prefix a function parameter
_PARAM_MODE_RE = re.compile(r"^(INOUT|IN|OUT)\b", re.IGNORECASE)

# Keywords that terminate the RETURNS type clause
_RETURNS_END_RE = re.compile(
    r"\b(?:AS|LANGUAGE|BEGIN|IMMUTABLE|STABLE|VOLATILE|STRICT|"
    r"SECURITY|COST|ROWS|SET|CALLED|RETURNS|PARALLEL)\b",
    re.IGNORECASE,
)


def _function_symbol_details(clean_source, func_name, comments):
    """Build a symbol_details dict for a CREATE FUNCTION.

    Returns None if the function is not found in the source.
    """
    for m in _CREATE_FUNCTION_RE.finditer(clean_source):
        matched_name = m.group(2)
        if matched_name.lower() != func_name.lower():
            continue

        # Find the closing ) of the parameter list.
        # m.end() is right after the opening (.
        paren_start = m.end() - 1
        depth = 0
        close_paren = paren_start
        for idx in range(paren_start, len(clean_source)):
            if clean_source[idx] == "(":
                depth += 1
            elif clean_source[idx] == ")":
                depth -= 1
                if depth == 0:
                    close_paren = idx
                    break

        # Parse parameters
        params_text = clean_source[paren_start + 1 : close_paren]
        params = _parse_function_params(params_text)

        # Parse RETURNS clause
        after_params = clean_source[close_paren + 1 :]
        return_type = _parse_returns_clause(after_params)

        # Check COMMENT ON FUNCTION for return_documented
        return_documented = _has_function_comment(comments, func_name)

        return {
            "params": params,
            "return_type": return_type,
            "return_documented": return_documented,
        }

    return None


def _parse_function_params(params_text):
    """Parse a SQL function parameter list into a list of param dicts.

    Each dict has {name, type, documented}. documented is always False
    because SQL has no standard per-parameter documentation mechanism.
    """
    parts = _split_column_defs(params_text)
    params = []

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Strip optional IN/OUT/INOUT mode prefix
        mode_match = _PARAM_MODE_RE.match(part)
        if mode_match:
            part = part[mode_match.end():].strip()

        # Split into name and type
        tokens = part.split()
        if not tokens:
            continue

        param_name = tokens[0]

        # Everything after the name is the type, up to DEFAULT
        type_tokens = []
        i = 1
        while i < len(tokens):
            if tokens[i].upper() == "DEFAULT":
                break
            type_tokens.append(tokens[i])
            i += 1

        param_type = " ".join(type_tokens) if type_tokens else None

        params.append({
            "name": param_name,
            "type": param_type,
            "documented": False,
        })

    return params


def _parse_returns_clause(after_params):
    """Extract the return type from text following the closing ) of params.

    Looks for RETURNS <type> and stops at the next SQL keyword (AS, LANGUAGE,
    BEGIN, etc.) or at $$ delimiter.
    """
    # Find RETURNS keyword
    returns_match = re.search(r"\bRETURNS\s+", after_params, re.IGNORECASE)
    if not returns_match:
        return None

    rest = after_params[returns_match.end():]

    # Collect the type until we hit a terminator keyword or $$
    type_tokens = []
    i = 0
    n = len(rest)

    while i < n:
        # Skip whitespace
        while i < n and rest[i].isspace():
            i += 1
        if i >= n:
            break

        # Check for $$ (dollar-quote start)
        if rest[i] == "$":
            break

        # Check for semicolon
        if rest[i] == ";":
            break

        # Read a word
        word_start = i
        while i < n and not rest[i].isspace() and rest[i] not in "$;":
            i += 1
        word = rest[word_start:i]

        if not word:
            break

        # Check if this word is a terminator keyword
        if _RETURNS_END_RE.fullmatch(word):
            break

        type_tokens.append(word)

    return " ".join(type_tokens) if type_tokens else None


def _has_function_comment(comments, func_name):
    """Check if there is a COMMENT ON FUNCTION for the given function name.

    Tries both unqualified and all schema-qualified variants.
    """
    for (obj_type, obj_name), _ in comments.items():
        if obj_type != "function":
            continue
        # obj_name could be "func_name" or "schema.func_name"
        bare_name = obj_name.split(".")[-1] if "." in obj_name else obj_name
        if bare_name.lower() == func_name.lower():
            return True
    return False


# ---------------------------------------------------------------------------
# Parsing: COMMENT ON
# ---------------------------------------------------------------------------


def _parse_comments(source):
    """Parse COMMENT ON statements from SQL source.

    Returns a dict mapping (object_type, qualified_name) to comment text.
    object_type is lowercase: "table", "column", "view", "type", "function".
    qualified_name preserves schema qualification if present.

    Handles single-quoted strings with '' escape, dollar-quoting,
    and IS NULL (which removes a comment -- skipped here).
    """
    comments = {}

    # Normalize line endings and work on the raw source (comments in SQL
    # comments are irrelevant, but COMMENT ON statements are real SQL)
    clean = _strip_sql_comments(source)

    # Match COMMENT ON <object_type> <name> IS <value>
    # We need a flexible pattern because names can be schema-qualified and
    # the value can be a multi-line string.
    comment_re = re.compile(
        r"\bCOMMENT\s+ON\s+"
        r"(TABLE|COLUMN|VIEW|TYPE|FUNCTION|INDEX|SCHEMA|SEQUENCE)\s+"
        r"([\w.]+)\s+"
        r"IS\s+",
        re.IGNORECASE,
    )

    for m in comment_re.finditer(clean):
        obj_type = m.group(1).lower()
        obj_name = m.group(2)
        rest = clean[m.end():]

        # Check for IS NULL (remove comment)
        if rest.lstrip().upper().startswith("NULL"):
            continue

        # Extract the string value
        text = _extract_comment_string(rest)
        if text is None:
            continue

        comments[(obj_type, obj_name)] = text

    return comments


def _extract_comment_string(text):
    """Extract a SQL string literal from the beginning of text.

    Supports single-quoted strings (with '' escape) and dollar-quoting.
    Returns the string content (unescaped) or None if no valid string found.
    """
    text = text.lstrip()

    # Single-quoted string
    if text.startswith("'"):
        parts = []
        i = 1
        n = len(text)
        while i < n:
            if text[i] == "'":
                if i + 1 < n and text[i + 1] == "'":
                    parts.append("'")
                    i += 2
                else:
                    return "".join(parts)
            else:
                parts.append(text[i])
                i += 1
        return None  # unterminated

    # Dollar-quoted string
    dollar_match = re.match(r"\$(\w*)\$", text)
    if dollar_match:
        tag = dollar_match.group(0)
        start = len(tag)
        end_pos = text.find(tag, start)
        if end_pos >= 0:
            return text[start:end_pos]
        return None  # unterminated

    return None


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _handle_ref(path, target, body, source_paths, base_dir, attrs):
    """List all CREATE objects with their COMMENT ON descriptions, grouped by type.

    path is a file path to a .sql file.
    """
    if not path:
        return format_error(":::ref requires a file path argument")

    resolved = _resolve_sql_path(path, source_paths, base_dir)
    if resolved is None:
        return format_error(f"'{path}' not found")

    source, err = read_source(resolved)
    if err:
        return format_error(f"cannot read '{path}': {err}")

    tables = _parse_create_table(source)
    views = _parse_create_view(source)
    types = _parse_create_type(source)
    functions = _parse_create_function(source)

    if not tables and not views and not types and not functions:
        return format_error(f"no CREATE objects found in '{path}'")

    comments = _parse_comments(source)

    if target:
        # Search all object types for the target
        for t in tables:
            if t["name"] == target:
                desc = _lookup_comment(comments, "table", t["name"], t["schema"])
                if desc:
                    return f"### {t['name']}\n\n{desc}"
                return f"### {t['name']}"
        for v in views:
            if v["name"] == target:
                desc = _lookup_comment(comments, "view", v["name"], v["schema"])
                if desc:
                    return f"### {v['name']}\n\n{desc}"
                return f"### {v['name']}"
        for t in types:
            if t["name"] == target:
                desc = _lookup_comment(comments, "type", t["name"], t["schema"])
                if t["kind"] == "enum":
                    vals = ", ".join(t["values"])
                    label = f"ENUM: {vals}"
                else:
                    fields_str = ", ".join(
                        f"{f['name']} {f['type']}" for f in t["fields"]
                    )
                    label = f"COMPOSITE: {fields_str}"
                parts_t = [f"### {t['name']}", "", label]
                if desc:
                    parts_t.append("")
                    parts_t.append(desc)
                return "\n".join(parts_t)
        for f in functions:
            if f["name"] == target:
                desc = _lookup_comment(comments, "function", f["name"], f["schema"])
                if desc:
                    return f"### {f['name']}\n\n{desc}"
                return f"### {f['name']}"
        return format_error(f"symbol '{target}' not found in '{path}'")

    parts = []
    parts.append(f"## {os.path.basename(resolved)}")

    # Tables
    if tables:
        parts.append("")
        parts.append("### Tables")
        parts.append("")
        for t in tables:
            desc = _lookup_comment(comments, "table", t["name"], t["schema"])
            if desc:
                parts.append(f"- **{t['name']}** -- {desc}")
            else:
                parts.append(f"- **{t['name']}**")

    # Views
    if views:
        parts.append("")
        parts.append("### Views")
        parts.append("")
        for v in views:
            desc = _lookup_comment(comments, "view", v["name"], v["schema"])
            if desc:
                parts.append(f"- **{v['name']}** -- {desc}")
            else:
                parts.append(f"- **{v['name']}**")

    # Types
    if types:
        parts.append("")
        parts.append("### Types")
        parts.append("")
        for t in types:
            desc = _lookup_comment(comments, "type", t["name"], t["schema"])
            if t["kind"] == "enum":
                vals = ", ".join(t["values"])
                label = f"ENUM: {vals}"
            else:
                fields_str = ", ".join(
                    f"{f['name']} {f['type']}" for f in t["fields"]
                )
                label = f"COMPOSITE: {fields_str}"
            if desc:
                parts.append(f"- **{t['name']}** -- {label} -- {desc}")
            else:
                parts.append(f"- **{t['name']}** -- {label}")

    # Functions
    if functions:
        parts.append("")
        parts.append("### Functions")
        parts.append("")
        for f in functions:
            desc = _lookup_comment(comments, "function", f["name"], f["schema"])
            if desc:
                parts.append(f"- **{f['name']}** -- {desc}")
            else:
                parts.append(f"- **{f['name']}**")

    return "\n".join(parts)


def _lookup_comment(comments, obj_type, name, schema):
    """Look up a COMMENT ON value, trying both qualified and unqualified names."""
    if schema:
        qualified = f"{schema}.{name}"
        val = comments.get((obj_type, qualified))
        if val:
            return val
    return comments.get((obj_type, name))


def _handle_prose_desc(path, target, body, source_paths, base_dir, attrs):
    """Return the COMMENT ON TABLE text for the targeted table.

    path is the file path, target is the table name.
    """
    if not path:
        return format_error(":::prose-desc requires a file path argument")

    if not target:
        return format_error(
            "prose-desc requires a target table name for SQL files"
        )

    resolved = _resolve_sql_path(path, source_paths, base_dir)
    if resolved is None:
        return format_error(f"'{path}' not found")

    source, err = read_source(resolved)
    if err:
        return format_error(f"cannot read '{path}': {err}")

    comments = _parse_comments(source)

    # Try exact match, then with all schemas
    for key, text in comments.items():
        obj_type, obj_name = key
        if obj_type == "table":
            # Match unqualified or the name part of schema.name
            bare_name = obj_name.split(".")[-1] if "." in obj_name else obj_name
            if bare_name == target or obj_name == target:
                return text

    return format_error(f"no comment found for table '{target}'")


def _handle_table_schema(path, target, body, source_paths, base_dir, attrs):
    """Present columns of the targeted table as a markdown table.

    path is the file path, target is the table name (or None).
    If no table name and only one table, use it.
    If no table name and multiple tables, show all with ### headings.
    """
    if not path:
        return format_error(":::table-schema requires a file path argument")

    # JSON/TOML files are config files -- delegate
    if path.endswith((".json", ".toml")):
        return handle_table_config(path, None, body, source_paths, base_dir, attrs)

    resolved = _resolve_sql_path(path, source_paths, base_dir)
    if resolved is None:
        return format_error(f"'{path}' not found")

    source, err = read_source(resolved)
    if err:
        return format_error(f"cannot read '{path}': {err}")

    tables = _parse_create_table(source)
    if not tables:
        return format_error(f"no tables found in '{path}'")

    comments = _parse_comments(source)

    # Apply column comments to tables
    for t in tables:
        for col in t["columns"]:
            desc = _lookup_column_comment(
                comments, t["name"], col["name"], t["schema"]
            )
            if desc:
                col["description"] = desc

    if target:
        matched = next((t for t in tables if t["name"] == target), None)
        if matched is None:
            return format_error(
                f"table '{target}' not found in '{path}'"
            )
        return _format_table_schema(matched)

    # No table name specified
    if len(tables) == 1:
        return _format_table_schema(tables[0])

    # Multiple tables -- show all
    results = []
    for t in tables:
        results.append(f"### {t['name']}")
        results.append("")
        results.append(_format_table_schema(t))
    return "\n".join(results)


def _lookup_column_comment(comments, table_name, col_name, schema):
    """Look up a COMMENT ON COLUMN value."""
    # Try schema.table.column
    if schema:
        val = comments.get(("column", f"{schema}.{table_name}.{col_name}"))
        if val:
            return val
    # Try table.column
    return comments.get(("column", f"{table_name}.{col_name}"))


def _format_table_schema(table_info):
    """Format a table's columns as a markdown table."""
    rows = []
    for col in table_info["columns"]:
        nullable_display = "NOT NULL" if not col["nullable"] else ""
        default_display = col["default"] if col["default"] else ""
        rows.append([
            f"`{col['name']}`",
            f"`{col['type']}`",
            nullable_display,
            default_display,
            col["description"],
        ])
    return render_markdown_table(
        ["Column", "Type", "Nullable", "Default", "Description"], rows
    )


SqlExtractor._HANDLERS = {
    "ref": _handle_ref,
    "prose-desc": _handle_prose_desc,
    "table-schema": _handle_table_schema,
    "table-config": handle_table_config,
}

# Generic markdown table renderer

## Problem

Selfdoc has ~10 places that build markdown tables inline using the same pattern:

```python
rows = []
rows.append("| Header1 | Header2 |")
rows.append("| --- | --- |")
rows.append(f"| {val1} | {val2} |")
return "\n".join(rows)
```

This is duplicated across:
- `content.py`: table-dep, table-commands, table-directives, table-config-schema, table-endpoint
- `extractors/go.py`: struct field tables, config tables
- `extractors/typescript.py`: interface/type tables, config tables
- `extractors/python.py`: dataclass field tables, class field tables
- `extractors/zig.py`: struct field tables

The config table helpers in `extractors/base.py` (`_config_from_json`, `_config_from_toml`) are the closest to shared infrastructure, but they're config-specific, not generic.

## Proposal

Add a generic `render_markdown_table(headers: list[str], rows: list[list[str]]) -> str` function that handles:
- Header row with pipe delimiters
- Separator row
- Data rows with proper escaping (pipes in cell content)
- Consistent formatting

Location: `selfdoc/markdown.py` or added to an existing utils module.

## Motivation

- DRY: eliminates duplicated table-building boilerplate across the codebase
- Custom directives in consumer projects (e.g., rlsbl) need to build markdown tables and currently have to roll their own renderer or duplicate the pattern
- Having a shared utility in selfdoc means any project using selfdoc directives can import it

## Scope

- Add the utility function
- Optionally refactor existing table-building code to use it (can be incremental)

# Changelog auto-generation

## Problem

There is no mechanism to auto-generate a changelog page from CHANGELOG.md or git history. Users who maintain a CHANGELOG.md in their project root have no way to include it in the generated documentation site without manually copying content into a `docs/changelog.md` file.

## Proposed solution

Add a `changelog` config option that points to a CHANGELOG.md file:

```json
{
  "changelog": "CHANGELOG.md"
}
```

During build:

1. Read the specified file.
2. Convert it to HTML using `md_to_html`.
3. Generate a `changelog.html` page using the standard page template.
4. Add it to the sidebar navigation (at the bottom, outside any group).

If the file does not exist, skip silently (no error).

## Affected files

- `selfdoc/build.py` — read changelog, generate page
- `selfdoc/config.py` — `changelog` config key
- `selfdoc/html.py` — integrate into nav generation

## Effort

Low-medium. Straightforward file read and template rendering.

---
title: Code Blocks
description: "Syntax highlighting, language icons, line numbers, run buttons, annotations, diff highlighting, code tabs, and copy buttons in selfdoc code blocks."
nav_group: "Guides"
nav_order: 8
---

# Code Blocks

Fenced code blocks in selfdoc get automatic syntax highlighting, language labels, and a copy button. Beyond the basics, you can enable line numbers, interactive run buttons, inline annotations, diff highlighting, and automatic language tabs.

## Syntax Highlighting

selfdoc uses Pygments for build-time syntax highlighting. Just specify the language after the opening fence:

````markdown
```python
def greet(name: str) -> str:
    return f"Hello, {name}!"
```
````

Pygments supports hundreds of languages out of the box. If the language is not recognized, the code renders as plain text. Light and dark mode get separate Pygments styles (default/monokai) that switch automatically with the theme.

> [!NOTE]
> Pygments is an optional dependency. If it is not installed, code blocks render without highlighting. Install it with `pip install pygments` or `uv add pygments`.

## Language Icons

Each code block with a language label gets a small icon next to the language name. Control the style with `code_icons` in your config:

```json
{
  "code_icons": "colorful"
}
```

| Value | Description |
| ----- | ----------- |
| `colorful` (default) | Full-color SVG icons for recognized languages |
| `monochrome` | Single-color icons that match the theme |
| `none` | No icons, just the language text label |

## Line Numbers

Enable line numbers globally with `line_numbers` in your config:

```json
{
  "line_numbers": true
}
```

Line numbers appear in the gutter via CSS counters, so they are not selectable when copying code. You can also enable line numbers per block using the `line_numbers` annotation in your fence:

````markdown
```python line_numbers
def example():
    pass
```
````

Per-block annotations can also set the starting line number with `line_start`:

````markdown
```python line_numbers line_start=42
    # This line is numbered 42
    return result
```
````

## Run Buttons

Enable interactive run buttons with `run_button` in your config:

```json
{
  "run_button": true
}
```

When enabled, code blocks get a "Run" button that opens the code in an appropriate online playground. You can also enable run buttons per block with the `run` annotation:

````markdown
```python run
print("Hello, world!")
```
````

## Annotations

Inline annotations turn comments like `// [1]` or `# [1]` into clickable badges that reveal explanatory text. Add annotation definitions after the closing fence:

````markdown
```python
config = load_config()  # [1]
result = build(config)  # [2]
```
[1]: Reads selfdoc.json from the current directory
[2]: Resolves directives and writes HTML output
````

The numbered markers in the code become small badge elements. Click or focus a badge to see the annotation text. This is useful for walking through code step by step without cluttering the code itself with long comments.

## Diff Highlighting

Use the `diff` language to get line-level add/remove coloring:

````markdown
```diff
-old_function()
+new_function(with_args=True)
 unchanged_line()
```
````

Lines starting with `+` are highlighted green, lines starting with `-` are highlighted red, and lines starting with a space are neutral. selfdoc also auto-detects diff-style content in any code block where lines start with `+` or `-`.

## Code Tabs

When you place two or more fenced code blocks with different languages next to each other (no content between them), selfdoc automatically groups them into a tabbed interface:

````markdown
```python
pip install selfdoc
```

```bash
npm install -g selfdoc
```
````

This renders as a single code block with "python" and "bash" tabs. The user clicks a tab to see that version. Only blocks with language labels participate in tab grouping -- unlabeled blocks are left standalone.

> [!TIP]
> Code tabs are great for showing the same concept in multiple languages, or alternative installation methods. Put the most common option first.

## Copy Button

Every code block gets a copy-to-clipboard button automatically. No config needed. It appears in the top-right corner of the block on hover and copies the raw code content (without line numbers or annotations).

Next: [Custom Directives](custom-directives/) -->

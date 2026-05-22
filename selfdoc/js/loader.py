"""Loader for selfdoc JS files using importlib.resources."""

import importlib.resources


def load_js(name: str) -> str:
    """Load a .js file from the selfdoc.js package.

    Args:
        name: Filename without extension (e.g. "theme-toggle").

    Returns:
        The JavaScript source as a string.
    """
    ref = importlib.resources.files("selfdoc.js").joinpath(f"{name}.js")
    return ref.read_text(encoding="utf-8")


def load_search_js(engine: str = "builtin") -> str:
    """Compose search JS from engine implementation + dialog UI.

    The engine must be one of "builtin", "fuse", or "minisearch".
    Falls back to "builtin" if the engine name is unrecognized.

    Returns:
        Combined JS string (engine + dialog).
    """
    valid_engines = {"builtin", "fuse", "minisearch"}
    if engine not in valid_engines:
        engine = "builtin"
    engine_js = load_js(f"search-{engine}")
    dialog_js = load_js("search-dialog")
    return engine_js + "\n" + dialog_js


def assemble_body_js(body_html: str, toc_html: str, footer_html: str,
                     search_engine: str | None = None) -> str:
    """Assemble the body JS blocks based on page content.

    Always includes: theme-toggle, sidebar, nav-groups,
    scroll-affordance, reading-progress. Conditionally includes
    blocks based on what HTML content is present on the page.
    Smooth-scroll restore is always appended last.

    Args:
        body_html: The article body HTML.
        toc_html: The table-of-contents HTML (empty string if none).
        footer_html: The page footer HTML.
        search_engine: Search engine name (unused here, kept for API).

    Returns:
        Concatenated JS string (not yet minified).
    """
    # Always-needed blocks
    js_blocks = [
        load_js("theme-toggle"),
        load_js("sidebar"),
        load_js("nav-groups"),
        load_js("scroll-affordance"),
        load_js("reading-progress"),
        load_js("pickers"),
    ]

    # Conditional blocks
    if "<pre" in body_html:
        js_blocks.append(load_js("copy-button"))
    if toc_html:
        js_blocks.append(load_js("scrollspy"))
    if 'class="feedback"' in footer_html:
        js_blocks.append(load_js("feedback"))
    if 'class="code-tabs"' in body_html:
        js_blocks.append(load_js("code-tabs"))
    if 'data-run="true"' in body_html:
        js_blocks.append(load_js("run-button"))
    if 'class="heading-link"' in body_html:
        js_blocks.append(load_js("heading-copy"))
    if 'class="table-wrap"' in body_html:
        js_blocks.append(load_js("sortable-tables"))

    # Always last: re-enable smooth scroll
    js_blocks.append(load_js("smooth-scroll"))

    return "\n".join(js_blocks)

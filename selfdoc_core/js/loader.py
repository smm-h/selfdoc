"""Loader for selfdoc_core JS files using importlib.resources."""

import importlib.resources


def load_js(name: str) -> str:
    """Load a .js file from the selfdoc_core.js package.

    Args:
        name: Filename without extension (e.g. "theme-toggle").

    Returns:
        The JavaScript source as a string.
    """
    ref = importlib.resources.files("selfdoc_core.js").joinpath(f"{name}.js")
    return ref.read_text(encoding="utf-8")


def assemble_body_js(body_html: str, toc_html: str, footer_html: str,
                     extras_html: str = "") -> str:
    """Assemble the body JS blocks based on page content.

    Always includes: theme-toggle, sidebar, nav-groups,
    scroll-affordance, reading-progress. Conditionally includes
    blocks based on what HTML content is present on the page.
    Smooth-scroll restore is always appended last.

    Args:
        body_html: The article body HTML.
        toc_html: The table-of-contents HTML (empty string if none).
        footer_html: The page footer HTML.
        extras_html: Template-level HTML the article body does not carry --
            the superseded-version notice and the share control, which the
            page wrapper renders around the body.

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
    if 'class="version-notice"' in extras_html:
        js_blocks.append(load_js("version-notice"))
    if 'class="share-address"' in extras_html:
        js_blocks.append(load_js("share-address"))

    # Always last: re-enable smooth scroll
    js_blocks.append(load_js("smooth-scroll"))

    return "\n".join(js_blocks)

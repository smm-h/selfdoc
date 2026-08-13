"""Playwright-based tests for the demo page's design settings panel."""

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

# The browser itself comes from conftest's session-scoped
# ``chromium_browser``: one launcher per suite, because Playwright's sync
# API refuses a second one while the first is open.

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _find_free_port():
    """Find a free TCP port by binding to port 0."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def http_server():
    """Start a Python HTTP server on a random port, yield the port, then kill it."""
    port = _find_free_port()
    # Serve from the project root so that both demo/ and selfdoc/ are accessible
    root = DEMO_DIR.parent
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=str(root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait until the server is accepting connections
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        raise RuntimeError(f"HTTP server on port {port} did not start in time")
    yield port
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="session")
def browser_context(chromium_browser):
    """Create a single browser context shared across all tests."""
    ctx = chromium_browser.new_context()
    # Grant clipboard permissions for the export test
    ctx.grant_permissions(["clipboard-read", "clipboard-write"])
    yield ctx
    ctx.close()


@pytest.fixture()
def page(browser_context, http_server):
    """Create a fresh page within the shared context for each test."""
    pg = browser_context.new_page()
    pg.goto(f"http://127.0.0.1:{http_server}/demo/index.html")
    pg.wait_for_load_state("domcontentloaded")
    # Clear localStorage to prevent state leakage between tests
    pg.evaluate("localStorage.clear()")
    yield pg
    pg.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def open_panel(page):
    page.click("#settings-toggle")
    page.wait_for_selector("#ds-panel.open")


def close_panel(page):
    page.click("#ds-close")
    page.wait_for_selector("#ds-panel:not(.open)")


def click_knob_option(page, knob_name, value):
    """Click an option button inside a knob."""
    selector = f'.ds-knob[data-knob="{knob_name}"] .ds-opt[data-value="{value}"]'
    page.click(selector)


# ---------------------------------------------------------------------------
# 0.1 -- Page loads without JS errors
# ---------------------------------------------------------------------------


def test_page_loads_without_js_errors(chromium_browser, http_server):
    ctx = chromium_browser.new_context()
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda exc: errors.append(str(exc)))
    pg.goto(f"http://127.0.0.1:{http_server}/demo/index.html")
    pg.wait_for_load_state("domcontentloaded")
    pg.close()
    ctx.close()
    assert errors == [], f"Page produced JS errors: {errors}"


# ---------------------------------------------------------------------------
# 0.2 -- Each knob works
# ---------------------------------------------------------------------------

# Knob definitions: (knob_name, [(value, verification_js, expected), ...])
# The verification_js is a JS expression evaluated in page context.
# 'expected' is the value we compare with; if it is a callable tag we handle
# it specially below.

_KNOB_CASES = [
    # sidebar-width
    (
        "sidebar-width",
        [
            (
                "200px",
                "getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width').trim()",
                "200px",
            ),
            (
                "220px",
                "getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width').trim()",
                "220px",
            ),
            (
                "240px",
                "getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width').trim()",
                "240px",
            ),
        ],
    ),
    # toc-width
    (
        "toc-width",
        [
            (
                "180px",
                "getComputedStyle(document.documentElement).getPropertyValue('--toc-width').trim()",
                "180px",
            ),
            (
                "200px",
                "getComputedStyle(document.documentElement).getPropertyValue('--toc-width').trim()",
                "200px",
            ),
            (
                "220px",
                "getComputedStyle(document.documentElement).getPropertyValue('--toc-width').trim()",
                "220px",
            ),
            (
                "hidden",
                "document.body.getAttribute('data-toc')",
                "hidden",
            ),
        ],
    ),
    # content-width
    (
        "content-width",
        [
            (
                "60ch",
                "getComputedStyle(document.documentElement).getPropertyValue('--content-max-width').trim()",
                "60ch",
            ),
            (
                "72ch",
                "getComputedStyle(document.documentElement).getPropertyValue('--content-max-width').trim()",
                "72ch",
            ),
            (
                "90ch",
                "getComputedStyle(document.documentElement).getPropertyValue('--content-max-width').trim()",
                "90ch",
            ),
            (
                "full",
                "getComputedStyle(document.documentElement).getPropertyValue('--content-max-width').trim()",
                "none",
            ),
        ],
    ),
    # font-kind
    (
        "font-kind",
        [
            (
                "system",
                "getComputedStyle(document.documentElement).getPropertyValue('--font-body').trim()",
                "-apple-system",  # contains check
            ),
            (
                "inter",
                "getComputedStyle(document.documentElement).getPropertyValue('--font-body').trim()",
                "Inter",
            ),
            (
                "source-sans",
                "getComputedStyle(document.documentElement).getPropertyValue('--font-body').trim()",
                "Source Sans 3",
            ),
            (
                "dm-sans",
                "getComputedStyle(document.documentElement).getPropertyValue('--font-body').trim()",
                "DM Sans",
            ),
            (
                "ibm-plex",
                "getComputedStyle(document.documentElement).getPropertyValue('--font-body').trim()",
                "IBM Plex Sans",
            ),
        ],
    ),
    # font-size
    (
        "font-size",
        [
            ("14px", "document.documentElement.style.fontSize", "14px"),
            ("16px", "document.documentElement.style.fontSize", "16px"),
            ("18px", "document.documentElement.style.fontSize", "18px"),
            ("20px", "document.documentElement.style.fontSize", "20px"),
        ],
    ),
    # density
    (
        "density",
        [
            (
                "compact",
                "getComputedStyle(document.documentElement).getPropertyValue('--spacing-scale').trim()",
                "0.8",
            ),
            (
                "normal",
                "getComputedStyle(document.documentElement).getPropertyValue('--spacing-scale').trim()",
                "1",
            ),
            (
                "relaxed",
                "getComputedStyle(document.documentElement).getPropertyValue('--spacing-scale').trim()",
                "1.2",
            ),
        ],
    ),
    # light-dark
    (
        "light-dark",
        [
            (
                "light",
                "document.documentElement.getAttribute('data-theme')",
                "light",
            ),
            (
                "dark",
                "document.documentElement.getAttribute('data-theme')",
                "dark",
            ),
            (
                "system",
                "document.documentElement.getAttribute('data-theme')",
                None,
            ),
        ],
    ),
    # accent-color
    (
        "accent-color",
        [
            (
                "blue",
                "getComputedStyle(document.documentElement).getPropertyValue('--link').trim()",
                "#0969da",
            ),
            (
                "green",
                "getComputedStyle(document.documentElement).getPropertyValue('--link').trim()",
                "#1a7f37",
            ),
            (
                "purple",
                "getComputedStyle(document.documentElement).getPropertyValue('--link').trim()",
                "#8250df",
            ),
            (
                "orange",
                "getComputedStyle(document.documentElement).getPropertyValue('--link').trim()",
                "#bf6a02",
            ),
            (
                "red",
                "getComputedStyle(document.documentElement).getPropertyValue('--link').trim()",
                "#cf222e",
            ),
        ],
    ),
    # topbar-color
    (
        "topbar-color",
        [
            (
                "dark",
                "!document.body.classList.contains('topbar-light') && !document.body.classList.contains('topbar-accent')",
                True,
            ),
            (
                "light",
                "document.body.classList.contains('topbar-light')",
                True,
            ),
            (
                "accent",
                "document.body.classList.contains('topbar-accent')",
                True,
            ),
        ],
    ),
    # gradient-strip
    (
        "gradient-strip",
        [
            (
                "show",
                "!document.body.classList.contains('gradient-hidden') && !document.body.classList.contains('gradient-solid')",
                True,
            ),
            (
                "hide",
                "document.body.classList.contains('gradient-hidden')",
                True,
            ),
            (
                "solid",
                "document.body.classList.contains('gradient-solid')",
                True,
            ),
        ],
    ),
    # border-radius
    (
        "border-radius",
        [
            (
                "0",
                "getComputedStyle(document.documentElement).getPropertyValue('--radius').trim()",
                "0",
            ),
            (
                "4px",
                "getComputedStyle(document.documentElement).getPropertyValue('--radius').trim()",
                "4px",
            ),
            (
                "8px",
                "getComputedStyle(document.documentElement).getPropertyValue('--radius').trim()",
                "8px",
            ),
            (
                "16px",
                "getComputedStyle(document.documentElement).getPropertyValue('--radius').trim()",
                "16px",
            ),
        ],
    ),
    # code-block-style
    (
        "code-block-style",
        [
            (
                "bordered",
                "document.body.getAttribute('data-code-style')",
                "bordered",
            ),
            ("plain", "document.body.getAttribute('data-code-style')", "plain"),
            (
                "filled",
                "document.body.getAttribute('data-code-style')",
                "filled",
            ),
            (
                "floating",
                "document.body.getAttribute('data-code-style')",
                "floating",
            ),
        ],
    ),
]


def _make_knob_ids():
    """Generate test IDs for parametrize."""
    ids = []
    for knob_name, options in _KNOB_CASES:
        for value, _js, _expected in options:
            ids.append(f"{knob_name}={value}")
    return ids


def _flatten_knob_cases():
    """Flatten nested knob cases for parametrize."""
    cases = []
    for knob_name, options in _KNOB_CASES:
        for value, js_expr, expected in options:
            cases.append((knob_name, value, js_expr, expected))
    return cases


@pytest.mark.parametrize(
    "knob_name,value,js_expr,expected",
    _flatten_knob_cases(),
    ids=_make_knob_ids(),
)
def test_knob(page, knob_name, value, js_expr, expected):
    """Click a knob option and verify its effect on the DOM/CSS."""
    open_panel(page)
    click_knob_option(page, knob_name, value)

    result = page.evaluate(js_expr)

    # font-kind uses a "contains" check because the value is a font stack
    if knob_name == "font-kind":
        assert expected in result, (
            f"Knob {knob_name}={value}: expected '{expected}' in '{result}'"
        )
    else:
        assert result == expected, (
            f"Knob {knob_name}={value}: expected {expected!r}, got {result!r}"
        )

    close_panel(page)


# ---------------------------------------------------------------------------
# 0.3 -- Panel open/close
# ---------------------------------------------------------------------------


def test_panel_opens_on_gear_click(page):
    page.click("#settings-toggle")
    panel = page.locator("#ds-panel")
    assert "open" in (panel.get_attribute("class") or "")


def test_panel_closes_on_escape(page):
    open_panel(page)
    page.keyboard.press("Escape")
    page.wait_for_selector("#ds-panel:not(.open)")
    panel = page.locator("#ds-panel")
    assert "open" not in (panel.get_attribute("class") or "")


def test_panel_closes_on_backdrop_click(page):
    open_panel(page)
    # Click the backdrop (covers the full viewport behind the panel)
    page.click("#ds-backdrop", position={"x": 10, "y": 10})
    page.wait_for_selector("#ds-panel:not(.open)")
    panel = page.locator("#ds-panel")
    assert "open" not in (panel.get_attribute("class") or "")


# ---------------------------------------------------------------------------
# 0.4 -- Export works
# ---------------------------------------------------------------------------


def test_export_produces_content(page):
    open_panel(page)

    # Change a knob from its default so the export has content
    click_knob_option(page, "border-radius", "16px")

    # Click export and wait for the button text to change (clipboard write is async)
    page.click("#ds-export")
    export_btn = page.locator("#ds-export")
    export_btn.wait_for(state="attached")
    # Wait until the button text starts with "Copied" (async clipboard write)
    page.wait_for_function(
        'document.getElementById("ds-export").textContent.startsWith("Copied")',
        timeout=5000,
    )
    btn_text = export_btn.text_content()
    assert btn_text.startswith("Copied") and "lines!" in btn_text

    # Verify the clipboard contains CSS with the override
    clipboard = page.evaluate("navigator.clipboard.readText()")
    assert "--radius: 16px" in clipboard, (
        f"Expected '--radius: 16px' in clipboard, got: {clipboard}"
    )

    close_panel(page)


# ---------------------------------------------------------------------------
# 0.5 -- Export contains CSS rules for all knobs (not just comments)
# ---------------------------------------------------------------------------

# Each entry: (knob_name, value_to_set, list_of_expected_css_fragments)
_EXPORT_KNOB_FRAGMENTS = [
    ("sidebar-width", "200px", ["--sidebar-width: 200px"]),
    ("toc-width", "hidden", [
        ".toc { display: none; }",
        "grid-template-columns: var(--sidebar-width, 240px) minmax(0, 1fr)",
    ]),
    ("toc-width", "220px", ["--toc-width: 220px"]),
    ("content-width", "90ch", ["--content-max-width: 90ch"]),
    ("font-kind", "source-sans", ['--font-body: "Source Sans 3", sans-serif']),
    ("font-size", "18px", ["font-size: 18px"]),
    ("density", "compact", [
        "--spacing-scale: 0.8",
        "--line-height-body: 1.4",
    ]),
    ("light-dark", "dark", [
        'Theme: dark. Set via <html data-theme="dark">',
    ]),
    ("accent-color", "green", [
        "--link: #1a7f37",
        '--link: #3fb950',
        '[data-theme="dark"]',
    ]),
    ("topbar-color", "light", [
        ".topbar {",
        "background: var(--bg)",
        "border-bottom: 1px solid var(--border)",
        "color: var(--text)",
    ]),
    ("topbar-color", "accent", [
        ".topbar { background: var(--link); }",
    ]),
    ("gradient-strip", "hide", [
        "body::before { display: none; }",
    ]),
    ("gradient-strip", "solid", [
        "body::before { background: var(--link); }",
    ]),
    ("border-radius", "8px", ["--radius: 8px"]),
    ("code-block-style", "plain", [
        ".code-block { border: none; background: transparent; }",
    ]),
    ("code-block-style", "filled", [
        ".code-block { border: none; background: var(--code-bg); }",
        ".code-block pre { background: transparent; }",
    ]),
    ("code-block-style", "floating", [
        "box-shadow: 0 2px 8px rgba(0,0,0,0.12)",
    ]),
]


def _make_export_ids():
    ids = []
    for knob_name, value, _frags in _EXPORT_KNOB_FRAGMENTS:
        ids.append(f"export-{knob_name}={value}")
    return ids


@pytest.mark.parametrize(
    "knob_name,value,expected_fragments",
    _EXPORT_KNOB_FRAGMENTS,
    ids=_make_export_ids(),
)
def test_export_contains_knob_css(page, knob_name, value, expected_fragments):
    """Change a knob to a non-default value, export, and verify CSS fragments."""
    open_panel(page)
    click_knob_option(page, knob_name, value)
    page.click("#ds-export")
    page.wait_for_function(
        'document.getElementById("ds-export").textContent.startsWith("Copied")',
        timeout=5000,
    )
    clipboard = page.evaluate("navigator.clipboard.readText()")
    for frag in expected_fragments:
        assert frag in clipboard, (
            f"Knob {knob_name}={value}: expected '{frag}' in export.\n"
            f"Got:\n{clipboard}"
        )
    close_panel(page)


# ---------------------------------------------------------------------------
# 0.6 -- Reset restores defaults
# ---------------------------------------------------------------------------


def test_reset_restores_defaults(page):
    """Change 3 knobs, click reset, verify all returned to defaults."""
    open_panel(page)

    # Change 3 knobs away from defaults
    click_knob_option(page, "border-radius", "16px")
    click_knob_option(page, "font-size", "20px")
    click_knob_option(page, "density", "compact")

    # Verify they changed
    assert page.evaluate(
        "getComputedStyle(document.documentElement).getPropertyValue('--radius').trim()"
    ) == "16px"
    assert page.evaluate("document.documentElement.style.fontSize") == "20px"
    assert page.evaluate(
        "getComputedStyle(document.documentElement).getPropertyValue('--spacing-scale').trim()"
    ) == "0.8"

    # Click reset
    page.click("#ds-reset")

    # Verify defaults restored
    assert page.evaluate(
        "getComputedStyle(document.documentElement).getPropertyValue('--radius').trim()"
    ) == "4px"
    assert page.evaluate("document.documentElement.style.fontSize") == "16px"
    assert page.evaluate(
        "getComputedStyle(document.documentElement).getPropertyValue('--spacing-scale').trim()"
    ) == "1"

    close_panel(page)


# ---------------------------------------------------------------------------
# 0.7 -- Modified indicator
# ---------------------------------------------------------------------------


def test_modified_indicator_appears(page):
    """Change one knob, verify indicator has class 'visible'."""
    open_panel(page)
    click_knob_option(page, "border-radius", "16px")
    indicator = page.locator("#ds-indicator")
    assert "visible" in (indicator.get_attribute("class") or "")
    close_panel(page)


def test_modified_indicator_disappears_on_reset(page):
    """Change a knob, click reset, verify indicator loses 'visible'."""
    open_panel(page)
    click_knob_option(page, "border-radius", "16px")
    indicator = page.locator("#ds-indicator")
    assert "visible" in (indicator.get_attribute("class") or "")

    page.click("#ds-reset")
    assert "visible" not in (indicator.get_attribute("class") or "")
    close_panel(page)


# ---------------------------------------------------------------------------
# 0.8 -- Live CSS preview
# ---------------------------------------------------------------------------


def test_live_preview_updates(page):
    """Change a knob, open the preview details, verify preview contains expected CSS."""
    open_panel(page)

    # Change a knob
    click_knob_option(page, "border-radius", "16px")

    # Open the details element
    page.click("#ds-preview summary")

    # Verify preview code contains the expected CSS
    preview_text = page.locator("#ds-preview-code").text_content()
    assert "--radius: 16px" in preview_text, (
        f"Expected '--radius: 16px' in preview, got: {preview_text}"
    )

    close_panel(page)


# ---------------------------------------------------------------------------
# 6.1 -- URL hash encodes on knob change
# ---------------------------------------------------------------------------


def test_url_hash_encodes_on_knob_change(page):
    """Change a knob, verify the URL hash contains the knob name and value."""
    open_panel(page)
    click_knob_option(page, "border-radius", "16px")

    url = page.url
    assert "#" in url, f"Expected hash in URL, got: {url}"
    assert "border-radius=16px" in url, (
        f"Expected 'border-radius=16px' in URL hash, got: {url}"
    )

    close_panel(page)


# ---------------------------------------------------------------------------
# 6.2 -- URL hash decoded on load
# ---------------------------------------------------------------------------


def test_url_hash_decoded_on_load(chromium_browser, http_server):
    """Navigate to the page with a hash, verify the knob is applied."""
    ctx = chromium_browser.new_context()
    pg = ctx.new_page()
    pg.goto(
        f"http://127.0.0.1:{http_server}/demo/index.html#accent-color=purple"
    )
    pg.wait_for_load_state("domcontentloaded")

    result = pg.evaluate(
        "getComputedStyle(document.documentElement)"
        ".getPropertyValue('--link').trim()"
    )
    assert result == "#8250df", (
        f"Expected accent-color purple (#8250df), got: {result}"
    )

    pg.close()
    ctx.close()


# ---------------------------------------------------------------------------
# 6.2 -- Hash takes priority over localStorage
# ---------------------------------------------------------------------------


def test_url_hash_priority_over_localstorage(chromium_browser, http_server):
    """Set a localStorage value, navigate with a different hash, verify hash wins."""
    ctx = chromium_browser.new_context()

    # First page: set border-radius to "16px" in localStorage
    pg1 = ctx.new_page()
    pg1.goto(f"http://127.0.0.1:{http_server}/demo/index.html")
    pg1.wait_for_load_state("domcontentloaded")
    pg1.evaluate(
        "localStorage.setItem('selfdoc-design-border-radius', '16px')"
    )
    pg1.close()

    # Second page: fresh load with hash specifying "0", which should win
    pg2 = ctx.new_page()
    pg2.goto(
        f"http://127.0.0.1:{http_server}/demo/index.html#border-radius=0"
    )
    pg2.wait_for_load_state("domcontentloaded")

    result = pg2.evaluate(
        "getComputedStyle(document.documentElement)"
        ".getPropertyValue('--radius').trim()"
    )
    assert result == "0", (
        f"Expected border-radius 0 (--radius: 0), got: {result}"
    )

    pg2.close()
    ctx.close()


# ---------------------------------------------------------------------------
# 6.3 -- Copy link button
# ---------------------------------------------------------------------------


def test_copy_link_button(page):
    """Click 'Copy link', verify clipboard contains the URL with hash."""
    open_panel(page)

    # Change a knob so the hash is non-empty
    click_knob_option(page, "border-radius", "16px")

    # Click "Copy link"
    page.click("#ds-copy-link")

    # Wait for "Copied!" confirmation
    page.wait_for_function(
        'document.getElementById("ds-copy-link").textContent === "Copied!"',
        timeout=5000,
    )

    # Verify clipboard contains the URL with the hash
    clipboard = page.evaluate("navigator.clipboard.readText()")
    assert "border-radius=16px" in clipboard, (
        f"Expected 'border-radius=16px' in clipboard URL, got: {clipboard}"
    )
    assert clipboard.startswith("http"), (
        f"Expected clipboard to contain a URL, got: {clipboard}"
    )

    close_panel(page)

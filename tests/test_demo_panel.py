"""Playwright-based tests for the demo page's design settings panel."""

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

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
def browser_instance():
    """Launch a Playwright Chromium browser for the entire session."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture()
def page(browser_instance, http_server):
    """Create a fresh page that navigates to the demo for each test."""
    ctx = browser_instance.new_context()
    # Grant clipboard permissions for the export test
    ctx.grant_permissions(["clipboard-read", "clipboard-write"])
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{http_server}/demo/index.html")
    pg.wait_for_load_state("networkidle")
    yield pg
    pg.close()
    ctx.close()


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


def test_page_loads_without_js_errors(browser_instance, http_server):
    ctx = browser_instance.new_context()
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda exc: errors.append(str(exc)))
    pg.goto(f"http://127.0.0.1:{http_server}/demo/index.html")
    pg.wait_for_load_state("networkidle")
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
    # sidebar-position
    (
        "sidebar-position",
        [
            ("left", "document.body.getAttribute('data-sidebar')", "left"),
            ("right", "document.body.getAttribute('data-sidebar')", "right"),
            ("hidden", "document.body.getAttribute('data-sidebar')", "hidden"),
        ],
    ),
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
                "240px",
                "getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width').trim()",
                "240px",
            ),
            (
                "280px",
                "getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width').trim()",
                "280px",
            ),
            (
                "320px",
                "getComputedStyle(document.documentElement).getPropertyValue('--sidebar-width').trim()",
                "320px",
            ),
        ],
    ),
    # toc-position
    (
        "toc-position",
        [
            ("right", "document.body.getAttribute('data-toc')", "right"),
            ("hidden", "document.body.getAttribute('data-toc')", "hidden"),
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
                "120ch",
                "getComputedStyle(document.documentElement).getPropertyValue('--content-max-width').trim()",
                "120ch",
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
                "serif",
                "getComputedStyle(document.documentElement).getPropertyValue('--font-body').trim()",
                "Georgia",
            ),
            (
                "monospace",
                "getComputedStyle(document.documentElement).getPropertyValue('--font-body').trim()",
                "JetBrains Mono",
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
    # heading-transform
    (
        "heading-transform",
        [
            (
                "uppercase",
                "getComputedStyle(document.documentElement).getPropertyValue('--heading-transform').trim()",
                "uppercase",
            ),
            (
                "small-caps",
                "document.body.classList.contains('heading-smallcaps')",
                True,
            ),
            (
                "normal",
                "getComputedStyle(document.documentElement).getPropertyValue('--heading-transform').trim()",
                "none",
            ),
        ],
    ),
    # heading-separator
    (
        "heading-separator",
        [
            (
                "top",
                "document.body.classList.contains('heading-sep-top')",
                True,
            ),
            (
                "bottom",
                "document.body.classList.contains('heading-sep-bottom')",
                True,
            ),
            (
                "none",
                "document.body.classList.contains('heading-sep-none')",
                True,
            ),
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
                "sharp",
                "getComputedStyle(document.documentElement).getPropertyValue('--radius').trim()",
                "0",
            ),
            (
                "subtle",
                "getComputedStyle(document.documentElement).getPropertyValue('--radius').trim()",
                "4px",
            ),
            (
                "rounded",
                "getComputedStyle(document.documentElement).getPropertyValue('--radius').trim()",
                "8px",
            ),
            (
                "pill",
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
    # table-style
    (
        "table-style",
        [
            (
                "striped",
                "document.body.getAttribute('data-table-style')",
                "striped",
            ),
            (
                "plain",
                "document.body.getAttribute('data-table-style')",
                "plain",
            ),
            (
                "bordered",
                "document.body.getAttribute('data-table-style')",
                "bordered",
            ),
            (
                "minimal",
                "document.body.getAttribute('data-table-style')",
                "minimal",
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
    click_knob_option(page, "border-radius", "pill")

    # Click export and wait for the button text to change (clipboard write is async)
    page.click("#ds-export")
    export_btn = page.locator("#ds-export")
    export_btn.wait_for(state="attached")
    # Wait until the button text becomes "Copied!" (async clipboard write)
    page.wait_for_function(
        'document.getElementById("ds-export").textContent === "Copied!"',
        timeout=5000,
    )
    assert export_btn.text_content() == "Copied!"

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
    ("sidebar-position", "right", [
        "grid-template-columns: minmax(0, 1fr) 200px var(--sidebar-width, 240px)",
        ".sidebar { order: 3; }",
        ".content { order: 1; }",
    ]),
    ("sidebar-position", "hidden", [
        ".sidebar { display: none; }",
        "grid-template-columns: minmax(0, 1fr) 200px",
    ]),
    ("sidebar-width", "280px", ["--sidebar-width: 280px"]),
    ("toc-position", "hidden", [
        ".toc { display: none; }",
        "grid-template-columns: var(--sidebar-width, 240px) minmax(0, 1fr)",
    ]),
    ("content-width", "90ch", ["--content-max-width: 90ch"]),
    ("font-kind", "serif", ['--font-body: Georgia, "Times New Roman", serif']),
    ("font-size", "18px", ["font-size: 18px"]),
    ("heading-transform", "uppercase", ["--heading-transform: uppercase"]),
    ("heading-transform", "small-caps", [
        "font-variant: small-caps",
        "text-transform: none",
    ]),
    ("heading-separator", "bottom", [
        "border-bottom: 1px solid var(--border)",
        "border-top: none",
    ]),
    ("heading-separator", "none", [
        "border-top: none",
        "padding-top: 0",
    ]),
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
    ("border-radius", "rounded", ["--radius: 8px"]),
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
    ("table-style", "plain", [
        "tr:nth-child(even) td { background: transparent; }",
    ]),
    ("table-style", "bordered", [
        "td, th { border: 1px solid var(--border); }",
    ]),
    ("table-style", "minimal", [
        "thead { border-bottom: 2px solid var(--border); }",
        "td { border: none; }",
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
        'document.getElementById("ds-export").textContent === "Copied!"',
        timeout=5000,
    )
    clipboard = page.evaluate("navigator.clipboard.readText()")
    for frag in expected_fragments:
        assert frag in clipboard, (
            f"Knob {knob_name}={value}: expected '{frag}' in export.\n"
            f"Got:\n{clipboard}"
        )
    close_panel(page)

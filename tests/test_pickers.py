"""Tests for version/locale pickers and absolute search base (Phase 1.4/1.5)."""

import re

from selfdoc.html import generate_html
from conftest import TEST_AUTHOR


def _make_html(available_versions=None, available_locales=None,
               current_version="", current_locale="",
               mount_version="1.0.0", mount_locale=""):
    """Generate HTML with the given version/locale configuration.

    A page is only version-scoped when it was built from a version, so the
    version picker needs a mount version to have anything to switch
    between; the locale picker needs a mount locale for the same reason.
    """
    return generate_html(
        {"index.md": "# Test\n\nHello.\n"},
        project_name="TestProject",
        version="1.0.0",
        mount_version=mount_version,
        mount_locale=mount_locale,
        available_versions=available_versions,
        available_locales=available_locales,
        current_version=current_version,
        current_locale=current_locale,
        author=TEST_AUTHOR,
    )


# --- Version picker ---


def test_version_picker_present_with_multiple_versions():
    """The version picker is present when multiple versions are configured."""
    versions = [
        {"version": "0.9.0"},
        {"version": "1.0.0"},
    ]
    files = _make_html(
        available_versions=versions,
        current_version="1.0.0",
    )
    content = files["index.html"]
    assert '<div class="sel version-picker">' in content
    assert 'role="combobox"' in content
    assert 'class="sel-opt"' in content
    assert "v0.9.0" in content
    assert "v1.0.0" in content


def test_version_picker_current_selected():
    """The current version's option is the one marked selected."""
    versions = [
        {"version": "0.9.0"},
        {"version": "1.0.0"},
    ]
    files = _make_html(
        available_versions=versions,
        current_version="1.0.0",
    )
    content = files["index.html"]
    # Each option carries the address the build computed for it, and the
    # one being rendered is the selected option.
    assert 'aria-selected="true" data-value="1.0.0" data-href="./"' in content
    assert 'data-value="0.9.0" data-href="v/0.9.0/"' in content
    assert 'aria-selected="true" data-value="0.9.0"' not in content


def test_no_version_picker_for_a_single_version():
    """A control with one option is not offered at all.

    It used to be rendered disabled; now the picker exists only when it
    can take the reader somewhere.
    """
    versions = [{"version": "1.0.0"}]
    files = _make_html(
        available_versions=versions,
        current_version="1.0.0",
    )
    content = files["index.html"]
    assert '<select class="version-picker"' not in content


def test_no_version_picker_on_a_page_that_is_not_version_scoped():
    """A `versioned: false` page has no version to switch away from."""
    versions = [{"version": "0.9.0"}, {"version": "1.0.0"}]
    files = _make_html(
        available_versions=versions,
        current_version="",
        mount_version="",
    )
    content = files["index.html"]
    assert '<select class="version-picker"' not in content


def test_version_picker_button_names_its_own_listbox():
    """The combobox's aria-controls has to reach the listbox beside it.

    The shape is pinned by the framework's markup contract, and it is the
    one part a server can get wrong silently: a button pointing at an id
    no element carries reads to assistive technology as a combobox with
    no options at all.
    """
    versions = [
        {"version": "0.9.0"},
        {"version": "1.0.0"},
    ]
    files = _make_html(
        available_versions=versions,
        current_version="1.0.0",
    )
    content = files["index.html"]
    controls = re.search(r'aria-controls="([^"]+)"', content)
    assert controls, content
    assert f'<div class="sel-menu" id="{controls.group(1)}" role="listbox">' in content


def test_no_version_picker_when_none():
    """No version picker appears when available_versions is None."""
    files = _make_html(available_versions=None)
    content = files["index.html"]
    assert "version-picker" not in content


# --- Locale picker ---


def test_locale_picker_present_with_multiple_locales():
    """The locale picker is present when multiple locales are configured."""
    locales = [
        {"code": "en", "label": "English"},
        {"code": "fr", "label": "French"},
    ]
    files = _make_html(
        available_locales=locales,
        current_locale="en",
        mount_locale="en",
    )
    content = files["en/index.html"]
    assert '<div class="sel locale-picker">' in content
    assert "English" in content
    assert "French" in content
    # Each option addresses this same page in the other locale.
    assert 'data-value="fr" data-href="../fr/"' in content


def test_locale_picker_current_selected():
    """The current_locale option gets the selected attribute."""
    locales = [
        {"code": "en", "label": "English"},
        {"code": "fr", "label": "French"},
    ]
    files = _make_html(
        available_locales=locales,
        current_locale="fr",
        mount_locale="fr",
    )
    content = files["fr/index.html"]
    assert 'aria-selected="true" data-value="fr"' in content
    assert 'aria-selected="true" data-value="en"' not in content


def test_no_locale_picker_for_a_single_locale():
    """One locale means no locale segment and nothing to switch between."""
    locales = [{"code": "en", "label": "English"}]
    files = _make_html(
        available_locales=locales,
        current_locale="en",
    )
    content = files["index.html"]
    assert "locale-picker" not in content


def test_no_picker_prints_a_native_select():
    """The hidden native <select> is the framework's to print, never ours.

    The framework's own factory emits one for form participation, and the
    conformance checker allows it there because the allowance is keyed on
    the file's location inside the packaged assets.  Server-emitted markup
    printing one would be a banned native control on the page.
    """
    locales = [
        {"code": "en", "label": "English"},
        {"code": "fr", "label": "French"},
    ]
    files = _make_html(
        available_locales=locales,
        current_locale="en",
        mount_locale="en",
    )
    content = files["en/index.html"]
    assert "<select" not in content
    assert "<option" not in content


def test_no_locale_picker_when_none():
    """No locale picker appears when available_locales is None."""
    files = _make_html(available_locales=None)
    content = files["index.html"]
    assert "locale-picker" not in content


# --- The Pagefind bundle path follows the page's own address ---


def test_search_assets_at_the_output_root():
    """An unmounted page loads the bundle from pagefind/ beside itself.

    No ``bundlePath`` accompanies it: the UI derives the index location
    from where this very bundle was loaded, which is the only value that
    is right at every depth. See ``pagefind_init_script``.
    """
    files = _make_html()
    content = files["index.html"]
    assert 'href="pagefind/pagefind-ui.css"' in content
    assert "bundlePath" not in content


def test_search_bundle_path_is_never_site_absolute():
    """A mounted page reaches the index without leaving the mount."""
    files = generate_html(
        {"guide.md": "# Guide\n\nHello.\n"},
        project_name="TestProject",
        version="1.0.0",
        mount_locale="en",
        mount_version="1.0.0",
        mount_archived=True,
        author=TEST_AUTHOR,
    )
    content = files["en/v/1.0.0/guide/index.html"]
    assert 'href="../../../../pagefind/pagefind-ui.css"' in content
    assert "bundlePath" not in content


# --- A framework theme's module specifiers ---


def test_no_module_specifier_is_ever_bare():
    """A specifier starting with neither "." nor "/" is refused outright.

    The palette script imports the framework's module and the index's
    query API, and at the output root -- the front page, and every
    project's landing page -- the hop to both is empty.  Written without
    a leading "./" the specifier becomes bare, which a browser answers
    with "Failed to resolve module specifier" and no search at all.  The
    Pagefind bundle path made this exact mistake in this exact place
    before, which is why there is a test rather than a habit.
    """
    from selfdoc_core.html import palette_search_script

    for asset_prefix, css_href in (
        ("", "css/style.css"),
        ("../", "../css/style.css"),
        ("../../", "../../_chrome/tinymoon-abc123/css/style.css"),
    ):
        script = palette_search_script(asset_prefix, css_href)
        specifiers = re.findall(r'(?:from|import\()\s*"([^"]+)"', script)
        assert specifiers, script
        for specifier in specifiers:
            assert specifier.startswith(("./", "../", "/")), (
                f"bare module specifier {specifier!r} at prefix "
                f"{asset_prefix!r}"
            )


def test_the_module_payload_is_addressed_from_the_stylesheet():
    """One address decides both, so they cannot disagree."""
    from selfdoc_core.html import theme_modules_prefix

    assert theme_modules_prefix("css/style.css") == "js/"
    assert theme_modules_prefix("../css/style.css") == "../js/"
    assert (
        theme_modules_prefix("../_chrome/tinymoon-abc123/css/style.css")
        == "../_chrome/tinymoon-abc123/js/"
    )


def test_a_plain_themes_stylesheet_has_no_module_payload():
    """Asking for one is a mistake, not a value to invent."""
    import pytest

    from selfdoc_core.html import theme_modules_prefix

    with pytest.raises(ValueError, match="framework payload"):
        theme_modules_prefix("style.css")

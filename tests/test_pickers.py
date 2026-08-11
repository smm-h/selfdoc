"""Tests for version/locale pickers and absolute search base (Phase 1.4/1.5)."""

from selfdoc.html import generate_html


def _make_html(available_versions=None, available_locales=None,
               current_version="", current_locale=""):
    """Generate HTML with the given version/locale configuration."""
    return generate_html(
        {"index.md": "# Test\n\nHello.\n"},
        project_name="TestProject",
        version="1.0.0",
        available_versions=available_versions,
        available_locales=available_locales,
        current_version=current_version,
        current_locale=current_locale,
    )


# --- Version picker ---


def test_version_picker_present_with_multiple_versions():
    """Version picker <select> is present when multiple versions configured."""
    versions = [
        {"version": "0.9.0"},
        {"version": "1.0.0"},
    ]
    files = _make_html(
        available_versions=versions,
        current_version="1.0.0",
    )
    content = files["index.html"]
    assert '<select class="version-picker"' in content
    assert "<option" in content
    assert "v0.9.0" in content
    assert "v1.0.0" in content


def test_version_picker_current_selected():
    """The current_version option gets the selected attribute."""
    versions = [
        {"version": "0.9.0"},
        {"version": "1.0.0"},
    ]
    files = _make_html(
        available_versions=versions,
        current_version="1.0.0",
    )
    content = files["index.html"]
    assert 'value="1.0.0" selected' in content
    # The non-current version should not be selected
    assert 'value="0.9.0" selected' not in content


def test_version_picker_disabled_single_version():
    """Version picker is disabled when only 1 version exists."""
    versions = [{"version": "1.0.0"}]
    files = _make_html(
        available_versions=versions,
        current_version="1.0.0",
    )
    content = files["index.html"]
    assert '<select class="version-picker"' in content
    assert "disabled" in content.split("version-picker")[1].split(">")[0]


def test_version_picker_not_disabled_multiple_versions():
    """Version picker is not disabled when multiple versions exist."""
    versions = [
        {"version": "0.9.0"},
        {"version": "1.0.0"},
    ]
    files = _make_html(
        available_versions=versions,
        current_version="1.0.0",
    )
    content = files["index.html"]
    picker_tag = content.split("version-picker")[1].split(">")[0]
    assert "disabled" not in picker_tag


def test_no_version_picker_when_none():
    """No version picker <select> appears when available_versions is None."""
    files = _make_html(available_versions=None)
    content = files["index.html"]
    assert '<select class="version-picker"' not in content


# --- Locale picker ---


def test_locale_picker_present_with_multiple_locales():
    """Locale picker <select> is present when multiple locales configured."""
    locales = [
        {"code": "en", "label": "English"},
        {"code": "fr", "label": "French"},
    ]
    files = _make_html(
        available_locales=locales,
        current_locale="en",
    )
    content = files["index.html"]
    assert '<select class="locale-picker"' in content
    assert "English" in content
    assert "French" in content


def test_locale_picker_current_selected():
    """The current_locale option gets the selected attribute."""
    locales = [
        {"code": "en", "label": "English"},
        {"code": "fr", "label": "French"},
    ]
    files = _make_html(
        available_locales=locales,
        current_locale="fr",
    )
    content = files["index.html"]
    assert 'value="fr" selected' in content
    assert 'value="en" selected' not in content


def test_locale_picker_disabled_single_locale():
    """Locale picker is disabled when only 1 locale exists."""
    locales = [{"code": "en", "label": "English"}]
    files = _make_html(
        available_locales=locales,
        current_locale="en",
    )
    content = files["index.html"]
    assert '<select class="locale-picker"' in content
    assert "disabled" in content.split("locale-picker")[1].split(">")[0]


def test_locale_picker_not_disabled_multiple_locales():
    """Locale picker is not disabled when multiple locales exist."""
    locales = [
        {"code": "en", "label": "English"},
        {"code": "fr", "label": "French"},
    ]
    files = _make_html(
        available_locales=locales,
        current_locale="en",
    )
    content = files["index.html"]
    picker_tag = content.split("locale-picker")[1].split(">")[0]
    assert "disabled" not in picker_tag


def test_no_locale_picker_when_none():
    """No locale picker <select> appears when available_locales is None."""
    files = _make_html(available_locales=None)
    content = files["index.html"]
    assert '<select class="locale-picker"' not in content


# --- Search dialog uses data-search-base ---


def test_search_dialog_has_data_search_base():
    """Search dialog carries a document-relative data-search-base."""
    files = _make_html()
    content = files["index.html"]
    # Unmounted build: the page is already at the output root.
    assert 'data-search-base="./"' in content
    assert "data-search-prefix" not in content


def test_search_dialog_base_is_never_site_absolute():
    """A mounted page reaches the search index without leaving the mount."""
    files = generate_html(
        {"guide.md": "# Guide\n\nHello.\n"},
        project_name="TestProject",
        version="1.0.0",
        mount_locale="en",
        mount_version="1.0.0",
    )
    content = files["en/1.0.0/guide/index.html"]
    assert 'data-search-base="../../../"' in content

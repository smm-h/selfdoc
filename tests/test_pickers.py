"""Tests for version/locale pickers and absolute search base (Phase 1.4/1.5)."""

from selfdoc.html import generate_html


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
    # Each option carries the address the build computed for it, then the
    # selected marker on the one being rendered.
    assert 'value="1.0.0" data-href="./" selected' in content
    assert 'value="0.9.0" data-href="v/0.9.0/"' in content
    assert 'value="0.9.0" data-href="v/0.9.0/" selected' not in content


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
        mount_locale="en",
    )
    content = files["en/index.html"]
    assert '<select class="locale-picker"' in content
    assert "English" in content
    assert "French" in content
    # Each option addresses this same page in the other locale.
    assert 'value="fr" data-href="../fr/"' in content


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
    assert 'value="fr" data-href="../fr/" selected' in content
    assert 'value="en" data-href="../en/" selected' not in content


def test_no_locale_picker_for_a_single_locale():
    """One locale means no locale segment and nothing to switch between."""
    locales = [{"code": "en", "label": "English"}]
    files = _make_html(
        available_locales=locales,
        current_locale="en",
    )
    content = files["index.html"]
    assert '<select class="locale-picker"' not in content


def test_locale_picker_not_disabled_multiple_locales():
    """Locale picker is not disabled when multiple locales exist."""
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
    picker_tag = content.split('<select class="locale-picker"')[1].split(">")[0]
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
        mount_archived=True,
    )
    content = files["en/v/1.0.0/guide/index.html"]
    assert 'data-search-base="../../../../"' in content

"""Overriding the configured theme for one build, and one preview.

A theme is judged by looking at real pages under it, and the pages worth
judging it on belong to a dozen projects that each declare a theme in
their own ``selfdoc.json``.  Editing twelve configs to look at a theme --
and editing them back afterwards -- is how a config gets left wrong, so
the override is a flag instead.

Two things have to agree for a page to look right: what the build
rendered the page's inlined critical CSS against, and which site-level
chrome asset the page then references.  The build takes the override
directly; the chrome normally reads each project's manifest, and takes
the same override so a preview cannot end up serving one theme's pages
against another theme's stylesheet.  Both halves are asserted here, and
so is the manifest field the chrome reads when no override is in play.

Nothing here writes a theme back to any config.  The override lives as
long as the call does, which is the property that makes it safe to use on
somebody else's checkout.
"""

from __future__ import annotations

import json
import os

import pytest

from selfblog import assembly
from selfblog.chrome import chrome_themes, manifest_theme
from selfblog.preview import (
    built_under_theme,
    expected_stylesheet,
    preview_assembly,
)
from selfdoc_core.build import build
from selfdoc_core.config import ConfigError
from selfdoc_core.manifest import (
    DEFAULT_THEME,
    generate_manifest,
    manifest_compat,
)
from selfdoc_core.themes import get_theme, get_theme_meta, list_themes

from conftest import default_config

CANONICAL_BASE = "https://docs.example.com"


@pytest.fixture()
def themed_project(tmp_path):
    """A minimal project whose config names a theme."""
    config = default_config(docs="docs/", output="docs/_build/")
    config["theme"] = "minimal"
    with open(os.path.join(tmp_path, "selfdoc.json"), "w", encoding="utf-8") as f:
        json.dump(config, f)
    docs = os.path.join(tmp_path, "docs")
    os.makedirs(docs)
    with open(os.path.join(docs, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Test Project\n\nWelcome.\n")
    return tmp_path


def _manifest(project_dir):
    path = os.path.join(project_dir, ".selfdoc", "manifest.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class TestTheRegistryIsTheOneList:
    def test_tinymoon_is_registered(self) -> None:
        assert "tinymoon" in list_themes()

    def test_the_listing_is_every_css_file(self) -> None:
        assert set(list_themes()) >= {"clean", "minimal", "tinymoon"}

    def test_every_listed_theme_loads(self) -> None:
        for name in list_themes():
            assert get_theme(name).strip()

    def test_tinymoon_fetches_no_fonts_from_the_network(self) -> None:
        """The faces are inlined; a CDN URL here would be a second source."""
        meta = get_theme_meta("tinymoon")
        assert meta["fonts_url"] is None
        assert meta["fonts_preconnect"] == []

    def test_tinymoon_inlines_its_faces(self) -> None:
        css = get_theme("tinymoon")
        assert css.count("@font-face") == 3
        assert "data:font/woff2;base64," in css
        assert "fonts.googleapis.com" not in css

    def test_the_inlined_faces_are_below_the_critical_marker(self) -> None:
        """Above it, every byte is inlined into the head of every page."""
        css = get_theme("tinymoon")
        assert css.index("/* --- NON-CRITICAL --- */") < css.index("@font-face")


def _built_css(project_dir):
    with open(
        os.path.join(project_dir, "docs", "_build", "style.css"),
        encoding="utf-8",
    ) as f:
        return f.read()


#: A declaration only tinymoon makes, so its presence in a build's
#: stylesheet is the theme's fingerprint.
_TINYMOON_MARKER = "--grain-opacity"


class TestTheBuildOverride:
    def test_the_config_decides_when_no_override_is_given(
        self, themed_project,
    ) -> None:
        build(str(themed_project))
        assert _TINYMOON_MARKER not in _built_css(themed_project)

    def test_the_override_reaches_the_rendered_css(self, themed_project) -> None:
        build(str(themed_project), theme="tinymoon")
        assert _TINYMOON_MARKER in _built_css(themed_project)

    def test_the_override_is_not_written_back_to_the_config(
        self, themed_project,
    ) -> None:
        build(str(themed_project), theme="tinymoon")
        with open(
            os.path.join(themed_project, "selfdoc.json"), encoding="utf-8",
        ) as f:
            assert json.load(f)["theme"] == "minimal"

    def test_an_unknown_theme_is_refused(self, themed_project) -> None:
        with pytest.raises(ConfigError) as excinfo:
            build(str(themed_project), theme="nosuchtheme")
        assert "nosuchtheme" in str(excinfo.value)
        assert "tinymoon" in str(excinfo.value)

    def test_the_refusal_leaves_no_output_behind(self, themed_project) -> None:
        with pytest.raises(ConfigError):
            build(str(themed_project), theme="nosuchtheme")
        assert not os.path.exists(
            os.path.join(themed_project, "docs", "_build", "style.css"),
        )


class TestTheManifestRecordsTheTheme:
    """``selfdoc gen`` writes the manifest, and the manifest is what the
    assembly's chrome reads to decide which stylesheet a project's pages
    reference.  Without the field every project's pages referenced the
    default theme's asset no matter what the project configured."""

    def test_a_config_naming_a_theme_records_it(self, tmp_path) -> None:
        config = default_config()
        config["theme"] = "tinymoon"
        manifest = generate_manifest(config, {}, dir_path=str(tmp_path))
        assert manifest.theme == "tinymoon"

    def test_a_config_naming_none_records_the_default(self, tmp_path) -> None:
        manifest = generate_manifest(default_config(), {}, dir_path=str(tmp_path))
        assert manifest.theme == DEFAULT_THEME

    def test_the_field_is_written_to_disk(self, tmp_path) -> None:
        config = default_config()
        config["theme"] = "tinymoon"
        generate_manifest(config, {}, dir_path=str(tmp_path))
        with open(
            os.path.join(tmp_path, ".selfdoc", "manifest.json"),
            encoding="utf-8",
        ) as f:
            assert json.load(f)["theme"] == "tinymoon"

    def test_an_older_manifest_without_the_field_still_reads(self) -> None:
        """The reader is tolerant by contract; this is that contract."""
        manifest = manifest_compat({"schema_version": 1, "slug": "alpha"})
        assert manifest.theme == ""


class TestTheManifestCarriesTheThemeToTheChrome:
    """The site-level asset is keyed by what each manifest declares."""

    def test_a_manifest_without_a_theme_reads_as_the_default(self) -> None:
        assert manifest_theme({"slug": "alpha"}) == DEFAULT_THEME

    def test_a_manifest_with_a_theme_reads_as_that_theme(self) -> None:
        assert manifest_theme({"slug": "alpha", "theme": "tinymoon"}) == "tinymoon"

    def test_the_asset_set_follows_the_manifests(self) -> None:
        by_slug, home = chrome_themes(
            [
                {"slug": "alpha", "theme": "tinymoon"},
                {"slug": "beta", "theme": "tinymoon"},
                {"slug": "home", "theme": "tinymoon"},
            ],
            home_slug="home",
        )
        assert set(by_slug.values()) == {"tinymoon"}
        assert home == "tinymoon"

    def test_a_generated_manifest_hands_its_theme_to_the_chrome(
        self, tmp_path,
    ) -> None:
        """The joint the chain turns on, asserted on real output."""
        config = default_config()
        config["theme"] = "tinymoon"
        generate_manifest(config, {}, dir_path=str(tmp_path))
        assert manifest_theme(_manifest(tmp_path)) == "tinymoon"

    def test_the_override_beats_every_manifest(self) -> None:
        """What ``preview --theme`` needs: the checkouts were all built
        under one theme, so their pages reference that theme's asset
        regardless of what their committed manifests declare."""
        manifests = [
            {"slug": "alpha", "theme": "minimal"},
            {"slug": "beta", "theme": "clean"},
            {"slug": "home"},
        ]
        by_slug, home = chrome_themes(manifests, "home", "tinymoon")
        assert set(by_slug.values()) == {"tinymoon"}
        assert home == "tinymoon"

    def test_no_override_leaves_every_project_alone(self) -> None:
        manifests = [
            {"slug": "alpha", "theme": "minimal"},
            {"slug": "beta", "theme": "clean"},
            {"slug": "home"},
        ]
        by_slug, home = chrome_themes(manifests, "home")
        assert by_slug == {
            "alpha": "minimal", "beta": "clean", "home": DEFAULT_THEME,
        }
        assert home == DEFAULT_THEME


class TestTheBuildInvocation:
    """What ``build_source_project`` actually asks the toolchain to run."""

    @pytest.fixture()
    def recorded(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            assembly, "_run_step",
            lambda argv, **kwargs: calls.append(argv),
        )
        monkeypatch.setattr(assembly, "detect_latest_version", lambda d: "")
        return calls

    def test_no_theme_flag_when_none_is_asked_for(self, recorded) -> None:
        argv = assembly.build_source_project("/nowhere", "full")
        assert "--theme" not in argv

    def test_the_theme_is_passed_through(self, recorded) -> None:
        argv = assembly.build_source_project(
            "/nowhere", "full", theme="tinymoon",
        )
        assert argv[argv.index("--theme") + 1] == "tinymoon"

    def test_the_home_build_gets_it_too(self, recorded, tmp_path) -> None:
        """The home project builds through a different command entirely."""
        argv = assembly.build_source_project(
            "/nowhere", "full", home=True, manifests_dir=str(tmp_path),
            theme="tinymoon",
        )
        assert argv[:3] == ["selfblog", "build", "--target"]
        assert argv[argv.index("--theme") + 1] == "tinymoon"

    def test_a_posts_build_gets_it_too(self, recorded) -> None:
        argv = assembly.build_source_project(
            "/nowhere", "posts", theme="tinymoon",
        )
        assert argv[argv.index("--theme") + 1] == "tinymoon"


class TestThePreviewOverride:
    """Refusals only: the accepting path runs a real build per project,
    which the preview suite covers with pre-populated build trees that a
    theme override could not touch."""

    def test_an_unknown_theme_is_refused(self, tmp_path) -> None:
        out = tmp_path / "out"
        with pytest.raises(ValueError) as excinfo:
            preview_assembly(
                home_dir=str(tmp_path / "home"), project_dirs=[],
                out_dir=str(out), canonical_base=CANONICAL_BASE,
                build=True, theme="nosuchtheme",
            )
        assert "nosuchtheme" in str(excinfo.value)
        assert "tinymoon" in str(excinfo.value)

    def test_the_refusal_happens_before_anything_is_written(
        self, tmp_path,
    ) -> None:
        out = tmp_path / "out"
        with pytest.raises(ValueError):
            preview_assembly(
                home_dir=str(tmp_path / "home"), project_dirs=[],
                out_dir=str(out), canonical_base=CANONICAL_BASE,
                build=True, theme="nosuchtheme",
            )
        assert not out.exists()


class TestTheStylesheetEqualityCheck:
    """``--theme`` with ``--no-build`` trusts nothing: the build trees on
    disk have to have been produced under that theme, and the test is an
    equality against the stylesheet the build writes."""

    def test_a_tree_built_under_the_theme_passes(self, tmp_path) -> None:
        checkout = tmp_path / "proj"
        build_dir = checkout / "docs" / "_build"
        build_dir.mkdir(parents=True)
        (build_dir / "style.css").write_text(expected_stylesheet("tinymoon"))
        assert built_under_theme(str(checkout), "tinymoon")

    def test_a_tree_built_under_another_theme_fails(self, tmp_path) -> None:
        checkout = tmp_path / "proj"
        build_dir = checkout / "docs" / "_build"
        build_dir.mkdir(parents=True)
        (build_dir / "style.css").write_text(expected_stylesheet("minimal"))
        assert not built_under_theme(str(checkout), "tinymoon")

    def test_a_tree_built_under_an_older_theme_file_fails(
        self, tmp_path,
    ) -> None:
        """Editing the theme after a build makes the build stale, and
        being told so is the point rather than a false alarm."""
        checkout = tmp_path / "proj"
        build_dir = checkout / "docs" / "_build"
        build_dir.mkdir(parents=True)
        (build_dir / "style.css").write_text(
            expected_stylesheet("tinymoon") + "\n.late{color:red}",
        )
        assert not built_under_theme(str(checkout), "tinymoon")

    def test_a_checkout_with_no_build_output_fails(self, tmp_path) -> None:
        assert not built_under_theme(str(tmp_path / "nothing"), "tinymoon")

    def test_the_expected_stylesheet_differs_per_theme(self) -> None:
        assert (
            expected_stylesheet("tinymoon")
            != expected_stylesheet("minimal")
            != expected_stylesheet("clean")
        )

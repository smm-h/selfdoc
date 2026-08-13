"""A theme may consume a framework rather than imitate one.

The tinymoon theme used to be a 183 KB restatement of someone else's design
language on selfdoc's class surface: the palette copied, the reset copied,
the three faces carried as 110 KB of base64 in every stylesheet.  It now
declares a *framework* in its companion JSON, and the composition is the
framework's own shipped sheets followed by a selfdoc overlay -- 67 KB of
overlay where the whole file used to be 183 KB, and the minified stylesheet
a page receives went from 158 KB to 116 KB with the four faces moved out
into separately cached files.

What is asserted here is the delivery shape, because that is where a
composition can quietly go wrong:

- the composed stylesheet really is the framework's bytes (a rename in the
  package must reach the page, not be shadowed by a local copy);
- nothing of it is inlined as critical CSS, because the framework's
  ``@font-face`` rules are relative to the stylesheet's own location;
- the stylesheet is written where those relative URLs resolve -- ``css/``
  with ``fonts/`` beside it -- in a standalone build and in the assembly's
  site-level chrome alike;
- the assembly's content hash covers the framework bytes, so a framework
  upgrade renames the payload and no cache serves the old one.
"""

import os

import pytest
import tinymoon

from selfdoc_core.themes import (
    DEFAULT_CSS_REL,
    FRAMEWORK_CSS_REL,
    framework_sheets_css,
    get_theme,
    get_theme_meta,
    list_themes,
    theme_assets,
    theme_css_rel,
    theme_framework,
    theme_overlay,
)

#: The order the framework's markup contract requires.  tokens before
#: everything, base before the shapes, prose last so the reading scale wins
#: over the app-scale docs family it extends.
CONTRACT_SHEET_ORDER = ["tokens", "base", "shell", "primitives", "widgets", "prose"]


def _uncommented(css: str) -> str:
    """*css* with its comments removed -- the rules, not the prose."""
    import re

    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


PLAIN_THEMES = [t for t in list_themes() if not theme_framework(t)]


class TestTheDeclaration:
    def test_tinymoon_declares_the_framework(self) -> None:
        block = theme_framework("tinymoon")
        assert block is not None
        assert block["package"] == "tinymoon"

    def test_the_sheets_are_named_in_contract_order(self) -> None:
        assert theme_framework("tinymoon")["sheets"] == CONTRACT_SHEET_ORDER

    def test_every_other_theme_is_a_whole_stylesheet(self) -> None:
        assert PLAIN_THEMES, "no plain theme left to compare against"
        for theme in PLAIN_THEMES:
            assert theme_framework(theme) is None

    def test_a_framework_block_without_sheets_is_refused(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Half a declaration is a broken theme, not a theme with defaults."""
        import selfdoc_core.themes as themes

        monkeypatch.setattr(
            themes, "get_theme_meta",
            lambda name: {"framework": {"package": "tinymoon"}},
        )
        with pytest.raises(ValueError, match="'sheets'"):
            themes.theme_framework("tinymoon")

    def test_an_unknown_package_is_refused(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import selfdoc_core.themes as themes

        monkeypatch.setattr(
            themes, "get_theme_meta",
            lambda name: {"framework": {"package": "nowhere", "sheets": ["a"]}},
        )
        with pytest.raises(ValueError, match="nowhere"):
            themes.framework_sheets_css("tinymoon")


class TestTheComposition:
    @pytest.mark.parametrize("sheet", CONTRACT_SHEET_ORDER)
    def test_the_framework_bytes_are_shipped_as_they_are(self, sheet: str) -> None:
        """Not a port of the sheet -- the sheet."""
        source = (tinymoon.assets_path() / "css" / f"{sheet}.css").read_text()
        assert source in get_theme("tinymoon")

    def test_the_sheets_appear_in_the_declared_order(self) -> None:
        composed = framework_sheets_css("tinymoon")
        positions = [
            composed.index(
                (tinymoon.assets_path() / "css" / f"{s}.css").read_text()
            )
            for s in CONTRACT_SHEET_ORDER
        ]
        assert positions == sorted(positions)

    def test_the_overlay_comes_last(self) -> None:
        """The overlay is an overlay: it has to be able to win."""
        composed = get_theme("tinymoon")
        overlay = theme_overlay("tinymoon")
        assert composed.endswith(overlay)

    def test_nothing_is_inlined_into_the_page_head(self) -> None:
        """Critical CSS is extracted from above the marker.

        The framework addresses its faces at ``../fonts/``, which resolves
        against the stylesheet.  Inlined into a page's <head>, the same rule
        resolves against the page's own directory and finds nothing, so the
        composition declares itself entirely non-critical.
        """
        from selfdoc_core.build import _extract_critical_css

        critical, _ = _extract_critical_css(get_theme("tinymoon"))
        assert critical.strip() == ""

    def test_the_overlay_carries_no_font_bytes(self) -> None:
        """110 KB of base64 per stylesheet, replaced by four real files."""
        overlay = _uncommented(theme_overlay("tinymoon"))
        assert "base64" not in overlay
        assert "@font-face" not in overlay

    def test_the_overlay_restates_no_palette(self) -> None:
        """The framework's tokens.css is the palette; a copy would drift.

        The overlay's own ``:root`` is the bridge -- selfdoc's variable
        names pointed at the framework's -- so every declaration in it is a
        ``var()`` reference and none is a colour.
        """
        import re

        overlay = _uncommented(theme_overlay("tinymoon"))
        # Only the top-level bridge: the print sheet forces ink on white
        # inside @media print, which is paper, not palette.
        for block in re.findall(r"^:root\s*\{([^}]*)\}", overlay, re.M):
            for declaration in block.split(";"):
                if ":" not in declaration:
                    continue
                name, _, value = declaration.partition(":")
                assert value.strip().startswith("var("), (
                    f"the bridge declares {name.strip()} as a literal "
                    f"{value.strip()!r}; it must reference a framework token"
                )

    def test_the_overlay_is_a_fraction_of_what_it_replaced(self) -> None:
        """The file was 183 KB.  A regression to a restatement is visible."""
        assert len(theme_overlay("tinymoon").encode()) < 90_000


class TestWhereTheStylesheetGoes:
    def test_a_framework_theme_sits_beside_its_fonts(self) -> None:
        assert theme_css_rel("tinymoon") == FRAMEWORK_CSS_REL
        assert FRAMEWORK_CSS_REL.startswith("css/")

    @pytest.mark.parametrize("theme", PLAIN_THEMES)
    def test_a_plain_theme_keeps_the_root_stylesheet(self, theme: str) -> None:
        assert theme_css_rel(theme) == DEFAULT_CSS_REL

    def test_the_metadata_carries_the_address(self) -> None:
        """Every page renderer already holds the metadata, so it holds this."""
        for theme in list_themes():
            meta = get_theme_meta(theme)
            assert meta["name"] == theme
            assert meta["css_rel"] == theme_css_rel(theme)

    def test_the_font_urls_resolve_from_that_directory(self) -> None:
        """``../fonts/x.woff2`` from ``css/style.css`` is ``fonts/x.woff2``."""
        import posixpath
        import re

        base = (tinymoon.assets_path() / "css" / "base.css").read_text()
        urls = re.findall(r'url\("(\.\./[^"]+)"\)', base)
        assert urls, "the framework's base.css declares no relative font URLs"
        destinations = {rel for _, rel in theme_assets("tinymoon")}
        for url in urls:
            resolved = posixpath.normpath(
                posixpath.join(posixpath.dirname(FRAMEWORK_CSS_REL), url)
            )
            assert resolved in destinations, (
                f"{url} resolves to {resolved}, which no theme asset provides"
            )


class TestTheAssetsThatTravelWithIt:
    def test_the_faces_are_real_files(self) -> None:
        fonts = [rel for _, rel in theme_assets("tinymoon")
                 if rel.startswith("fonts/")]
        assert len(fonts) >= 4
        assert all(rel.endswith(".woff2") for rel in fonts)

    def test_only_the_declared_kinds_travel(self) -> None:
        """The declaration drives the payload, not a hardcoded list.

        Only ``fonts`` is declared today, because only the ``@font-face``
        rules reference anything outside the stylesheet.  The framework's ES
        modules join the declaration when a page imports one; shipping 536 KB
        of modules nothing references would be dead weight on every deploy.
        """
        kinds = {rel.split("/")[0] for _, rel in theme_assets("tinymoon")}
        assert kinds == set(theme_framework("tinymoon")["assets"])

    def test_every_source_exists(self) -> None:
        for src, _ in theme_assets("tinymoon"):
            assert os.path.isfile(src)

    @pytest.mark.parametrize("theme", PLAIN_THEMES)
    def test_a_plain_theme_ships_nothing_beside_its_stylesheet(
        self, theme: str,
    ) -> None:
        assert theme_assets(theme) == []


class TestTheStandaloneBuild:
    """A project deployed on its own has no assembly to serve the payload."""

    @pytest.fixture(scope="class")
    def built(self, tmp_path_factory: pytest.TempPathFactory) -> str:
        import json

        from selfdoc_core.build import build

        root = tmp_path_factory.mktemp("tm-standalone")
        (root / "src").mkdir()
        (root / "src" / "__init__.py").write_text('"""Example."""\n')
        docs = root / "docs"
        docs.mkdir()
        (docs / "index.md").write_text(
            "# Home\n\nA paragraph.\n\n## A section\n\nMore.\n\n"
            "## Another\n\nMore still.\n"
        )
        (root / "selfdoc.json").write_text(json.dumps({
            "source": [{"path": "src/", "language": "python"}],
            "base_url": "https://example.com",
            "version": "1.0.0",
            "versions": [{"version": "1.0.0"}],
            "locales": [{"code": "en", "label": "English", "default": True}],
            "search_engine": "pagefind",
            "author": {"name": "Test", "url": "https://author.example"},
            "theme": "tinymoon",
        }))
        build(str(root))
        return str(root / "docs" / "_build")

    def test_the_stylesheet_is_written_under_css(self, built: str) -> None:
        assert os.path.isfile(os.path.join(built, "css", "style.css"))
        assert not os.path.isfile(os.path.join(built, "style.css"))

    def test_the_fonts_are_beside_it(self, built: str) -> None:
        fonts = os.path.join(built, "fonts")
        assert os.path.isdir(fonts)
        assert any(n.endswith(".woff2") for n in os.listdir(fonts))

    def test_nothing_undeclared_is_written(self, built: str) -> None:
        assert not os.path.isdir(os.path.join(built, "js"))

    def test_every_font_url_in_the_written_sheet_resolves(
        self, built: str,
    ) -> None:
        import re

        css_dir = os.path.join(built, "css")
        with open(os.path.join(css_dir, "style.css"), encoding="utf-8") as f:
            written = f.read()
        for url in re.findall(r'url\("(\.\./[^"]+)"\)', written):
            assert os.path.isfile(os.path.normpath(os.path.join(css_dir, url)))

    def test_the_pages_reference_it(self, built: str) -> None:
        page = None
        for dirpath, _dirs, files in os.walk(built):
            if "index.html" in files:
                page = os.path.join(dirpath, "index.html")
                break
        assert page is not None
        with open(page, encoding="utf-8") as f:
            html = f.read()
        hop = os.path.relpath(built, os.path.dirname(page)).replace(os.sep, "/")
        prefix = "" if hop == "." else hop + "/"
        assert f'href="{prefix}css/style.css"' in html


class TestTheAssemblyChrome:
    """The site-level asset is a directory when the theme ships a payload."""

    def test_the_asset_is_a_directory_under_the_chrome_dir(self) -> None:
        from selfblog.chrome import CHROME_DIR, chrome_asset_rel, chrome_css

        rel = chrome_asset_rel("tinymoon", chrome_css("tinymoon"))
        assert rel.startswith(f"{CHROME_DIR}/tinymoon-")
        assert rel.endswith("/css/style.css")

    def test_a_plain_theme_stays_one_file(self) -> None:
        from selfblog.chrome import chrome_asset_rel, chrome_css

        rel = chrome_asset_rel("minimal", chrome_css("minimal"))
        assert rel.endswith(".css")
        assert "/css/" not in rel

    def test_the_hash_covers_the_framework_bytes(self) -> None:
        """A framework upgrade has to rename the payload.

        The digest is taken over the composed stylesheet, which contains the
        framework's own sheets, so changing one of them changes the name and
        no cache can serve the previous payload against the new markup.
        """
        from selfblog.chrome import chrome_asset_rel, chrome_css

        css = chrome_css("tinymoon")
        before = chrome_asset_rel("tinymoon", css)
        after = chrome_asset_rel("tinymoon", css + "\n/* framework moved */")
        assert before != after

    def test_the_payload_is_written_beside_the_stylesheet(
        self, tmp_path,
    ) -> None:
        from selfblog.chrome import write_chrome_assets

        assets = write_chrome_assets(str(tmp_path), ["tinymoon"])
        sheet = os.path.join(tmp_path, *assets["tinymoon"].split("/"))
        assert os.path.isfile(sheet)
        payload_root = os.path.dirname(os.path.dirname(sheet))
        assert os.path.isdir(os.path.join(payload_root, "fonts"))

    def test_a_superseded_payload_is_pruned_whole(self, tmp_path) -> None:
        """An old directory is as stale as an old file, and as heavy."""
        from selfblog.chrome import CHROME_DIR, write_chrome_assets

        stale = os.path.join(tmp_path, CHROME_DIR, "tinymoon-000000000000")
        os.makedirs(os.path.join(stale, "fonts"))
        with open(os.path.join(stale, "fonts", "old.woff2"), "wb") as f:
            f.write(b"stale")

        write_chrome_assets(str(tmp_path), ["tinymoon"])
        assert not os.path.exists(stale)

    def test_a_page_reference_to_the_payload_is_recognised(self) -> None:
        """Re-pointing has to find the reference it wrote last deploy."""
        from selfblog.chrome import chrome_asset_rel, chrome_css, is_chrome_reference

        rel = chrome_asset_rel("tinymoon", chrome_css("tinymoon"))
        assert is_chrome_reference("../" + rel)
        assert is_chrome_reference("css/style.css")


class TestTheDependencyIsDeclared:
    def test_the_engine_declares_a_floor_on_the_framework(self) -> None:
        """The wheel a consumer installs has to resolve a framework that
        ships the markup contract the emitters are written against."""
        import tomllib

        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(here, "selfdoc_core", "pyproject.toml"), "rb") as f:
            manifest = tomllib.load(f)
        declared = [
            d for d in manifest["project"]["dependencies"]
            if d.split(">")[0].split("=")[0].strip() == "tinymoon"
        ]
        assert declared, "selfdoc-core does not depend on tinymoon"
        assert ">=0.10.0" in declared[0], declared[0]
        assert "<" not in declared[0], "upper bounds are banned"

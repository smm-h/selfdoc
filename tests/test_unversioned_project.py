"""A project that declares it has no public version.

A portfolio or personal site ships no artifact, so there is no version for
a reader to pick, compare or be told about.  Before this, the required
``versions`` array forced such a site to state one anyway, and ``selfdoc
init`` wrote ``0.1.0`` into the file -- a number the project had never
released, rendered as a badge in the topbar and offered as a search filter.

The remedy is a declaration, not a guess: ``"unversioned": true`` says the
project has no public version, and everything version-shaped is omitted.
"""

import json

import pytest

from selfdoc_core.config import ConfigError, validate_config

BASE_URL = "https://example.com"
AUTHOR_NAME = "Test Author"
AUTHOR_URL = "https://author.example"


def _config(**overrides):
    config = {
        "base_url": BASE_URL,
        "author": {"name": AUTHOR_NAME, "url": AUTHOR_URL},
        "docs": "docs/",
        "output": "docs/_build/",
        "locales": [{"code": "en", "label": "English", "default": True}],
        "search_engine": "pagefind",
    }
    config.update(overrides)
    return config


# -- the declaration ----------------------------------------------------------


class TestTheDeclaration:
    def test_an_unversioned_project_needs_no_versions_array(self):
        config = validate_config(_config(unversioned=True))
        assert config["unversioned"] is True

    def test_the_declaration_resolves_to_one_anonymous_version(self):
        """Build machinery reads one version, whose string is empty.

        The empty string is what every version-shaped emitter already
        treats as "there is none": no badge, no facet, no picker, and no
        version segment in any address.
        """
        config = validate_config(_config(unversioned=True))
        assert config["versions"] == [{"version": ""}]

    def test_declaring_both_is_refused(self):
        with pytest.raises(ConfigError, match="unversioned"):
            validate_config(_config(
                unversioned=True, versions=[{"version": "1.0.0"}],
            ))

    def test_a_project_that_declares_source_may_not_declare_it(self):
        """Code is the thing that gets released, so it carries a version."""
        with pytest.raises(ConfigError, match="unversioned"):
            validate_config(_config(
                unversioned=True,
                source=[{"path": "pkg", "language": "python"}],
            ))

    def test_unversioned_false_is_not_a_declaration(self):
        """Declaring it false synthesizes nothing; versions stays required."""
        config = validate_config(_config(unversioned=False))
        assert config["versions"] is None

    def test_a_versioned_project_is_untouched(self):
        config = validate_config(_config(versions=[{"version": "1.2.3"}]))
        assert config["versions"] == [{"version": "1.2.3"}]
        assert config.get("unversioned") is not True


# -- what the built pages carry ------------------------------------------------


def _site(tmp_path, config):
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "index.md").write_text(
        "---\ntitle: Home\ndescription: The front page of a small site.\n---\n"
        "\n# Home\n\nA page.\n"
    )
    (tmp_path / "selfdoc.json").write_text(json.dumps(config) + "\n")
    return tmp_path


@pytest.fixture()
def unversioned_site(tmp_path):
    return _site(tmp_path, _config(unversioned=True))


@pytest.fixture()
def versioned_site(tmp_path):
    return _site(tmp_path, _config(versions=[{"version": "1.2.3"}]))


def _build_index(project_dir):
    from selfdoc.build import build
    from selfdoc.config import load_config

    build(str(project_dir), config=load_config(str(project_dir)))
    return (project_dir / "docs" / "_build" / "index.html").read_text()


class TestBuiltPages:
    def test_no_version_badge(self, unversioned_site):
        # The class appears in the stylesheet either way; what must be absent
        # is an element wearing it.
        assert 'class="version-badge"' not in _build_index(unversioned_site)

    def test_no_version_search_facet(self, unversioned_site):
        assert 'data-pagefind-filter="version:' not in _build_index(
            unversioned_site
        )

    def test_no_version_picker(self, unversioned_site):
        assert 'class="version-picker"' not in _build_index(unversioned_site)

    def test_a_versioned_project_still_carries_all_three(self, versioned_site):
        html = _build_index(versioned_site)
        assert 'class="version-badge">v1.2.3<' in html
        assert 'data-pagefind-filter="version:1.2.3"' in html


# -- what init writes ----------------------------------------------------------


@pytest.fixture()
def codeless_dir(tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "about.md").write_text(
        "---\ntitle: About\ndescription: A page with no code behind it.\n---\n"
        "\n# About\n\nText.\n"
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture()
def versionless_code_dir(tmp_path, monkeypatch):
    """A Python project whose manifest states no version."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "testproj"\n'
    )
    pkg = tmp_path / "testproj"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('"""Test package."""\n')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _init():
    from selfdoc.cli import _cmd_init

    _cmd_init(None, base_url=BASE_URL, author_name=AUTHOR_NAME,
              author_url=AUTHOR_URL, auto_commit=False)


class TestInit:
    def test_codeless_init_declares_unversionedness(self, codeless_dir):
        _init()
        raw = json.loads((codeless_dir / "selfdoc.json").read_text())
        assert raw["unversioned"] is True
        assert "versions" not in raw

    def test_codeless_init_writes_no_placeholder_version(self, codeless_dir):
        _init()
        assert "0.1.0" not in (codeless_dir / "selfdoc.json").read_text()

    def test_the_emitted_config_loads_and_builds(self, codeless_dir):
        from selfdoc.build import build

        _init()
        build(".")
        out = codeless_dir / "docs" / "_build" / "index.html"
        assert out.exists()
        assert 'class="version-badge"' not in out.read_text()

    def test_a_code_project_with_no_declared_version_is_refused(
        self, versionless_code_dir,
    ):
        """No invented number, and no silent unversioned declaration either."""
        with pytest.raises(SystemExit):
            _init()
        assert not (versionless_code_dir / "selfdoc.json").exists()

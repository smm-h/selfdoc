"""The declared author block, and the Person it puts in every page's JSON-LD.

Structured data names who wrote a page.  Before the author block was
required, an absent one made the emitters invent an Organization named after
the project directory -- a legal entity nobody had declared, minted once per
project.  The block is now required and the invention is gone: one Person,
declared in selfdoc.json, is what every emitter reads.
"""

import json
import os
import re

import pytest

from selfdoc.config import ConfigError, load_config
from selfdoc_core.html import _render_seo_tags

AUTHOR = {
    "name": "Jane Doe",
    "url": "https://jane.example",
    "same_as": ["https://github.com/jane", "https://example.org/@jane"],
}


def _write_config(directory, data):
    path = os.path.join(str(directory), "selfdoc.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _base_config(**overrides):
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "search_engine": "pagefind",
        "author": dict(AUTHOR),
    }
    config.update(overrides)
    return config


# -- the config block ---------------------------------------------------------


class TestAuthorRequired:
    def test_absent_author_is_a_hard_error_naming_the_key(self, tmp_path):
        config = _base_config()
        del config["author"]
        _write_config(tmp_path, config)
        with pytest.raises(ConfigError, match="author"):
            load_config(str(tmp_path))

    def test_the_refusal_says_what_to_declare(self, tmp_path):
        config = _base_config()
        del config["author"]
        _write_config(tmp_path, config)
        with pytest.raises(ConfigError) as exc:
            load_config(str(tmp_path))
        message = str(exc.value)
        assert "name" in message
        assert "url" in message

    def test_author_without_url_is_refused(self, tmp_path):
        _write_config(tmp_path, _base_config(author={"name": "Jane Doe"}))
        with pytest.raises(ConfigError, match="'author.url' is required"):
            load_config(str(tmp_path))

    def test_author_without_name_is_refused(self, tmp_path):
        _write_config(
            tmp_path, _base_config(author={"url": "https://jane.example"}),
        )
        with pytest.raises(ConfigError, match="'author.name' is required"):
            load_config(str(tmp_path))

    def test_unknown_author_key_is_refused(self, tmp_path):
        _write_config(tmp_path, _base_config(author={
            "name": "Jane Doe", "url": "https://jane.example", "type": "Person",
        }))
        with pytest.raises(ConfigError, match="invalid author key 'type'"):
            load_config(str(tmp_path))

    def test_same_as_is_optional(self, tmp_path):
        _write_config(tmp_path, _base_config(author={
            "name": "Jane Doe", "url": "https://jane.example",
        }))
        cfg = load_config(str(tmp_path))
        assert cfg["author"] == {
            "name": "Jane Doe", "url": "https://jane.example",
        }

    def test_same_as_loads_in_declared_order(self, tmp_path):
        _write_config(tmp_path, _base_config())
        cfg = load_config(str(tmp_path))
        assert cfg["author"]["same_as"] == [
            "https://github.com/jane", "https://example.org/@jane",
        ]

    def test_same_as_must_hold_strings(self, tmp_path):
        _write_config(tmp_path, _base_config(author={
            "name": "Jane Doe", "url": "https://jane.example",
            "same_as": [{"url": "https://github.com/jane"}],
        }))
        with pytest.raises(ConfigError):
            load_config(str(tmp_path))


# -- the emitted structured data ----------------------------------------------


def _ld_objects(html_text):
    return [
        json.loads(block)
        for block in re.findall(
            r'<script type="application/ld\+json">\n(.*?)\n</script>',
            html_text, re.DOTALL,
        )
    ]


def _render(page_path="guide.html", author=AUTHOR, page_type="guide"):
    seo_tags, _security = _render_seo_tags(
        title="A Page",
        base_url="https://example.com",
        page_path=page_path,
        description="A description.",
        body_html="<p>Body</p>",
        author=author,
        project_name="mypackage",
        repo=None,
        date_published=None,
        date_modified=None,
        lang="en",
        breadcrumbs=None,
        schema=None,
        twitter_site=None,
        deploy_target=None,
        page_type=page_type,
    )
    return seo_tags


class TestPersonEmission:
    def test_page_author_is_the_declared_person(self):
        objs = _ld_objects(_render())
        article = next(o for o in objs if o.get("headline"))
        assert article["author"] == {
            "@type": "Person",
            "name": "Jane Doe",
            "url": "https://jane.example",
            "sameAs": ["https://github.com/jane", "https://example.org/@jane"],
        }

    def test_publisher_is_the_same_person(self):
        objs = _ld_objects(_render())
        article = next(o for o in objs if o.get("headline"))
        assert article["publisher"] == article["author"]

    def test_homepage_entity_is_the_declared_person(self):
        objs = _ld_objects(_render(page_path="index.html"))
        person = next(o for o in objs if o.get("@type") == "Person")
        assert person["name"] == "Jane Doe"
        assert person["url"] == "https://jane.example"
        assert person["sameAs"] == [
            "https://github.com/jane", "https://example.org/@jane",
        ]

    def test_no_organization_is_ever_minted(self):
        for page_path in ("index.html", "guide.html"):
            rendered = _render(page_path=page_path)
            assert "Organization" not in rendered
            objs = _ld_objects(rendered)
            for obj in objs:
                assert "mypackage" not in json.dumps(obj.get("author", {}))
                assert "mypackage" not in json.dumps(obj.get("publisher", {}))

    def test_missing_author_refuses_rather_than_inventing_one(self):
        with pytest.raises(ValueError, match="author"):
            _render(author=None)

    def test_author_without_url_refuses(self):
        with pytest.raises(ValueError, match="author"):
            _render(author={"name": "Jane Doe"})


class TestNoOrganizationFallbackInSource:
    """The minting path is deleted, not merely unreachable."""

    def test_no_module_emits_an_organization(self):
        """No emitter names the type at all -- the site's identity is a Person."""
        import selfblog.listing as listing_module
        import selfdoc_core.build as build_module
        import selfdoc_core.html as html_module

        for module in (html_module, build_module, listing_module):
            with open(module.__file__, "r", encoding="utf-8") as f:
                source = f.read()
            assert "Organization" not in source, module.__name__

    def test_the_only_person_builder_is_the_identity_module(self):
        """Every Person entity is built by one function, from one block."""
        import selfdoc_core.html as html_module

        with open(html_module.__file__, "r", encoding="utf-8") as f:
            source = f.read()
        assert '"Person"' not in source
        assert "person_entity(" in source

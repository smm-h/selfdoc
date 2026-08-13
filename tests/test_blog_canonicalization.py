"""Tests for the canonical blog URL topology.

The blog is served from exactly one canonical URL (``<docs_base>/blog/``).
Every other way of reaching it -- the retired blog subdomain, or any other
host bound to the same Pages project -- must 301 there in a single hop, and
the shared index pages must declare the canonical URL.
"""

import json
import os

import pytest

from selfblog.assembly import generate_worker_js
from selfblog.cli import _cmd_assembly_generate_shared
from selfblog.shared import wrap_shared_page

CANONICAL_BASE = "https://docs.example.com"
LEGACY_BLOG_HOST = "blog.example.com"


def _write_manifest(manifests_dir, slug="alpha"):
    manifest = {
        "schema_version": 1,
        "name": slug.title(),
        "slug": slug,
        "version": "1.0.0",
        "description": "",
        "language": "python",
        "base_url": f"{CANONICAL_BASE}/{slug}",
        "author": {"name": "Test Author", "url": "https://author.example"},
        "pages": [{"path": "index.md", "title": "Home"}],
        "posts": [],
        "last_gen": "2024-01-01T00:00:00+00:00",
    }
    with open(os.path.join(manifests_dir, f"{slug}.json"), "w") as f:
        json.dump(manifest, f)


# -- generate_worker_js -------------------------------------------------------


def test_worker_targets_the_canonical_base():
    js = generate_worker_js(CANONICAL_BASE, LEGACY_BLOG_HOST)
    assert f'const CANONICAL_BASE = "{CANONICAL_BASE}";' in js


def test_worker_legacy_host_redirect_is_single_hop():
    """The retired subdomain goes straight to the canonical blog URL."""
    js = generate_worker_js(CANONICAL_BASE, LEGACY_BLOG_HOST)
    assert f'["{LEGACY_BLOG_HOST}", "/blog"]' in js
    # No intermediate apex hop.
    assert "smmh.dev" not in js


def test_worker_consolidates_every_path_on_non_canonical_hosts():
    """One hostname serves content; every other host 301s to it."""
    js = generate_worker_js(CANONICAL_BASE, LEGACY_BLOG_HOST)
    assert "url.hostname !== CANONICAL_HOST" in js
    assert "if (offHost) return CANONICAL_BASE + pathname + url.search;" in js
    # Not just the blog: the rule is about hosts, not about one path.
    assert 'url.pathname.startsWith("/blog/")' not in js


def test_worker_omits_legacy_prefix_when_no_legacy_host():
    js = generate_worker_js(CANONICAL_BASE, "")
    assert "HOST_PREFIXES = new Map([])" in js
    assert "url.hostname !== CANONICAL_HOST" in js


def test_worker_still_serves_assets():
    js = generate_worker_js(CANONICAL_BASE, LEGACY_BLOG_HOST)
    assert "env.ASSETS.fetch(request)" in js


def test_worker_requires_a_canonical_base():
    """No implicit default for the redirect target."""
    with pytest.raises(ValueError) as excinfo:
        generate_worker_js("", LEGACY_BLOG_HOST)
    assert "docs_base" in str(excinfo.value)


def test_worker_strips_trailing_slash_from_canonical_base():
    js = generate_worker_js(CANONICAL_BASE + "/", LEGACY_BLOG_HOST)
    assert f'const CANONICAL_BASE = "{CANONICAL_BASE}";' in js


# -- rel=canonical ------------------------------------------------------------


def test_wrap_shared_page_emits_canonical_link():
    html = wrap_shared_page(
        "Blog", "<p>x</p>", canonical_url=f"{CANONICAL_BASE}/blog/",
        css_url="../_chrome/x.css", search_prefix="../",
    )
    assert f'<link rel="canonical" href="{CANONICAL_BASE}/blog/">' in html


def test_wrap_shared_page_omits_canonical_when_empty():
    html = wrap_shared_page(
        "Blog", "<p>x</p>", css_url="../_chrome/x.css", search_prefix="../",
    )
    assert 'rel="canonical"' not in html


def test_wrap_shared_page_escapes_canonical_url():
    html = wrap_shared_page(
        "Blog", "<p>x</p>", canonical_url='https://x/"><script>',
        css_url="../_chrome/x.css", search_prefix="../",
    )
    assert "<script>" not in html.split("<body>")[0]


# -- generate-shared end to end ----------------------------------------------


def _run_generate_shared(tmp_path, **kwargs):
    site_dir = str(tmp_path / "site")
    manifests_dir = str(tmp_path / "manifests")
    os.makedirs(site_dir, exist_ok=True)
    os.makedirs(manifests_dir, exist_ok=True)
    _write_manifest(manifests_dir)
    _cmd_assembly_generate_shared(
        None, site_dir=site_dir, manifests_dir=manifests_dir,
        canonical_base=CANONICAL_BASE, **kwargs,
    )
    return site_dir


def test_generate_shared_requires_canonical_base(tmp_path):
    site_dir = str(tmp_path / "site")
    manifests_dir = str(tmp_path / "manifests")
    os.makedirs(site_dir)
    os.makedirs(manifests_dir)
    with pytest.raises(SystemExit):
        _cmd_assembly_generate_shared(
            None, site_dir=site_dir, manifests_dir=manifests_dir,
        )


def test_generate_shared_blog_index_declares_canonical(tmp_path):
    site_dir = _run_generate_shared(tmp_path)
    with open(os.path.join(site_dir, "blog", "index.html")) as f:
        html = f.read()
    assert f'<link rel="canonical" href="{CANONICAL_BASE}/blog/">' in html


def test_generate_shared_writes_no_root_index(tmp_path):
    """The site root belongs to the home project, never to the generator."""
    site_dir = _run_generate_shared(tmp_path)
    assert not os.path.exists(os.path.join(site_dir, "index.html"))


def test_generate_shared_projects_page_declares_canonical(tmp_path):
    """The listing has one fixed address, and it names it."""
    site_dir = _run_generate_shared(tmp_path)
    with open(os.path.join(site_dir, "projects", "index.html")) as f:
        html = f.read()
    assert f'<link rel="canonical" href="{CANONICAL_BASE}/projects/">' in html


def test_generate_shared_worker_uses_canonical_base(tmp_path):
    site_dir = _run_generate_shared(tmp_path, legacy_blog_host=LEGACY_BLOG_HOST)
    with open(os.path.join(site_dir, "_worker.js")) as f:
        js = f.read()
    assert f'const CANONICAL_BASE = "{CANONICAL_BASE}";' in js
    assert LEGACY_BLOG_HOST in js


# -- posts_base semantics -----------------------------------------------------


def test_posts_base_is_no_longer_a_url_builder_input():
    """The dead TopologyURLBuilder posts_base parameter is gone."""
    from selfdoc_core.urls import TopologyURLBuilder

    with pytest.raises(TypeError):
        TopologyURLBuilder(
            "https://docs.example.com", "selfdoc",
            posts_base="https://blog.example.com",
        )


def test_posts_url_var_resolves_posts_base():
    """topology.posts_url is the surviving posts_base consumer."""
    from selfdoc_core.content import resolve_var

    config = {"topology": {"posts_base": f"{CANONICAL_BASE}/blog"}}
    assert resolve_var({"key": "topology.posts_url"}, config, ".") == \
        f"{CANONICAL_BASE}/blog"


def _own_topology():
    from selfdoc_core.config import load_config

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return load_config(root)["topology"]


def test_own_config_posts_base_lives_under_docs_base():
    """This repo's own config encodes the canonical blog URL, not a subdomain."""
    topology = _own_topology()
    assert topology["posts_base"].startswith(topology["docs_base"] + "/")
    assert topology["posts_base"].endswith("/blog")


def test_own_config_names_the_apex_as_canonical():
    """The assembly's canonical base is the apex, not the docs subdomain.

    This repo's ``topology.docs_base`` is what the generated deploy
    workflow passes as ``--canonical-base``, so it is the one declaration
    of which of the site's hostnames serves content. Every other host --
    the docs subdomain, the retired blog subdomain, the provider's preview
    domain -- 301s onto it.
    """
    docs_base = _own_topology()["docs_base"]
    assert docs_base == "https://smmh.dev"


def test_own_config_addresses_sibling_projects_on_the_canonical_host():
    """Cross-project links point at the host that serves, not at a redirect."""
    topology = _own_topology()
    for name, url in (topology.get("projects") or {}).items():
        assert url.startswith(topology["docs_base"] + "/"), name

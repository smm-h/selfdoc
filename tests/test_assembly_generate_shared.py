"""Tests for selfdoc assembly generate-shared command."""

import json
import os

import pytest

from selfblog.cli import _cmd_assembly_generate_shared

# Absolute canonical origin of the assembly site.  Required by
# generate-shared: it targets the redirect worker and rel=canonical.
CANONICAL_BASE = "https://docs.example.com"


def _write_manifest(manifests_dir, name, slug, version, description="",
                    pages=None, posts=None):
    """Write a single manifest JSON file to the manifests directory."""
    manifest = {
        "schema_version": 1,
        "name": name,
        "slug": slug,
        "version": version,
        "description": description,
        "language": "python",
        "base_url": f"https://docs.example.com/{slug}",
        "pages": pages if pages is not None else [{"path": "index.md", "title": "Home"}],
        "posts": posts or [],
        "last_gen": "2024-01-01T00:00:00+00:00",
    }
    fpath = os.path.join(manifests_dir, f"{slug}.json")
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    return manifest


# -- Two manifests: all 6 output files created --------------------------------


def test_generate_shared_creates_all_files(tmp_path):
    """With 2 manifests, all 7 output files are created."""
    site_dir = str(tmp_path / "site")
    manifests_dir = str(tmp_path / "manifests")
    os.makedirs(site_dir)
    os.makedirs(manifests_dir)

    _write_manifest(manifests_dir, "Alpha", "alpha", "1.0.0", "First project")
    _write_manifest(manifests_dir, "Beta", "beta", "2.0.0", "Second project",
                    posts=[{"title": "Hello", "slug": "hello", "date": "2024-06-01"}])

    _cmd_assembly_generate_shared(
        None, site_dir=site_dir, manifests_dir=manifests_dir,
        canonical_base=CANONICAL_BASE,
    )

    # The listing is generated at its own fixed address; the site root is
    # the home project's page and is grafted, never generated here.
    assert os.path.isfile(os.path.join(site_dir, "projects", "index.html"))
    assert not os.path.exists(os.path.join(site_dir, "index.html"))
    assert os.path.isfile(os.path.join(site_dir, "blog", "index.html"))
    assert os.path.isfile(os.path.join(site_dir, "nav.json"))
    assert os.path.isfile(os.path.join(site_dir, "feed.xml"))
    assert os.path.isfile(os.path.join(site_dir, "sitemap.xml"))
    assert os.path.isfile(os.path.join(site_dir, "_headers"))
    assert os.path.isfile(os.path.join(site_dir, "_worker.js"))


# -- index.html is a complete HTML page, not a fragment -----------------------


def test_the_listing_page_is_a_complete_page(tmp_path):
    """projects/index.html has DOCTYPE, <html>, <head>, <body>."""
    site_dir = str(tmp_path / "site")
    manifests_dir = str(tmp_path / "manifests")
    os.makedirs(site_dir)
    os.makedirs(manifests_dir)

    _write_manifest(manifests_dir, "Proj", "proj", "1.0.0")

    _cmd_assembly_generate_shared(
        None, site_dir=site_dir, manifests_dir=manifests_dir,
        canonical_base=CANONICAL_BASE,
    )

    with open(os.path.join(site_dir, "projects", "index.html"), "r",
              encoding="utf-8") as f:
        content = f.read()

    assert "<!DOCTYPE html>" in content
    assert "<html" in content
    assert "<head>" in content
    assert "<body>" in content


# -- blog/index.html is also a complete page ----------------------------------


def test_blog_index_html_is_complete_page(tmp_path):
    """blog/index.html has DOCTYPE, <html>, <head>, <body>."""
    site_dir = str(tmp_path / "site")
    manifests_dir = str(tmp_path / "manifests")
    os.makedirs(site_dir)
    os.makedirs(manifests_dir)

    _write_manifest(manifests_dir, "Proj", "proj", "1.0.0",
                    posts=[{"title": "Post", "slug": "post", "date": "2024-01-01"}])

    _cmd_assembly_generate_shared(
        None, site_dir=site_dir, manifests_dir=manifests_dir,
        canonical_base=CANONICAL_BASE,
    )

    with open(os.path.join(site_dir, "blog", "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert "<!DOCTYPE html>" in content
    assert "<html" in content
    assert "<head>" in content
    assert "<body>" in content


# -- _headers file contains security headers ----------------------------------


def test_headers_file_contains_security_headers(tmp_path):
    """_headers file has X-Frame-Options, X-Content-Type-Options, Referrer-Policy."""
    site_dir = str(tmp_path / "site")
    manifests_dir = str(tmp_path / "manifests")
    os.makedirs(site_dir)
    os.makedirs(manifests_dir)

    _write_manifest(manifests_dir, "Proj", "proj", "1.0.0")

    _cmd_assembly_generate_shared(
        None, site_dir=site_dir, manifests_dir=manifests_dir,
        canonical_base=CANONICAL_BASE,
    )

    with open(os.path.join(site_dir, "_headers"), "r", encoding="utf-8") as f:
        content = f.read()

    assert "X-Frame-Options: DENY" in content
    assert "X-Content-Type-Options: nosniff" in content
    assert "Referrer-Policy: strict-origin-when-cross-origin" in content


# -- Empty manifests dir: still produces valid outputs ------------------------


def test_empty_manifests_dir_produces_valid_outputs(tmp_path):
    """With no manifests, all 6 files are still created with valid content."""
    site_dir = str(tmp_path / "site")
    manifests_dir = str(tmp_path / "manifests")
    os.makedirs(site_dir)
    os.makedirs(manifests_dir)

    _cmd_assembly_generate_shared(
        None, site_dir=site_dir, manifests_dir=manifests_dir,
        canonical_base=CANONICAL_BASE,
    )

    # All files exist
    # The listing is generated at its own fixed address; the site root is
    # the home project's page and is grafted, never generated here.
    assert os.path.isfile(os.path.join(site_dir, "projects", "index.html"))
    assert not os.path.exists(os.path.join(site_dir, "index.html"))
    assert os.path.isfile(os.path.join(site_dir, "blog", "index.html"))
    assert os.path.isfile(os.path.join(site_dir, "nav.json"))
    assert os.path.isfile(os.path.join(site_dir, "feed.xml"))
    assert os.path.isfile(os.path.join(site_dir, "sitemap.xml"))
    assert os.path.isfile(os.path.join(site_dir, "_headers"))

    # the listing is still a complete page
    with open(os.path.join(site_dir, "projects", "index.html"), "r",
              encoding="utf-8") as f:
        content = f.read()
    assert "<!DOCTYPE html>" in content


# -- nav.json is valid JSON ---------------------------------------------------


def test_nav_json_is_valid_json(tmp_path):
    """nav.json parses as valid JSON with expected structure."""
    site_dir = str(tmp_path / "site")
    manifests_dir = str(tmp_path / "manifests")
    os.makedirs(site_dir)
    os.makedirs(manifests_dir)

    _write_manifest(manifests_dir, "Alpha", "alpha", "1.0.0")

    _cmd_assembly_generate_shared(
        None, site_dir=site_dir, manifests_dir=manifests_dir,
        canonical_base=CANONICAL_BASE,
    )

    with open(os.path.join(site_dir, "nav.json"), "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "projects" in data
    assert isinstance(data["projects"], list)


# -- feed.xml contains Atom namespace -----------------------------------------


def test_feed_xml_contains_atom_namespace(tmp_path):
    """feed.xml contains the Atom XML namespace."""
    site_dir = str(tmp_path / "site")
    manifests_dir = str(tmp_path / "manifests")
    os.makedirs(site_dir)
    os.makedirs(manifests_dir)

    _write_manifest(manifests_dir, "Proj", "proj", "1.0.0",
                    posts=[{"title": "Test", "slug": "test", "date": "2024-01-01"}])

    _cmd_assembly_generate_shared(
        None, site_dir=site_dir, manifests_dir=manifests_dir,
        canonical_base=CANONICAL_BASE,
    )

    with open(os.path.join(site_dir, "feed.xml"), "r", encoding="utf-8") as f:
        content = f.read()

    assert 'xmlns="http://www.w3.org/2005/Atom"' in content


# -- sitemap.xml contains urlset namespace ------------------------------------


def test_sitemap_xml_contains_urlset_namespace(tmp_path):
    """sitemap.xml contains the sitemaps.org urlset namespace."""
    site_dir = str(tmp_path / "site")
    manifests_dir = str(tmp_path / "manifests")
    os.makedirs(site_dir)
    os.makedirs(manifests_dir)

    _write_manifest(manifests_dir, "Proj", "proj", "1.0.0",
                    pages=[{"path": "guide.md", "title": "Guide"}])

    _cmd_assembly_generate_shared(
        None, site_dir=site_dir, manifests_dir=manifests_dir,
        canonical_base=CANONICAL_BASE,
    )

    with open(os.path.join(site_dir, "sitemap.xml"), "r", encoding="utf-8") as f:
        content = f.read()

    assert 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"' in content


# -- Post overlay: replaces base posts -----------------------------------


def _write_post_overlay(manifests_dir, slug, posts):
    """Write a post overlay manifest (*-posts.json) to the manifests directory."""
    overlay = {
        "schema_version": 1,
        "name": slug,
        "slug": slug,
        "version": "1.0.0",
        "description": "",
        "language": "python",
        "base_url": f"https://docs.example.com/{slug}",
        "pages": [],
        "posts": posts,
        "last_gen": "2024-01-01T00:00:00+00:00",
    }
    fpath = os.path.join(manifests_dir, f"{slug}-posts.json")
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(overlay, f)
    return overlay


def test_overlay_replaces_base_posts(tmp_path):
    """A post overlay replaces the base manifest's posts list."""
    site_dir = str(tmp_path / "site")
    manifests_dir = str(tmp_path / "manifests")
    os.makedirs(site_dir)
    os.makedirs(manifests_dir)

    base_posts = [
        {"title": "Old Post", "slug": "old-post", "date": "2024-01-01"},
    ]
    _write_manifest(manifests_dir, "Alpha", "alpha", "1.0.0",
                    posts=base_posts)

    overlay_posts = [
        {"title": "New Post", "slug": "new-post", "date": "2024-06-01"},
        {"title": "Another", "slug": "another", "date": "2024-06-02"},
    ]
    _write_post_overlay(manifests_dir, "alpha", overlay_posts)

    _cmd_assembly_generate_shared(
        None, site_dir=site_dir, manifests_dir=manifests_dir,
        canonical_base=CANONICAL_BASE,
    )

    # Blog page should contain the overlay posts, not the old ones
    with open(os.path.join(site_dir, "blog", "index.html"), "r",
              encoding="utf-8") as f:
        blog_html = f.read()

    assert "New Post" in blog_html
    assert "Another" in blog_html
    assert "Old Post" not in blog_html


def test_overlay_deleted_post_disappears(tmp_path):
    """An overlay with fewer posts causes the removed post to disappear."""
    site_dir = str(tmp_path / "site")
    manifests_dir = str(tmp_path / "manifests")
    os.makedirs(site_dir)
    os.makedirs(manifests_dir)

    base_posts = [
        {"title": "Keep Me", "slug": "keep-me", "date": "2024-01-01"},
        {"title": "Remove Me", "slug": "remove-me", "date": "2024-01-02"},
    ]
    _write_manifest(manifests_dir, "Beta", "beta", "1.0.0", posts=base_posts)

    # Overlay only has one post -- the removed post should disappear
    overlay_posts = [
        {"title": "Keep Me", "slug": "keep-me", "date": "2024-01-01"},
    ]
    _write_post_overlay(manifests_dir, "beta", overlay_posts)

    _cmd_assembly_generate_shared(
        None, site_dir=site_dir, manifests_dir=manifests_dir,
        canonical_base=CANONICAL_BASE,
    )

    with open(os.path.join(site_dir, "blog", "index.html"), "r",
              encoding="utf-8") as f:
        blog_html = f.read()

    assert "Keep Me" in blog_html
    assert "Remove Me" not in blog_html


def test_no_overlay_uses_base_posts(tmp_path):
    """Without an overlay, the base manifest's posts are used unchanged."""
    site_dir = str(tmp_path / "site")
    manifests_dir = str(tmp_path / "manifests")
    os.makedirs(site_dir)
    os.makedirs(manifests_dir)

    base_posts = [
        {"title": "Base Post", "slug": "base-post", "date": "2024-03-01"},
    ]
    _write_manifest(manifests_dir, "Gamma", "gamma", "1.0.0",
                    posts=base_posts)

    _cmd_assembly_generate_shared(
        None, site_dir=site_dir, manifests_dir=manifests_dir,
        canonical_base=CANONICAL_BASE,
    )

    with open(os.path.join(site_dir, "blog", "index.html"), "r",
              encoding="utf-8") as f:
        blog_html = f.read()

    assert "Base Post" in blog_html


def test_overlay_unknown_slug_ignored(tmp_path):
    """An overlay for an unknown slug is silently ignored."""
    site_dir = str(tmp_path / "site")
    manifests_dir = str(tmp_path / "manifests")
    os.makedirs(site_dir)
    os.makedirs(manifests_dir)

    _write_manifest(manifests_dir, "Delta", "delta", "1.0.0",
                    posts=[{"title": "Delta Post", "slug": "dp",
                            "date": "2024-04-01"}])

    # Overlay for a slug that has no matching base manifest
    _write_post_overlay(manifests_dir, "nonexistent",
                        [{"title": "Ghost", "slug": "ghost",
                          "date": "2024-05-01"}])

    _cmd_assembly_generate_shared(
        None, site_dir=site_dir, manifests_dir=manifests_dir,
        canonical_base=CANONICAL_BASE,
    )

    with open(os.path.join(site_dir, "blog", "index.html"), "r",
              encoding="utf-8") as f:
        blog_html = f.read()

    # Original delta post is unchanged
    assert "Delta Post" in blog_html
    # Ghost from the unmatched overlay should not appear
    assert "Ghost" not in blog_html


# -- Blog URLs are correct (regression for slug-as-hostname bug) -------------


def test_blog_urls_not_broken_without_docs_base(tmp_path):
    """Without --docs-base, blog links are root-relative, not protocol-only broken URLs.

    Regression test: previously, docs_base was derived from manifest base_url by
    stripping the last path segment. For URLs like 'https://selfdoc.smmh.dev'
    (no path segment), rsplit('/') produced 'https:' as docs_base, resulting in
    href="https:/blog/..." which browsers normalize to
    href="https://blog/..." (the first segment treated as a hostname).
    """
    site_dir = str(tmp_path / "site")
    manifests_dir = str(tmp_path / "manifests")
    os.makedirs(site_dir)
    os.makedirs(manifests_dir)

    # Manifest with a per-project base_url (no path segment, just hostname)
    manifest = {
        "schema_version": 1,
        "name": "rlsbl",
        "slug": "rlsbl",
        "version": "1.0.0",
        "description": "Release tool",
        "language": "python",
        "base_url": "https://rlsbl.smmh.dev",
        "pages": [{"path": "index.md", "title": "Home"}],
        "posts": [{"title": "First Post", "slug": "first", "date": "2024-01-01"}],
        "last_gen": "2024-01-01T00:00:00+00:00",
    }
    fpath = os.path.join(manifests_dir, "rlsbl.json")
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    _cmd_assembly_generate_shared(
        None, site_dir=site_dir, manifests_dir=manifests_dir,
        canonical_base=CANONICAL_BASE,
    )

    with open(os.path.join(site_dir, "blog", "index.html"), "r",
              encoding="utf-8") as f:
        blog_html = f.read()

    # The URL must be root-relative (no docs_base provided)
    assert 'href="/blog/first/"' in blog_html
    # Must NOT have broken protocol-only URL
    assert "https:/blog" not in blog_html
    assert "://blog" not in blog_html


def test_blog_urls_correct_with_docs_base(tmp_path):
    """With --docs-base, blog links use the provided base URL."""
    site_dir = str(tmp_path / "site")
    manifests_dir = str(tmp_path / "manifests")
    os.makedirs(site_dir)
    os.makedirs(manifests_dir)

    manifest = {
        "schema_version": 1,
        "name": "rlsbl",
        "slug": "rlsbl",
        "version": "1.0.0",
        "description": "Release tool",
        "language": "python",
        "base_url": "https://rlsbl.smmh.dev",
        "pages": [{"path": "index.md", "title": "Home"}],
        "posts": [{"title": "First Post", "slug": "first", "date": "2024-01-01"}],
        "last_gen": "2024-01-01T00:00:00+00:00",
    }
    fpath = os.path.join(manifests_dir, "rlsbl.json")
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    _cmd_assembly_generate_shared(
        None,
        site_dir=site_dir,
        manifests_dir=manifests_dir,
        docs_base="https://docs.smmh.dev",
        canonical_base=CANONICAL_BASE,
    )

    with open(os.path.join(site_dir, "blog", "index.html"), "r",
              encoding="utf-8") as f:
        blog_html = f.read()

    assert 'href="https://docs.smmh.dev/blog/first/"' in blog_html

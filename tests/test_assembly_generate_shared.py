"""Tests for selfdoc assembly generate-shared command."""

import json
import os

import pytest

from selfdoc.cli import _cmd_assembly_generate_shared


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
    """With 2 manifests, all 6 output files are created."""
    site_dir = str(tmp_path / "site")
    manifests_dir = str(tmp_path / "manifests")
    os.makedirs(site_dir)
    os.makedirs(manifests_dir)

    _write_manifest(manifests_dir, "Alpha", "alpha", "1.0.0", "First project")
    _write_manifest(manifests_dir, "Beta", "beta", "2.0.0", "Second project",
                    posts=[{"title": "Hello", "slug": "hello", "date": "2024-06-01"}])

    _cmd_assembly_generate_shared(site_dir=site_dir, manifests_dir=manifests_dir)

    assert os.path.isfile(os.path.join(site_dir, "index.html"))
    assert os.path.isfile(os.path.join(site_dir, "blog", "index.html"))
    assert os.path.isfile(os.path.join(site_dir, "nav.json"))
    assert os.path.isfile(os.path.join(site_dir, "feed.xml"))
    assert os.path.isfile(os.path.join(site_dir, "sitemap.xml"))
    assert os.path.isfile(os.path.join(site_dir, "_headers"))


# -- index.html is a complete HTML page, not a fragment -----------------------


def test_index_html_is_complete_page(tmp_path):
    """index.html has DOCTYPE, <html>, <head>, <body>."""
    site_dir = str(tmp_path / "site")
    manifests_dir = str(tmp_path / "manifests")
    os.makedirs(site_dir)
    os.makedirs(manifests_dir)

    _write_manifest(manifests_dir, "Proj", "proj", "1.0.0")

    _cmd_assembly_generate_shared(site_dir=site_dir, manifests_dir=manifests_dir)

    with open(os.path.join(site_dir, "index.html"), "r", encoding="utf-8") as f:
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

    _cmd_assembly_generate_shared(site_dir=site_dir, manifests_dir=manifests_dir)

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

    _cmd_assembly_generate_shared(site_dir=site_dir, manifests_dir=manifests_dir)

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

    _cmd_assembly_generate_shared(site_dir=site_dir, manifests_dir=manifests_dir)

    # All files exist
    assert os.path.isfile(os.path.join(site_dir, "index.html"))
    assert os.path.isfile(os.path.join(site_dir, "blog", "index.html"))
    assert os.path.isfile(os.path.join(site_dir, "nav.json"))
    assert os.path.isfile(os.path.join(site_dir, "feed.xml"))
    assert os.path.isfile(os.path.join(site_dir, "sitemap.xml"))
    assert os.path.isfile(os.path.join(site_dir, "_headers"))

    # index.html is still a complete page
    with open(os.path.join(site_dir, "index.html"), "r", encoding="utf-8") as f:
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

    _cmd_assembly_generate_shared(site_dir=site_dir, manifests_dir=manifests_dir)

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

    _cmd_assembly_generate_shared(site_dir=site_dir, manifests_dir=manifests_dir)

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

    _cmd_assembly_generate_shared(site_dir=site_dir, manifests_dir=manifests_dir)

    with open(os.path.join(site_dir, "sitemap.xml"), "r", encoding="utf-8") as f:
        content = f.read()

    assert 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"' in content

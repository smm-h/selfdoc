"""Monorepo unified site builder.

Orchestrates building a single documentation site from multiple
constituent projects plus a docs-site's own cross-cutting content.
Each constituent project is built using its own selfdoc.json; the
docs-site's config provides the unified orchestration via its
``unified`` section.
"""

import dataclasses
import json
import os
import re

from selfdoc_core.address import page_address
from selfdoc_core.build import (
    _check_reserved_paths,
    _check_unversioned_collisions,
    _cleanup_injected_posts,
    _compress_output,
    _extract_critical_css,
    _extract_version_content,
    _generate_auxiliary_files,
    _inject_posts_into_docs,
    _minify_css,
    _minify_html,
    _partition_pages,
    build_single,
)
from selfdoc_core.config import ConfigError, load_config
from selfdoc_core.html import (
    _escape_html,
    _html_path_to_url,
    _md_to_html_path,
    _slugify,
    generate_pygments_css,
    get_css,
)
from selfdoc_core.themes import get_theme_meta
from selfdoc_core.urls import SimpleURLBuilder

from selfdoc_core import effects


def _resolve_project_path(project_entry, docs_site_dir):
    """Resolve a constituent project's absolute path from its config entry.

    The ``path`` value in the unified config is relative to the docs-site
    directory (e.g. ``../core``).

    Returns the absolute project directory path.
    Raises ConfigError if the resolved path does not exist.
    """
    raw_path = project_entry["path"]
    abs_path = os.path.normpath(os.path.join(docs_site_dir, raw_path))
    if not os.path.isdir(abs_path):
        raise ConfigError(
            f"unified project path '{raw_path}' resolves to "
            f"'{abs_path}' which does not exist"
        )
    return abs_path


def _project_slug(project_entry):
    """Derive the URL slug for a constituent project.

    Uses the explicit ``slug`` field if set, otherwise the basename
    of the project path.
    """
    return (
        project_entry.get("slug")
        or os.path.basename(project_entry["path"].rstrip("/"))
    )


def _project_nav_title(project_entry):
    """Derive the navigation title for a constituent project.

    Uses the explicit ``nav_title`` field if set, otherwise titlecases
    the slug.
    """
    return (
        project_entry.get("nav_title")
        or _project_slug(project_entry).replace("-", " ").replace("_", " ").title()
    )


def _build_unified_nav(common_nav, projects_nav, config):
    """Merge navigation from common docs and constituent projects.

    Returns a flat nav_items list suitable for _render_nav:
    - Common (docs-site) pages first
    - Then one collapsible group per constituent project

    Args:
        common_nav: Nav items from the docs-site's own docs.
        projects_nav: List of (slug, nav_title, nav_items, url_prefix)
            tuples, one per constituent project.
        config: The docs-site's config dict.
    """
    merged = list(common_nav)
    for slug, nav_title, nav_items, url_prefix in projects_nav:
        # Wrap each project's nav as a collapsible group
        # Prefix each item's path with the project's output_subdir
        prefixed_items = []
        for item in nav_items:
            if "group" in item:
                # Nested group: prefix each sub-item's path
                prefixed_sub = []
                for sub in item["items"]:
                    prefixed_sub.append({
                        "label": sub["label"],
                        "path": f"{url_prefix}/{sub['path']}",
                        "md_path": sub.get("md_path", ""),
                    })
                prefixed_items.append({
                    "group": item["group"],
                    "slug": item.get("slug", ""),
                    "items": prefixed_sub,
                })
            else:
                prefixed_items.append({
                    "label": item["label"],
                    "path": f"{url_prefix}/{item['path']}",
                    "md_path": item.get("md_path", ""),
                })
        merged.append({
            "group": nav_title,
            "slug": _slugify(nav_title),
            "items": prefixed_items,
        })
    return merged


def _generate_landing_page(projects_info, config):
    """Generate an HTML landing page listing all constituent projects as cards.

    Args:
        projects_info: List of dicts with keys: slug, nav_title, description,
            version, url_prefix.
        config: The docs-site config dict.

    Returns:
        HTML body string for the landing page.
    """
    cards = []
    for info in projects_info:
        title = _escape_html(info["nav_title"])
        desc = _escape_html(info.get("description", ""))
        version = _escape_html(info.get("version", ""))
        link = _html_path_to_url(f"{info['url_prefix']}/index.html")
        card = (
            f'<div class="project-card">'
            f'<h3><a href="{link}">{title}</a></h3>'
        )
        if desc:
            card += f'<p>{desc}</p>'
        if version:
            card += f'<span class="project-version">v{version}</span>'
        card += '</div>'
        cards.append(card)
    return (
        '<div class="project-grid">'
        + "\n".join(cards)
        + '</div>'
    )


def _validate_rlsbl_workspace(docs_site_dir, unified_config):
    """Validate unified config against rlsbl monorepo workspace.

    Walks up from docs_site_dir looking for ``.rlsbl-monorepo/workspace.toml``.
    If found, checks that every workspace project with a ``selfdoc.json``
    is either listed in ``unified.projects`` or ``unified.exclude``.

    Raises ConfigError if an undeclared selfdoc-enabled project is found.
    """
    import tomllib

    # Walk up looking for .rlsbl-monorepo/workspace.toml
    current = os.path.abspath(docs_site_dir)
    workspace_toml = None
    for _ in range(10):  # max 10 levels up
        candidate = os.path.join(current, ".rlsbl-monorepo", "workspace.toml")
        if os.path.isfile(candidate):
            workspace_toml = candidate
            break
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    if workspace_toml is None:
        return  # no rlsbl monorepo -- skip validation

    monorepo_root = os.path.dirname(os.path.dirname(workspace_toml))

    with open(workspace_toml, "rb") as f:
        workspace = tomllib.load(f)

    # Get workspace project paths
    workspace_projects = workspace.get("projects", [])
    if not workspace_projects:
        return

    # Build sets of known slugs/paths from unified config
    unified_projects = unified_config.get("projects", [])
    exclude_patterns = unified_config.get("exclude", [])

    known_paths = set()
    for proj in unified_projects:
        abs_path = os.path.normpath(
            os.path.join(docs_site_dir, proj["path"])
        )
        known_paths.add(abs_path)

    # Check each workspace project
    for wp in workspace_projects:
        # workspace.toml entries can be strings (path) or dicts with "path" key
        if isinstance(wp, str):
            wp_path = wp
        elif isinstance(wp, dict):
            wp_path = wp.get("path", "")
        else:
            continue

        abs_wp = os.path.normpath(os.path.join(monorepo_root, wp_path))

        # Skip if no selfdoc.json
        if not os.path.isfile(os.path.join(abs_wp, "selfdoc.json")):
            continue

        # Skip if it's the docs-site itself
        if os.path.abspath(abs_wp) == os.path.abspath(docs_site_dir):
            continue

        # Skip if already in unified.projects
        if abs_wp in known_paths:
            continue

        # Check exclude patterns
        wp_name = os.path.basename(abs_wp)
        excluded = False
        for pattern in exclude_patterns:
            if re.match(pattern.replace("*", ".*"), wp_name):
                excluded = True
                break
        if excluded:
            continue

        raise ConfigError(
            f"rlsbl workspace project '{wp_path}' has selfdoc.json but is "
            f"neither in unified.projects nor unified.exclude. Add it to one."
        )


def _merge_site_terms(all_terms):
    """Merge site_terms dicts from multiple projects.

    Each entry in *all_terms* is a (project_slug, terms_dict) tuple.
    Returns a merged dict keyed by lowercase term, with project
    attribution added to each entry.
    """
    merged = {}
    for project_slug, terms in all_terms:
        for key, info in terms.items():
            if key not in merged:
                merged[key] = dict(info)
                merged[key]["project"] = project_slug
    return merged


def _generate_unified_glossary_html(merged_terms, projects_info):
    """Generate a unified glossary page body from merged terms.

    Groups terms alphabetically with project attribution.
    Returns HTML body string.
    """
    if not merged_terms:
        return "<p>No glossary terms defined.</p>"

    sorted_terms = sorted(merged_terms.values(), key=lambda t: t["term"].lower())
    items = []
    for info in sorted_terms:
        anchor = info.get("anchor", _slugify(info["term"]))
        term_name = _escape_html(info["term"])
        definition = info.get("definition", "")
        project = _escape_html(info.get("project", ""))
        source_html = ""
        if project:
            source_html = f' <span class="term-project">[{project}]</span>'
        items.append(
            f'<dt id="{anchor}"><dfn>{term_name}</dfn></dt>'
            f'<dd>{definition}{source_html}</dd>'
        )
    return (
        '<div class="glossary"><dl>\n'
        + "\n".join(items)
        + '\n</dl></div>'
    )


def build_unified(dir_path=".", config=None, include_drafts=False):
    """Build a unified documentation site from multiple constituent projects.

    Main entry point for monorepo unified builds. Reads the ``unified``
    section from the docs-site's config, builds each constituent project
    and the docs-site's own content, then assembles everything into a
    single output directory with merged search index, unified navigation,
    and shared assets.

    Args:
        dir_path: The docs-site's project root directory.
        config: Pre-loaded config dict (if None, loads from selfdoc_core.json).
        include_drafts: Include draft posts in the build output.

    Returns:
        Dict of {output_path: True} for files written.
    """
    if config is None:
        config = load_config(dir_path)
    if config is None:
        raise RuntimeError(
            "No selfdoc.json found. Run 'selfdoc init' to initialize."
        )

    unified_config = config.get("unified")
    if unified_config is None:
        raise ConfigError("No 'unified' section in selfdoc.json")

    if config.get("versions") is None:
        raise ConfigError(
            "selfdoc.json requires 'versions' array for unified builds."
        )
    if config.get("locales") is None:
        raise ConfigError(
            "selfdoc.json requires 'locales' array for unified builds."
        )

    # Validate against rlsbl workspace if present
    _validate_rlsbl_workspace(dir_path, unified_config)

    locales = config["locales"]
    versions = config["versions"]
    default_locale = locales[0]
    for loc in locales:
        if loc.get("default") is True:
            default_locale = loc
            break
    default_locale_code = default_locale["code"]
    latest_version = versions[-1]["version"]

    output_dir = os.path.join(dir_path, config["output"].rstrip("/"))
    docs_dir_name = config["docs"].rstrip("/")
    docs_dir = os.path.join(dir_path, docs_dir_name)

    if not os.path.isdir(docs_dir):
        raise RuntimeError(
            f"Docs directory '{docs_dir_name}' not found. "
            "Create it or run 'selfdoc init'."
        )

    # Clean output directory
    if os.path.exists(output_dir):
        effects.rmtree(output_dir)
    effects.makedirs(output_dir, exist_ok=True)

    # Get theme info from docs-site config
    theme_name = config.get("theme", "minimal")
    raw_theme_css = get_css(theme_name)
    theme_meta = get_theme_meta(theme_name)
    critical_css, _ = _extract_critical_css(raw_theme_css)
    critical_css = _minify_css(critical_css)

    # Track all injected post files for cleanup: list of (files, docs_dir) tuples
    all_injected_posts = []

    # --- Partition pages for each constituent project ---
    # slug -> (versioned_set, unversioned_set, uv_markdown, uv_frontmatter)
    project_page_partitions = {}
    for project_entry in unified_config["projects"]:
        slug = _project_slug(project_entry)
        project_path = _resolve_project_path(project_entry, dir_path)
        proj_config = load_config(project_path)
        if proj_config is not None:
            proj_docs_dir = os.path.join(
                project_path, proj_config["docs"].rstrip("/"),
            )
            # Inject posts for this constituent project
            proj_injected = _inject_posts_into_docs(
                project_path, proj_config, proj_docs_dir, include_drafts,
            )
            if proj_injected:
                all_injected_posts.append((proj_injected, proj_docs_dir))
            v_pages, uv_pages, uv_md, uv_fm = _partition_pages(
                proj_config, proj_docs_dir, project_path,
            )
            project_page_partitions[slug] = (v_pages, uv_pages, uv_md, uv_fm)

    # Also partition the docs-site's own pages
    docs_site_docs_dir = os.path.join(dir_path, config["docs"].rstrip("/"))

    # Inject posts into docs-site's docs/posts/ so the normal pipeline discovers them
    injected_post_files = _inject_posts_into_docs(
        dir_path, config, docs_site_docs_dir, include_drafts,
    )
    if injected_post_files:
        all_injected_posts.append((injected_post_files, docs_site_docs_dir))

    ds_versioned, ds_unversioned, ds_uv_markdown, ds_uv_frontmatter = _partition_pages(
        config, docs_site_docs_dir, dir_path,
    )

    try:
        written = _build_unified_body(
            dir_path, config, unified_config, locales, versions,
            default_locale_code, latest_version, output_dir,
            docs_site_docs_dir, project_page_partitions,
            ds_versioned, ds_unversioned, ds_uv_markdown,
            ds_uv_frontmatter, raw_theme_css, theme_meta,
            critical_css, include_drafts,
        )
    finally:
        for files, d_dir in all_injected_posts:
            _cleanup_injected_posts(files, d_dir)

    return written


def _build_unified_body(
    dir_path, config, unified_config, locales, versions,
    default_locale_code, latest_version, output_dir,
    docs_site_docs_dir, project_page_partitions,
    ds_versioned, ds_unversioned, ds_uv_markdown,
    ds_uv_frontmatter, raw_theme_css, theme_meta,
    critical_css, include_drafts,
):
    """Core build logic for unified sites.

    Extracted so ``build_unified`` can wrap it in try/finally for
    post-injection cleanup.
    """
    written = {}
    all_search_entries = []
    projects_info = []
    projects_nav_data = []

    # Check reserved paths and collisions
    version_strs = [v["version"] for v in versions]
    _check_reserved_paths(version_strs, config)
    for slug, (v_pages, uv_pages, _uv_md, _uv_fm) in project_page_partitions.items():
        _check_unversioned_collisions(uv_pages, version_strs)
    _check_unversioned_collisions(ds_unversioned, version_strs)

    # --- Build each constituent project for each docs-site version ---
    for ver_entry in versions:
        ver_str = ver_entry["version"]
        is_latest = (ver_str == latest_version)
        ver_projects_pinning = ver_entry.get("projects") or {}

        for project_entry in unified_config["projects"]:
            slug = _project_slug(project_entry)
            nav_title = _project_nav_title(project_entry)
            project_path = _resolve_project_path(project_entry, dir_path)

            # Load the constituent project's own config
            proj_config = load_config(project_path)
            if proj_config is None:
                raise ConfigError(
                    f"No selfdoc.json found in constituent project "
                    f"'{project_entry['path']}' (resolved to '{project_path}')"
                )

            # Determine the build directory and version for this project.
            # For old docs-site versions with a projects pinning dict,
            # extract the constituent project at the pinned version tag.
            if not is_latest and slug in ver_projects_pinning:
                pinned_version = ver_projects_pinning[slug]
                build_dir = _extract_version_content(
                    pinned_version, proj_config, project_path,
                )
                proj_version = pinned_version
            else:
                build_dir = project_path
                from selfdoc_core.utils import detect_project_version
                proj_version = detect_project_version(project_path)

            # Build the project for each locale
            for locale in locales:
                locale_code = locale["code"]
                output_subdir = page_address(
                    "index.html", locale=locale_code, project=slug,
                    version=ver_str,
                ).mount

                proj_v_pages, proj_uv_pages, proj_uv_md, proj_uv_fm = (
                    project_page_partitions.get(
                        slug, (None, set(), {}, {}),
                    )
                )
                result = build_single(
                    dir_path=build_dir,
                    config=proj_config,
                    mount_locale=locale_code,
                    mount_project=slug,
                    mount_version=ver_str,
                    version_override=proj_version or ver_str,
                    locale_override=locale_code,
                    available_versions=versions,
                    available_locales=locales,
                    current_version=ver_str,
                    current_locale=locale_code,
                    is_latest=is_latest,
                    page_filter=proj_v_pages if proj_uv_pages else None,
                    unversioned_markdown=proj_uv_md if proj_uv_pages else None,
                    unversioned_frontmatter=proj_uv_fm if proj_uv_pages else None,
                )
                html_files = result.html_files
                search_entries = result.search_entries
                proj_docs_dir = result.docs_dir
                other_files = result.other_files
                nav_items = result.nav_items
                config_description = result.config_description

                # Override the project field in search entries
                patched_entries = []
                for entry in search_entries:
                    patched = dataclasses.replace(entry, project=slug)
                    patched_entries.append(patched)
                all_search_entries.extend(patched_entries)

                # Write HTML files
                for rel_path, html_content in html_files.items():
                    out_path = os.path.join(output_dir, rel_path)
                    effects.makedirs(os.path.dirname(out_path), exist_ok=True)
                    with effects.open_write(out_path, "w", encoding="utf-8") as f:
                        f.write(_minify_html(html_content))
                    written[out_path] = True

                # Copy static assets
                for rel_path in other_files:
                    src = os.path.join(proj_docs_dir, rel_path)
                    dst = os.path.join(output_dir, output_subdir, rel_path)
                    effects.makedirs(os.path.dirname(dst), exist_ok=True)
                    effects.copy_file(src, dst)
                    written[dst] = True

                # Collect nav data (only for latest version + default locale)
                if is_latest and locale_code == default_locale_code:
                    projects_nav_data.append(
                        (slug, nav_title, nav_items, output_subdir)
                    )
                    projects_info.append({
                        "slug": slug,
                        "nav_title": nav_title,
                        "description": config_description or "",
                        "version": proj_version or ver_str,
                        "url_prefix": output_subdir,
                    })

    # --- Build unversioned pages for each constituent project ---
    for project_entry in unified_config["projects"]:
        slug = _project_slug(project_entry)
        nav_title = _project_nav_title(project_entry)
        project_path = _resolve_project_path(project_entry, dir_path)
        proj_config = load_config(project_path)
        _, proj_uv_pages, _, _ = project_page_partitions.get(slug, (None, set(), {}, {}))

        if not proj_uv_pages:
            continue

        for locale in locales:
            locale_code = locale["code"]
            output_subdir = page_address(
                "index.html", locale=locale_code, project=slug,
            ).mount

            uv_result = build_single(
                dir_path=project_path,
                config=proj_config,
                mount_locale=locale_code,
                mount_project=slug,
                mount_version="",
                version_override="",
                locale_override=locale_code,
                available_versions=versions,
                available_locales=locales,
                current_version="",
                current_locale=locale_code,
                is_latest=True,
                page_filter=proj_uv_pages,
            )

            patched_entries = []
            for entry in uv_result.search_entries:
                patched = dataclasses.replace(entry, project=slug)
                patched_entries.append(patched)
            all_search_entries.extend(patched_entries)

            for rel_path, html_content in uv_result.html_files.items():
                out_path = os.path.join(output_dir, rel_path)
                effects.makedirs(os.path.dirname(out_path), exist_ok=True)
                with effects.open_write(out_path, "w", encoding="utf-8") as f:
                    f.write(_minify_html(html_content))
                written[out_path] = True

            for rel_path in uv_result.other_files:
                src = os.path.join(uv_result.docs_dir, rel_path)
                dst = os.path.join(output_dir, output_subdir, rel_path)
                effects.makedirs(os.path.dirname(dst), exist_ok=True)
                effects.copy_file(src, dst)
                written[dst] = True

    # --- Build the docs-site's own content (common pages) ---
    common_latest_build = None
    for locale in locales:
        locale_code = locale["code"]
        common_subdir = page_address(
            "index.html", locale=locale_code, project="common",
            version=latest_version,
        ).mount

        result = build_single(
            dir_path=dir_path,
            config=config,
            mount_locale=locale_code,
            mount_project="common",
            mount_version=latest_version,
            version_override=latest_version,
            locale_override=locale_code,
            available_versions=versions,
            available_locales=locales,
            current_version=latest_version,
            current_locale=locale_code,
            is_latest=True,
            page_filter=ds_versioned if ds_unversioned else None,
            unversioned_markdown=ds_uv_markdown if ds_unversioned else None,
            unversioned_frontmatter=ds_uv_frontmatter if ds_unversioned else None,
        )
        html_files = result.html_files
        search_entries = result.search_entries
        common_docs_dir = result.docs_dir
        other_files = result.other_files
        nav_items = result.nav_items

        # Mark common search entries
        patched_entries = []
        for entry in search_entries:
            patched = dataclasses.replace(entry, project="common")
            patched_entries.append(patched)
        all_search_entries.extend(patched_entries)

        # Write HTML files
        for rel_path, html_content in html_files.items():
            out_path = os.path.join(output_dir, rel_path)
            effects.makedirs(os.path.dirname(out_path), exist_ok=True)
            with effects.open_write(out_path, "w", encoding="utf-8") as f:
                f.write(_minify_html(html_content))
            written[out_path] = True

        # Copy static assets
        for rel_path in other_files:
            src = os.path.join(common_docs_dir, rel_path)
            dst = os.path.join(output_dir, common_subdir, rel_path)
            effects.makedirs(os.path.dirname(dst), exist_ok=True)
            effects.copy_file(src, dst)
            written[dst] = True

        if locale_code == default_locale_code:
            common_latest_build = {
                "html_files": result.html_files,
                "markdown_files": result.markdown_files,
                "frontmatter": result.frontmatter,
                "page_dates": result.page_dates,
                "project_name": result.project_name,
                "version": result.version,
                "docs_dir": common_docs_dir,
                "has_custom_css": result.has_custom_css,
                "config_description": result.config_description,
                "base_url": result.base_url,
                "url_builder": SimpleURLBuilder(result.base_url) if result.base_url else None,
                "feed_url": result.feed_url,
                "lang": result.lang,
            }

    # --- Build unversioned docs-site pages ---
    if ds_unversioned:
        for locale in locales:
            locale_code = locale["code"]
            uv_subdir = page_address(
                "index.html", locale=locale_code, project="common",
            ).mount

            uv_result = build_single(
                dir_path=dir_path,
                config=config,
                mount_locale=locale_code,
                mount_project="common",
                mount_version="",
                version_override="",
                locale_override=locale_code,
                available_versions=versions,
                available_locales=locales,
                current_version="",
                current_locale=locale_code,
                is_latest=True,
                page_filter=ds_unversioned,
            )

            patched_entries = []
            for entry in uv_result.search_entries:
                patched = dataclasses.replace(entry, project="common")
                patched_entries.append(patched)
            all_search_entries.extend(patched_entries)

            for rel_path, html_content in uv_result.html_files.items():
                out_path = os.path.join(output_dir, rel_path)
                effects.makedirs(os.path.dirname(out_path), exist_ok=True)
                with effects.open_write(out_path, "w", encoding="utf-8") as f:
                    f.write(_minify_html(html_content))
                written[out_path] = True

            for rel_path in uv_result.other_files:
                src = os.path.join(uv_result.docs_dir, rel_path)
                dst = os.path.join(output_dir, uv_subdir, rel_path)
                effects.makedirs(os.path.dirname(dst), exist_ok=True)
                effects.copy_file(src, dst)
                written[dst] = True

            # Merge unversioned data into common_latest_build for auxiliary files
            if locale_code == default_locale_code and common_latest_build:
                common_latest_build["markdown_files"] = {
                    **common_latest_build["markdown_files"],
                    **uv_result.markdown_files,
                }
                common_latest_build["frontmatter"] = {
                    **common_latest_build["frontmatter"],
                    **uv_result.frontmatter,
                }
                common_latest_build["page_dates"] = {
                    **common_latest_build["page_dates"],
                    **uv_result.page_dates,
                }

    # --- Generate landing page ---
    landing_body = _generate_landing_page(projects_info, config)
    common_subdir = f"{default_locale_code}/common/{latest_version}"
    landing_html_path = os.path.join(
        output_dir, common_subdir, "projects", "index.html",
    )
    # Wrap landing page in minimal HTML
    landing_full = (
        '<!DOCTYPE html>'
        '<html lang="en">'
        '<head><meta charset="utf-8">'
        f'<title>Projects - {common_latest_build["project_name"]}</title>'
        f'<link rel="stylesheet" href="../style.css">'
        '</head>'
        '<body>'
        f'<h1>Projects</h1>'
        f'{landing_body}'
        '</body></html>'
    )
    effects.makedirs(os.path.dirname(landing_html_path), exist_ok=True)
    with effects.open_write(landing_html_path, "w", encoding="utf-8") as f:
        f.write(landing_full)
    written[landing_html_path] = True

    # --- Shared assets: CSS ---
    lb = common_latest_build
    css_path = os.path.join(output_dir, "style.css")
    theme_css = raw_theme_css
    pygments_css = generate_pygments_css(
        light_style=theme_meta.get("pygments_light", "default"),
        dark_style=theme_meta.get("pygments_dark", "monokai"),
    )
    if pygments_css:
        theme_css = theme_css + "\n\n/* Pygments syntax highlighting */\n" + pygments_css

    # Append project-grid card styles
    theme_css += "\n\n" + _PROJECT_GRID_CSS

    theme_css = _minify_css(theme_css)
    with effects.open_write(css_path, "w", encoding="utf-8") as f:
        f.write(theme_css)
    written[css_path] = True

    # --- Search index ---
    search_index_path = os.path.join(output_dir, "search-index.json")
    with effects.open_write(search_index_path, "w", encoding="utf-8") as f:
        json.dump(
            [dataclasses.asdict(entry) for entry in all_search_entries],
            f, ensure_ascii=False,
        )
    written[search_index_path] = True

    # --- Search JS ---
    from selfdoc_core.html import _generate_search_js, _minify_js
    search_engine = config.get("search_engine") or "builtin"
    search_js_path = os.path.join(output_dir, "search.js")
    with effects.open_write(search_js_path, "w", encoding="utf-8") as f:
        f.write(_minify_js(_generate_search_js(engine=search_engine)))
    written[search_js_path] = True

    # --- Custom CSS ---
    custom_css_src = os.path.join(lb["docs_dir"], "custom.css")
    if lb["has_custom_css"]:
        custom_css_dst = os.path.join(output_dir, "custom.css")
        effects.copy_file(custom_css_src, custom_css_dst)
        written[custom_css_dst] = True

    # --- Auxiliary files (OG cards, sitemap, llms.txt, 404, etc.) ---
    all_html_paths = []
    for k in written:
        if k.endswith(".html"):
            rel = os.path.relpath(k, output_dir)
            all_html_paths.append(rel)

    repo = config.get("repo", None)
    aux_written = _generate_auxiliary_files(
        output_dir=output_dir,
        project_name=lb["project_name"],
        version=lb["version"],
        markdown_files=lb["markdown_files"],
        html_paths=all_html_paths,
        base_url=lb["base_url"],
        has_custom_css=lb["has_custom_css"],
        repo=repo,
        lang=lb["lang"],
        page_dates=lb["page_dates"],
        frontmatter=lb["frontmatter"],
        description=lb["config_description"],
        feed_url=lb["feed_url"],
        critical_css=critical_css,
        accent_color=theme_meta["accent_color"],
        theme_meta=theme_meta,
        deploy=config.get("deploy"),
        feed_max_entries=config.get("feed_max_entries"),
        url_builder=lb["url_builder"],
        # The aux files describe the docs-site's own common pages, which
        # mount under <locale>/common/<version>.
        mount_locale=default_locale_code,
        mount_project="common",
        mount_version=latest_version,
        page_addresses={
            md: page_address(
                _md_to_html_path(md),
                locale=default_locale_code,
                project="common",
                version=latest_version,
            )
            for md in lb["markdown_files"]
        },
    )
    written.update(aux_written)

    # --- Root redirect to common landing ---
    landing_prefix = f"{default_locale_code}/common/{latest_version}"
    # Document-relative, with no leading slash.  The build output is not
    # always served from an origin root: an assembly serves it under
    # /<slug>/ and GitHub Pages project sites under /<repo>/.  A
    # root-relative hop escapes that subtree; a document-relative one
    # resolves correctly in every case, origin root included.
    redirect_url = f"{landing_prefix}/"
    # Absolute canonical: a root-relative one resolves against whatever host
    # served the stub, so every alias of the site would claim to be canonical.
    canonical_url = lb["url_builder"].page_url(redirect_url)
    root_index_html = (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head>\n"
        f'  <meta http-equiv="refresh" content="0;url={redirect_url}">\n'
        f'  <link rel="canonical" href="{canonical_url}">\n'
        "</head>\n"
        "<body>\n"
        f'  <script>window.location.replace("{redirect_url}")</script>\n'
        f'  <p>Redirecting to <a href="{redirect_url}">{redirect_url}</a></p>\n'
        "</body>\n"
        "</html>\n"
    )
    root_index_path = os.path.join(output_dir, "index.html")
    with effects.open_write(root_index_path, "w", encoding="utf-8") as f:
        f.write(root_index_html)
    written[root_index_path] = True

    # Cloudflare only ever reads the _redirects at the deployed site root,
    # where there is no document to resolve a relative target against --
    # this rule stays site-absolute.
    redirects_content = f"/ /{landing_prefix}/ 302\n"
    redirects_path = os.path.join(output_dir, "_redirects")
    with effects.open_write(redirects_path, "w", encoding="utf-8") as f:
        f.write(redirects_content)
    written[redirects_path] = True

    # --- Pre-compress ---
    compress_count, has_brotli = _compress_output(output_dir)
    if has_brotli:
        print(f"Pre-compressed {compress_count} files (gzip + brotli)")
    else:
        print(
            f"Pre-compressed {compress_count} files "
            f"(gzip only, install brotli for better compression)"
        )

    return written


# CSS for the project card grid on the landing page
_PROJECT_GRID_CSS = """\
.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1.5rem;
  margin: 2rem 0;
}
.project-card {
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 8px;
  padding: 1.5rem;
  transition: box-shadow 0.2s;
}
.project-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}
.project-card h3 {
  margin: 0 0 0.5rem 0;
}
.project-card h3 a {
  text-decoration: none;
  color: var(--link, #0969da);
}
.project-card p {
  margin: 0 0 0.5rem 0;
  color: var(--text-secondary, #666);
}
.project-version {
  font-size: 0.85em;
  color: var(--text-secondary, #666);
  background: var(--code-bg, #f6f8fa);
  padding: 0.1em 0.4em;
  border-radius: 3px;
}
.term-project {
  font-size: 0.85em;
  color: var(--text-secondary, #666);
}
"""

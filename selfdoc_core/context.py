"""Build, page, and search context dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BuildContext:
    dir_path: str
    config: dict
    locale: str
    version: str
    url_prefix: str
    output_dir: str
    output_subdir: str
    is_latest: bool
    available_versions: list
    available_locales: list
    base_url: str | None
    project_name: str
    theme_meta: dict
    accent_color: str
    critical_css: str
    deploy_target: str | None


@dataclass
class PageContext:
    md_path: str
    html_path: str
    title: str
    body_html: str
    nav_html: str
    toc_html: str
    breadcrumbs: list | None
    prefix: str
    frontmatter: dict
    prev_page: dict | None
    next_page: dict | None
    page_number: int | None
    total_pages: int | None
    summary: str
    source_path: str | None


@dataclass
class SearchEntry:
    title: str
    path: str
    body: str
    version: str = ""
    locale: str = ""
    group: str = ""
    type: str = ""
    target: str = ""
    project: str = ""
    tags: list = field(default_factory=list)

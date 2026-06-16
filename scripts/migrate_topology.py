#!/usr/bin/env python3
"""Migrate selfdoc projects to use topology config.

Discovers all selfdoc-enabled projects under a directory and adds/updates
topology and assembly sections in each project's selfdoc.json.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys


def to_kebab(name: str) -> str:
    """Convert a name to kebab-case slug."""
    s = name.lower()
    s = s.replace(" ", "-").replace("_", "-")
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def discover_projects(projects_dir: str) -> list[str]:
    """Find immediate subdirectories containing selfdoc.json."""
    results = []
    try:
        entries = sorted(os.listdir(projects_dir))
    except OSError as e:
        print(f"Warning: cannot list {projects_dir}: {e}", file=sys.stderr)
        return results
    for entry in entries:
        full = os.path.join(projects_dir, entry)
        if os.path.isdir(full) and os.path.isfile(os.path.join(full, "selfdoc.json")):
            results.append(full)
    return results


def update_config(
    config: dict,
    slug: str,
    docs_base: str,
    posts_base: str | None,
    assembly_repo: str,
) -> dict:
    """Add/update topology and assembly sections in a config dict."""
    topo = config.get("topology", {})
    topo["slug"] = slug
    topo["docs_base"] = docs_base
    if posts_base is not None:
        topo["posts_base"] = posts_base
    topo["assembly"] = assembly_repo
    config["topology"] = topo

    asm = config.get("assembly", {})
    asm["repo"] = assembly_repo
    config["assembly"] = asm

    return config


def build_projects_map(
    projects: list[tuple[str, str]], docs_base: str
) -> dict[str, str]:
    """Build {slug: url} map from list of (slug, dir_path) pairs."""
    result = {}
    for slug, _dir_path in projects:
        result[slug] = docs_base.rstrip("/") + "/" + slug
    return result


def add_cross_links(
    config: dict, slug: str, projects_map: dict[str, str]
) -> dict:
    """Add topology.projects excluding the current project."""
    filtered = {k: v for k, v in projects_map.items() if k != slug}
    config.setdefault("topology", {})["projects"] = filtered
    return config


def main(argv: list[str] | None = None) -> None:
    """Entry point for the migration script."""
    parser = argparse.ArgumentParser(
        description="Apply topology config to selfdoc projects."
    )
    parser.add_argument("--docs-base", required=True, help="Base URL for docs")
    parser.add_argument("--posts-base", default=None, help="Base URL for blog posts")
    parser.add_argument(
        "--assembly-repo", required=True, help="GitHub repo for docs assembly"
    )
    parser.add_argument(
        "--projects-dir",
        default=os.path.expanduser("~/Projects"),
        help="Directory containing projects (default: ~/Projects)",
    )
    args = parser.parse_args(argv)

    project_dirs = discover_projects(args.projects_dir)
    if not project_dirs:
        print("No selfdoc projects found.")
        return

    # First pass: update each project's config and collect slugs
    project_info: list[tuple[str, str]] = []  # (slug, dir_path)
    updated_paths: list[str] = []

    for proj_dir in project_dirs:
        config_path = os.path.join(proj_dir, "selfdoc.json")
        try:
            with open(config_path) as f:
                config = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(
                f"Warning: skipping {proj_dir}: {e}",
                file=sys.stderr,
            )
            continue

        dir_name = os.path.basename(proj_dir)
        slug = to_kebab(dir_name)
        project_info.append((slug, proj_dir))

        update_config(config, slug, args.docs_base, args.posts_base, args.assembly_repo)

        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")

        updated_paths.append(proj_dir)

    # Second pass: add cross-project links
    projects_map = build_projects_map(project_info, args.docs_base)

    for slug, proj_dir in project_info:
        config_path = os.path.join(proj_dir, "selfdoc.json")
        with open(config_path) as f:
            config = json.load(f)

        add_cross_links(config, slug, projects_map)

        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")

    # Summary
    print(f"Updated {len(updated_paths)} project(s):")
    for slug, proj_dir in project_info:
        print(f"  {slug} ({proj_dir})")
    print(f"Cross-project map has {len(projects_map)} entries.")


if __name__ == "__main__":
    main()

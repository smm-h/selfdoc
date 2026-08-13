"""Manifest generation and loading for selfdoc projects, producing JSON metadata for pages, posts, slugs, and version info."""

from __future__ import annotations

import datetime
import json
import os
import re
from dataclasses import dataclass

from selfdoc_core.utils import atomic_write, detect_project_version

#: The theme a project's manifest records when its config names none.  It
#: is the same default ``build`` applies, and the assembly's chrome reads
#: this field to decide which stylesheet a project's pages reference.
DEFAULT_THEME = "minimal"

from selfdoc_core import effects


@dataclass(frozen=True, slots=True)
class Manifest:
    schema_version: int
    name: str
    slug: str
    version: str
    description: str
    language: str
    base_url: str
    pages: list
    posts: list
    last_gen: str
    #: The theme the build rendered against.  The assembly's site-level
    #: chrome asset is keyed by it, so a manifest that does not carry one
    #: leaves every page referencing the default theme's stylesheet
    #: regardless of what its project configured.
    theme: str = ""


def _to_kebab(name: str) -> str:
    """Convert a name to kebab-case slug.

    Lowercase, replace spaces/underscores with hyphens, strip
    non-alphanumeric characters except hyphens, collapse multiple
    hyphens.
    """
    s = name.lower()
    s = s.replace(" ", "-").replace("_", "-")
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def _page_headings(frontmatter: dict, content: str) -> list[dict]:
    """Return this page's headings with the anchors the built page carries.

    Anchors come from the same assignment the HTML renderer and the search
    index use, so a manifest anchor is always an id that exists on the
    page -- de-duplicated (``setup``, ``setup-1``) and free of ``#`` lines
    inside fenced code blocks.
    """
    # Imported here: html pulls in themes/icons, and manifest is loaded by
    # readers that never render.
    from selfdoc_core.html import assign_heading_anchors
    from selfdoc_core.tokenizer import tokenize

    # A frontmatter title renames the page's H1, and its anchor with it.
    # Without one the H1's own text is the title, which is what
    # assign_heading_anchors falls back to.
    title = frontmatter.get("title")
    page_title = str(title) if title else None

    return [
        {"level": ha.level, "text": ha.text, "anchor": ha.anchor}
        for ha in assign_heading_anchors(tokenize(content), page_title=page_title)
    ]


def _extract_title(frontmatter: dict, raw_content: str) -> str:
    """Extract page title from frontmatter or first heading."""
    title = frontmatter.get("title")
    if title:
        return str(title)
    # Fall back to first markdown heading
    for line in raw_content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def generate_manifest(
    config: dict,
    pages_data: dict,
    posts_data: list | None = None,
    dir_path: str = ".",
    output_name: str = "manifest.json",
) -> Manifest:
    """Build a Manifest from config and resolved docs, write it to disk.

    Parameters
    ----------
    config:
        The loaded selfdoc config dict (from ``load_config``).
    pages_data:
        Dict from ``resolve_all_docs`` mapping rel_path to
        ``(frontmatter, resolved, raw, fm_line_count)``.
    posts_data:
        Optional list of post metadata dicts (for Phase 3.3-3.4).
        Defaults to an empty list.
    dir_path:
        Project root directory. Defaults to ``"."``.
    output_name:
        Filename for the manifest inside ``.selfdoc/``.
        Defaults to ``"manifest.json"``.
    """
    if posts_data is None:
        posts_data = []

    # Name: from config or directory basename
    name = config.get("name") or os.path.basename(os.path.abspath(dir_path))

    # Slug: from topology config or kebab-case of name
    slug = (config.get("topology") or {}).get("slug")
    if not slug:
        slug = _to_kebab(name)

    # Version: from config or detect from project files
    version = config.get("version") or detect_project_version(
        os.path.abspath(dir_path)
    )

    # Description
    description = config.get("description") or ""

    # Language: primary language from first source entry
    source = config.get("source")
    language = source[0]["language"] if source else ""

    # Base URL
    base_url = config.get("base_url") or ""

    # Theme: what the chrome asset for this project's pages is built from.
    theme = str(config.get("theme") or "") or DEFAULT_THEME

    # Pages
    pages = []
    for rel_path, (frontmatter, resolved, raw, _fm_line_count) in sorted(
        pages_data.items()
    ):
        page_title = _extract_title(frontmatter, raw)
        pages.append({
            "path": rel_path,
            "title": page_title,
            "type": frontmatter.get("type", "doc"),
            # Headings are read from the resolved content -- what the
            # renderer sees -- so directive-generated headings are included.
            "headings": _page_headings(frontmatter, resolved),
        })

    # Posts
    posts = []
    for post in posts_data:
        posts.append({
            "path": post.get("path", ""),
            "title": post.get("title", ""),
            "date": post.get("date", ""),
            "slug": post.get("slug", ""),
            "tags": post.get("tags", []),
        })

    manifest = Manifest(
        schema_version=1,
        name=name,
        slug=slug,
        version=version,
        description=description,
        language=language,
        base_url=base_url,
        pages=pages,
        posts=posts,
        last_gen=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        theme=theme,
    )

    # Write to .selfdoc/<output_name>
    selfdoc_dir = os.path.join(dir_path, ".selfdoc")
    effects.makedirs(selfdoc_dir, exist_ok=True)
    manifest_path = os.path.join(selfdoc_dir, output_name)

    data = {
        "schema_version": manifest.schema_version,
        "name": manifest.name,
        "slug": manifest.slug,
        "version": manifest.version,
        "description": manifest.description,
        "language": manifest.language,
        "base_url": manifest.base_url,
        "pages": manifest.pages,
        "posts": manifest.posts,
        "last_gen": manifest.last_gen,
        "theme": manifest.theme,
    }

    # Skip write when only last_gen changed (idempotency: avoids dirtying
    # the working tree on every selfdoc gen when content is unchanged).
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            # Compare everything except last_gen
            new_content = {k: v for k, v in data.items() if k != "last_gen"}
            old_content = {k: v for k, v in existing.items() if k != "last_gen"}
            if new_content == old_content:
                return manifest
        except (OSError, json.JSONDecodeError, ValueError):
            pass  # Unreadable or corrupt -- rewrite

    atomic_write(manifest_path, json.dumps(data, indent=2) + "\n")

    return manifest


def manifest_compat(data: dict, source: str = "") -> Manifest:
    """Centralized manifest compatibility layer.

    All manifest read paths (``load_manifest``, ``load_manifest_from_git``,
    and assembly's raw ``json.load``) go through this function to construct
    a ``Manifest`` from a parsed JSON dict.

    The function is a tolerant reader: it extracts only the fields it knows
    about and silently ignores any unknown keys.  This codifies the contract
    that future manifest fields can be added without breaking older readers.

    Args:
        data: Parsed manifest JSON dict.
        source: Human-readable description of where the data came from
            (used in error messages). Empty string for generic context.

    Returns:
        A ``Manifest`` instance.

    Raises:
        RuntimeError: If ``schema_version`` is greater than 1.
    """
    sv = data.get("schema_version", 1)
    if sv > 1:
        ctx = f" in {source}" if source else ""
        raise RuntimeError(
            f"Unsupported manifest schema_version {sv}{ctx} "
            f"(max supported: 1)"
        )

    return Manifest(
        schema_version=sv,
        name=data.get("name", ""),
        slug=data.get("slug", ""),
        version=data.get("version", ""),
        description=data.get("description", ""),
        language=data.get("language", ""),
        base_url=data.get("base_url", ""),
        pages=data.get("pages", []),
        posts=data.get("posts", []),
        last_gen=data.get("last_gen", ""),
        theme=str(data.get("theme") or ""),
    )


def load_manifest(path: str) -> Manifest | None:
    """Read a manifest JSON file and return a Manifest instance.

    Returns ``None`` if the file does not exist. Raises ``RuntimeError``
    if ``schema_version`` is greater than 1 (unsupported future format).
    """
    if not os.path.isfile(path):
        return None

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return manifest_compat(data, source=path)


def load_manifest_from_git(dir_path: str = ".") -> Manifest | None:
    """Load manifest.json from the last git commit (HEAD).

    Reads ``.selfdoc/manifest.json`` from the git index at HEAD, bypassing
    the working-tree copy.  This is used for slug immutability checking:
    comparing post slugs against the *committed* manifest prevents silent
    slug changes when ``selfdoc gen`` has already regenerated the on-disk
    manifest.

    Returns ``None`` if: not a git repo, no commits yet, or the file has
    never been committed.  Raises ``RuntimeError`` on unexpected git
    failures.
    """
    # Check if the file exists in HEAD.
    result = effects.run(
        ["git", "cat-file", "-e", "HEAD:.selfdoc/manifest.json"],
        cwd=dir_path,
        capture_output=True,
        timeout=10,
        read=True,
    )
    if result.returncode == 128:
        # Not a git repo, or no commits yet (HEAD doesn't resolve).
        return None
    if result.returncode == 1:
        # File does not exist in HEAD (never committed).
        return None
    if result.returncode != 0:
        raise RuntimeError(
            f"Unexpected git error (exit {result.returncode}): "
            f"{result.stderr.decode().strip()}"
        )

    # Read the file contents from HEAD.
    result = effects.run(
        ["git", "show", "HEAD:.selfdoc/manifest.json"],
        cwd=dir_path,
        capture_output=True,
        timeout=10,
        read=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to read manifest from git: "
            f"{result.stderr.decode().strip()}"
        )

    data = json.loads(result.stdout)

    return manifest_compat(data, source="git HEAD")

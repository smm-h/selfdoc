"""Convert Markdown files to static HTML with a built-in minimal converter.

No external dependencies -- handles headings, code blocks, inline code,
paragraphs, lists, links, bold/italic, tables, blockquotes, and admonitions.
Syntax highlighting uses Pygments when available (optional dependency).
"""

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime

from selfdoc_core.address import page_address
from selfdoc_core.icons import get_icon
from selfdoc_core.prose import first_sentence
from selfdoc_core.themes import get_theme, get_theme_meta
from selfdoc_core.urls import SimpleURLBuilder
from selfdoc_core.tokenizer import (
    tokenize as tokenize_md,
    Heading as TokHeading,
    CodeBlock as TokCodeBlock,
    Table as TokTable,
    UnorderedList as TokUnorderedList,
    OrderedList as TokOrderedList,
    Blockquote as TokBlockquote,
    DefinitionList as TokDefinitionList,
    ThematicBreak as TokThematicBreak,
    BlankLine as TokBlankLine,
    Paragraph as TokParagraph,
)

# Pygments is optional: when available, code blocks get build-time syntax
# highlighting.  When missing, code blocks render as plain text.
try:
    from pygments import highlight as pygments_highlight
    from pygments.lexers import get_lexer_by_name
    from pygments.formatters import HtmlFormatter
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False

# Admonition types recognized in GitHub-flavored blockquotes (> [!TYPE])
_ADMONITION_TYPES = {"NOTE", "TIP", "WARNING", "CAUTION", "IMPORTANT"}


def _minify_js(js_text):
    """Minify JavaScript by removing comments and collapsing whitespace.

    Conservative approach: avoids breaking URLs containing ``//`` and
    preserves single spaces between identifiers.
    """
    # Remove multi-line comments /* ... */
    js_text = re.sub(r"/\*.*?\*/", "", js_text, flags=re.DOTALL)
    # Remove single-line comments (// ... to end of line) but not inside
    # strings and not URLs (https://, http://).  Only strip when //
    # appears at the start of a line or after whitespace/semicolons.
    js_text = re.sub(r"(?m)(?<=^)[ \t]*//(?!.*['\"]).*$", "", js_text)
    js_text = re.sub(r"(?m)(?<=[;{}\n])[ \t]*//(?!.*['\"]).*$", "", js_text)
    # Collapse runs of whitespace (but keep at least one space between
    # word characters so identifiers don't merge)
    js_text = re.sub(r"[ \t]+", " ", js_text)
    # Remove whitespace around structural characters
    js_text = re.sub(r"\s*([{}();,=])\s*", r"\1", js_text)
    # Strip blank lines
    js_text = re.sub(r"\n{2,}", "\n", js_text)
    js_text = js_text.strip()
    return js_text


def _slugify(text):
    """Convert heading text to a URL-friendly slug for deep linking.

    Strips HTML tags first, then: NFKD-normalize to decompose accented
    characters, strip combining marks, lowercase, spaces to hyphens,
    remove non-word characters except hyphens (preserves CJK/Cyrillic).
    """
    # Strip HTML tags (e.g. <code>, <strong>, <a>)
    text = re.sub(r"<[^>]+>", "", text)
    # Decompose accented characters and strip combining marks
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    text = text.replace(" ", "-")
    text = re.sub(r"[^\w-]", "", text)
    # Collapse multiple hyphens
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def get_css(theme_name="minimal"):
    """Return the CSS content for the named theme.

    Args:
        theme_name: Name of the theme to load (default "minimal").

    Returns:
        The CSS content as a string.
    """
    return get_theme(theme_name)


def _flatten_dark_css(dark_rules):
    """Convert dark mode CSS rules to flat selectors.

    Pygments ``get_style_defs`` returns rules like ``.code-block code .hll { ... }``.
    We need to wrap each rule individually for both ``@media`` and ``[data-theme]``
    contexts instead of nesting them (which is invalid CSS without native nesting).
    """
    rules = re.findall(r'([^{]+)\{([^}]+)\}', dark_rules)
    media_lines = []
    attr_lines = []
    for selector, body in rules:
        selector = selector.strip()
        media_lines.append(
            f"  :root:not([data-theme='light']) {selector} {{ {body.strip()} }}"
        )
        attr_lines.append(
            f"[data-theme='dark'] {selector} {{ {body.strip()} }}"
        )
    media_block = (
        "@media (prefers-color-scheme: dark) {\n"
        + "\n".join(media_lines)
        + "\n}"
    )
    attr_block = "\n".join(attr_lines)
    return f"{media_block}\n\n{attr_block}"


def generate_pygments_css(light_style="default", dark_style="monokai"):
    """Generate Pygments CSS rules for light and dark mode.

    Args:
        light_style: Pygments style name for light mode.
        dark_style: Pygments style name for dark mode.

    Scoped to ``.code-block code`` to match the HTML structure produced
    by ``_render_code_block()``.

    Returns the CSS string, or an empty string if Pygments is not installed.
    """
    if not HAS_PYGMENTS:
        return ""
    scope = ".code-block code"
    light = HtmlFormatter(style=light_style).get_style_defs(scope)
    dark = HtmlFormatter(style=dark_style).get_style_defs(scope)
    dark_css = _flatten_dark_css(dark)
    return f"{light}\n\n{dark_css}"


def _generate_hero_html(branding, project_name, config_description, nav_items):
    """Generate the hero section HTML for the landing page.

    Args:
        branding: Branding config dict (must not be None).
        project_name: Project name for the hero title.
        config_description: Project-level description from config.
        nav_items: Navigation items list, used to derive default CTA link.

    Returns:
        HTML string for the hero section.
    """
    parts = []
    parts.append('<section class="hero">')
    parts.append('<div class="hero-inner">')

    # Logo
    logo = branding.get("logo")
    if logo:
        parts.append(
            f'<img class="hero-logo" src="{_escape_html(logo)}" alt="{_escape_html(project_name)} logo">'
        )

    # Title
    parts.append(
        f'<h1 class="hero-title">{_escape_html(project_name)}</h1>'
    )

    # Tagline
    tagline = branding.get("tagline")
    if tagline:
        parts.append(f'<p class="hero-tagline">{_escape_html(tagline)}</p>')

    # Description from config
    if config_description:
        parts.append(
            f'<p class="hero-description">{_escape_html(config_description)}</p>'
        )

    # CTA link: explicit or default to first non-index page in nav
    cta_link = branding.get("cta_link")
    if not cta_link:
        flat = _flatten_nav(nav_items)
        for item in flat:
            if item.get("md_path") != "index.md":
                cta_link = _html_path_to_url(item["path"])
                break
    if not cta_link:
        cta_link = "#"

    cta_text = branding.get("cta_text") or "Get Started"

    parts.append('<div class="hero-actions">')
    parts.append(
        f'<a class="hero-cta" href="{_escape_html(cta_link)}">'
        f'{_escape_html(cta_text)}</a>'
    )

    # Secondary CTA
    secondary_text = branding.get("secondary_cta_text")
    secondary_link = branding.get("secondary_cta_link")
    if secondary_text and secondary_link:
        parts.append(
            f'<a class="hero-cta hero-cta-secondary" '
            f'href="{_escape_html(secondary_link)}">'
            f'{_escape_html(secondary_text)}</a>'
        )

    parts.append('</div>')  # hero-actions
    parts.append('</div>')  # hero-inner
    parts.append('</section>')

    return "\n".join(parts)


def _generate_features_html(branding, nav_items):
    """Generate the feature grid HTML for the landing page.

    When branding.features is set, uses those explicitly. Otherwise
    auto-generates one feature card per nav group (subdirectory).

    Args:
        branding: Branding config dict (must not be None).
        nav_items: Navigation items list from _build_nav.

    Returns:
        HTML string for the feature grid, or empty string if no features.
    """
    features = branding.get("features")

    if features is None:
        # Auto-generate from nav groups
        features = []
        for item in nav_items:
            if "group" not in item:
                continue
            group_title = item["group"]
            group_items = item["items"]
            count = len(group_items)
            link = _html_path_to_url(group_items[0]["path"]) if group_items else None
            features.append({
                "title": group_title,
                "description": f"{count} page{'s' if count != 1 else ''}",
                "link": link,
            })

    if not features:
        return ""

    parts = ['<section class="feature-grid">']
    for feat in features:
        title = feat.get("title", "")
        description = feat.get("description", "")
        link = feat.get("link")

        parts.append('<div class="feature-card">')
        if link:
            parts.append(
                f'<h3 class="feature-title">'
                f'<a href="{_escape_html(link)}">'
                f'{_escape_html(title)}</a></h3>'
            )
        else:
            parts.append(
                f'<h3 class="feature-title">{_escape_html(title)}</h3>'
            )
        parts.append(
            f'<p class="feature-description">{_escape_html(description)}</p>'
        )
        parts.append('</div>')

    parts.append('</section>')
    return "\n".join(parts)


def generate_html(markdown_files, project_name=None, version=None,
                   has_custom_css=False, repo=None, docs_dir_name="docs/",
                   base_url=None, url_builder=None, frontmatter=None, lang="en",
                   page_dates=None, author=None, feed_url=None,
                   critical_css=None, twitter_site=None, search=None,
                   feedback=None, branch="main",
                   branding=None, config_description=None,
                   auto_detect=None, theme_meta=None,
                   deploy_target=None, run_button=False,
                   line_numbers=False,
                   page_nav=True, page_progress=True,
                   code_icons="colorful", glossary=True,
                   mount_locale="", mount_project="", mount_version="",
                   mount_archived=False,
                   available_versions=None, available_locales=None,
                   version_pages=None,
                   current_version="", current_locale="",
                   is_latest=True,
                   schema_types=None,
                   unversioned_pages=None, unversioned_frontmatter=None):
    """Convert Markdown files to static HTML.

    Args:
        markdown_files: Dict mapping relative paths to MD content.
        project_name: Project name for titles and sidebar.
        version: Version string for display (optional).
        has_custom_css: Whether a custom.css file exists for the project.
        repo: GitHub repo URL for "Edit this page" links (optional).
        docs_dir_name: Docs directory name for constructing source paths.
        base_url: Base URL for canonical links and sitemap (optional).
        frontmatter: Dict mapping relative paths to metadata dicts (Feature 34).
        page_dates: Dict mapping relative paths to (published, modified) tuples (optional).
        author: Author dict from config (optional, keys: name, type, url).
        feed_url: Relative URL to the Atom feed (optional, e.g. "feed.xml").
        mount_locale: Locale segment of the output mount (e.g. "en").
        mount_project: Constituent-project segment of the output mount on a
            unified site (e.g. "core"); empty on a standalone site.
        mount_version: Version these pages were built from (e.g. "0.7.0");
            empty for pages that are not version-scoped.  The current
            version carries no version segment -- see ``mount_archived``.
        mount_archived: Whether this build is a superseded version, emitted
            under ``v/<version>/`` instead of at the stable address.
        available_versions: List of version dicts for version picker (optional).
        available_locales: List of locale dicts for locale picker (optional).
        version_pages: Optional ``version -> set of html paths`` map saying
            which pages each version actually has.  The version picker
            offers a version only when it holds the page being rendered.
            ``None`` means the caller cannot tell them apart, and every
            version is offered.
        current_version: Current version being built (e.g. "0.7.0").
        current_locale: Current locale being built (e.g. "en").
        is_latest: Whether this is the latest version (default True).

    Returns:
        Dict mapping output keys (mount-prefixed .html paths) to HTML content.
    """
    if not project_name:
        project_name = "Documentation"
    if not version:
        version = ""
    if frontmatter is None:
        frontmatter = {}
    if page_dates is None:
        page_dates = {}

    # Build navigation from the file list, using frontmatter for ordering
    nav_items = _build_nav(
        markdown_files, frontmatter,
        unversioned_pages=unversioned_pages,
        unversioned_frontmatter=unversioned_frontmatter,
    )

    # Flatten nav_items for page iteration order (prev/next links)
    flat_nav = _flatten_nav(nav_items)

    # md_path -> nav group title.  The sidebar already decides which group a
    # page belongs to, and that decision is also the ``group`` search facet.
    page_group = {}
    for nav_item in nav_items:
        if "group" in nav_item:
            for sub_item in nav_item.get("items", []):
                page_group[sub_item.get("md_path", "")] = nav_item["group"]

    # Pre-compute set of all HTML paths for breadcrumb link validation
    all_html_paths = {_md_to_html_path(p) for p in markdown_files}

    # --- Pass 1: Convert and collect ---
    # For each page, convert Markdown to HTML, apply post-processing,
    # and extract <dfn> terms into a cross-site glossary. Store the
    # processed body HTML and per-page metadata for pass 2.
    page_data = []  # list of dicts with all per-page state
    site_terms = {}  # term_text_lower -> {term, page, anchor, definition}

    for page_idx, (md_path, md_content) in enumerate(
        # Iterate in nav order so prev/next matches sidebar
        [(item["md_path"], markdown_files[item["md_path"]])
         for item in flat_nav if item["md_path"] in markdown_files]
    ):
        html_path = _md_to_html_path(md_path)

        # Phase 3: validate H1 headings in Markdown source
        page_meta = frontmatter.get(md_path, {})
        _md_tokens = tokenize_md(md_content)
        h1_lines = [
            (tok.start, tok.text)
            for tok in _md_tokens
            if isinstance(tok, TokHeading) and tok.level == 1
        ]
        if len(h1_lines) > 1:
            locations = ", ".join(f"line {ln}" for ln, _ in h1_lines)
            raise RuntimeError(
                f"{md_path}: multiple H1 headings found ({locations}). "
                f"Each page must have at most one '# ' heading."
            )
        if not h1_lines and not page_meta.get("title"):
            raise RuntimeError(
                f"{md_path}: no title source found. Add a '# Heading' line "
                f"or set 'title:' in frontmatter."
            )

        # Every relative reference this page emits comes from its address.
        # Two distinct hops: `prefix` reaches this page's own mount root
        # (where its sibling pages are), `asset_prefix` reaches the output
        # root (where the shared assets are). They differ by the mount, so
        # deriving one from the other's depth is what broke asset links.
        addr = page_address(
            html_path,
            locale=mount_locale,
            project=mount_project,
            version=mount_version,
            archived=mount_archived,
        )
        prefix = addr.to_mount_root
        asset_prefix = addr.to_site_root
        # Pages marked `versioned: false` are built at the version-free
        # mount, one level shallower than this page's own.
        unversioned_prefix = addr.to_stable_mount_root
        home_href = _home_href(addr, all_html_paths)
        md_config = {}
        if auto_detect:
            md_config["auto_detect"] = auto_detect
        if run_button:
            md_config["run_button"] = True
        if line_numbers:
            md_config["line_numbers"] = True
        if code_icons != "colorful":
            md_config["code_icons"] = code_icons
        body_html = md_to_html(
            md_content,
            metadata=page_meta,
            config=md_config or None,
        )
        # Rewrite internal .md links to directory-style URLs.
        # index.md links stay as index.html; others become dir/ paths.
        body_html = re.sub(
            r'(?<!\w)index\.md"', 'index.html"', body_html,
        )
        body_html = re.sub(
            r'(\w[\w/.-]*)\.md"',
            lambda m: m.group(1) + '/"',
            body_html,
        )
        body_html = re.sub(
            r'(?<!\w)index\.md\)', 'index.html)', body_html,
        )
        body_html = re.sub(
            r'(\w[\w/.-]*)\.md\)',
            lambda m: m.group(1) + '/)',
            body_html,
        )
        nav_html = _render_nav(
            nav_items, prefix, current_path=html_path,
            unversioned_prefix=unversioned_prefix,
        )

        # Use frontmatter title if available, else extract from content
        # (Feature 34)
        title = page_meta.get("title") or _extract_title(md_content, project_name)

        # Meta description from frontmatter (Feature 34)
        description = page_meta.get("description", "")

        # Track frontmatter description for visible summary block (Phase 2.6)
        frontmatter_description = description or None

        # Truncation is abolished: a handwritten frontmatter description is a
        # complete linguistic unit and is emitted verbatim in the meta tag.
        # (The advisory SEO length lint in check.py still pressures authors to
        # keep descriptions concise -- only silent mutation was removed.)

        css_href = asset_prefix + "style.css"
        custom_css_href = (asset_prefix + "custom.css") if has_custom_css else None

        # Prev/next page links (Feature 8)
        prev_page = flat_nav[page_idx - 1] if page_idx > 0 else None
        next_page = (flat_nav[page_idx + 1]
                     if page_idx < len(flat_nav) - 1 else None)

        # Breadcrumbs (Feature 9): not shown on index.html
        breadcrumbs = None
        if html_path != "index.html":
            breadcrumbs = _build_breadcrumbs(html_path, title, prefix,
                                             all_html_paths,
                                             home_href=home_href)

        # Extract TOC from the body HTML (Feature 2)
        toc_html = _build_toc(body_html)

        # Source path for "Edit this page" link (Feature 14)
        source_path = docs_dir_name.rstrip("/") + "/" + md_path

        # Date published and modified for this page (Wave 2 date infrastructure)
        date_tuple = page_dates.get(md_path)
        date_published = date_tuple[0] if date_tuple else None
        date_modified = date_tuple[1] if date_tuple else None

        # The feed lives at the output root, not the mount root.
        page_feed_url = (asset_prefix + feed_url) if feed_url else None

        # Schema type from frontmatter (e.g. "itemlist" for ItemList JSON-LD)
        schema = page_meta.get("schema")

        # Page type from frontmatter (e.g. "post", "tutorial") for layout/SEO
        page_type = page_meta.get("type")

        # Page tags from frontmatter for SEO keywords
        _tags_val = page_meta.get("tags", [])
        if isinstance(_tags_val, str):
            _tags_val = [_tags_val] if _tags_val else []
        page_tags = list(_tags_val)

        # Landing page: inject hero + features for index.html when branding
        # is configured. The hero replaces the page summary block.
        has_hero = False
        if html_path == "index.html" and branding is not None:
            has_hero = True
            hero_html = _generate_hero_html(
                branding, project_name,
                config_description or "", nav_items,
            )
            features_html = _generate_features_html(branding, nav_items)
            landing_prefix = hero_html
            if features_html:
                landing_prefix += "\n" + features_html
            body_html = landing_prefix + "\n" + body_html
            # Suppress page summary on the landing page (hero replaces it)
            frontmatter_description = None

        # Extract <dfn> terms from processed body HTML into site_terms.
        # Glossary terms: <dt><dfn>X</dfn></dt><dd>Y</dd>
        if '<div class="glossary">' in body_html:
            for term_match in re.finditer(
                r"<dt><dfn>(.*?)</dfn></dt>\s*<dd>(.*?)</dd>", body_html,
            ):
                term_name = term_match.group(1)
                term_desc = term_match.group(2)
                key = term_name.lower()
                if key not in site_terms:
                    site_terms[key] = {
                        "term": term_name,
                        "page": html_path,
                        "anchor": _slugify(term_name),
                        "definition": term_desc,
                    }

        # Standalone <dfn> tags (from _apply_definitions, inside <p> tags)
        for p_match in re.finditer(r"<p>(.*?)</p>", body_html, re.DOTALL):
            p_content = p_match.group(1)
            dfn_match = re.search(r"<dfn>(.*?)</dfn>", p_content)
            if not dfn_match:
                continue
            # Skip if inside a glossary block
            p_start = p_match.start()
            glossary_open = body_html.rfind(
                '<div class="glossary">', 0, p_start,
            )
            if glossary_open != -1:
                glossary_close = body_html.find('</div>', glossary_open)
                if glossary_close == -1 or glossary_close > p_start:
                    continue
            raw_term = dfn_match.group(1)
            clean_name = re.sub(r"<[^>]+>", "", raw_term).strip()
            key = clean_name.lower()
            if key not in site_terms:
                clean_desc = re.sub(r"<[^>]+>", "", p_content).strip()
                site_terms[key] = {
                    "term": clean_name,
                    "page": html_path,
                    "anchor": _slugify(clean_name),
                    "definition": clean_desc,
                }

        # Store all per-page state for pass 2
        page_data.append({
            "html_path": html_path,
            "address": addr,
            "asset_prefix": asset_prefix,
            "body_html": body_html,
            "nav_html": nav_html,
            "title": title,
            "description": description,
            "frontmatter_description": frontmatter_description,
            "css_href": css_href,
            "custom_css_href": custom_css_href,
            "toc_html": toc_html,
            "breadcrumbs": breadcrumbs,
            "prev_page": prev_page,
            "next_page": next_page,
            "prefix": prefix,
            "unversioned_prefix": unversioned_prefix,
            "home_href": home_href,
            "source_path": source_path,
            "date_published": date_published,
            "date_modified": date_modified,
            "page_feed_url": page_feed_url,
            "schema": schema,
            "page_type": page_type,
            "page_tags": page_tags,
            "nav_group": page_group.get(md_path, ""),
            "page_number": page_idx + 1,
            "total_pages": len(flat_nav),
            "has_hero": has_hero,
        })

    # --- Auto-generated glossary page ---
    # If site_terms were collected from any page, synthesize a glossary
    # page so all terms appear in one alphabetically-sorted definition list.
    # Skip if the user already has a glossary.md in their docs.
    existing_html_paths = {pd["html_path"] for pd in page_data}
    if glossary and site_terms and "glossary/index.html" not in existing_html_paths:
        glossary_addr = page_address(
            "glossary/index.html",
            locale=mount_locale,
            project=mount_project,
            version=mount_version,
            archived=mount_archived,
        )
        # Build glossary body HTML
        sorted_terms = sorted(site_terms.values(), key=lambda t: t["term"].lower())
        glossary_dl_items = []
        for info in sorted_terms:
            anchor = info["anchor"]
            term_name = _escape_html(info["term"])
            definition = info["definition"]
            source_page = info["page"]
            # _html_path_to_url gives the URL relative to the mount, and the
            # glossary page sits a level inside it, so the hop back is what
            # makes a "Source" link land on the page that defined the term.
            source_url = (
                glossary_addr.to_mount_root + _html_path_to_url(source_page)
            )
            glossary_dl_items.append(
                f'<dt id="{anchor}"><dfn>{term_name}</dfn></dt>'
                f'<dd>{definition} '
                f'<a href="{source_url}">Source</a></dd>'
            )
        # The H1 is auto-generated by _wrap_page from the title "Glossary",
        # so we only need the glossary content body here.
        glossary_body = (
            '<div class="glossary"><dl>\n'
            + "\n".join(glossary_dl_items)
            + "\n</dl></div>"
        )

        # DefinedTermSet JSON-LD for the glossary page
        glossary_defined_terms = []
        for info in sorted_terms:
            glossary_defined_terms.append({
                "@type": "DefinedTerm",
                "name": info["term"],
                "description": re.sub(r"<[^>]+>", "", info["definition"]).strip(),
            })
        glossary_jsonld = {
            "@context": "https://schema.org",
            "@type": "DefinedTermSet",
            "name": f"{project_name} Glossary",
            "hasDefinedTerm": glossary_defined_terms,
        }
        glossary_jsonld_tag = (
            '<script type="application/ld+json">\n'
            + json.dumps(glossary_jsonld)
            + '\n</script>'
        )
        # Inject the JSON-LD into the body so _wrap_page's seo_tags section
        # picks it up naturally (it will be in the body, but we handle it
        # by appending after the glossary body).
        glossary_body += "\n" + glossary_jsonld_tag

        # Add "Glossary" to nav_items as a top-level link at the bottom
        glossary_nav_item = {
            "label": "Glossary",
            "path": "glossary/index.html",
            "md_path": "glossary.md",
        }
        nav_items.append(glossary_nav_item)

        # Re-render nav HTML for the glossary page and rebuild nav for
        # existing pages (since the glossary link is now in the sidebar)
        glossary_nav_html = _render_nav(
            nav_items, prefix=glossary_addr.to_mount_root,
            current_path="glossary/index.html",
            unversioned_prefix=glossary_addr.to_stable_mount_root,
        )

        # Update nav_html for all previously collected page_data entries
        for pd in page_data:
            pd["nav_html"] = _render_nav(
                nav_items, prefix=pd["prefix"],
                current_path=pd["html_path"],
                unversioned_prefix=pd["unversioned_prefix"],
            )

        # Build page_data entry for the glossary page
        glossary_toc_html = _build_toc(glossary_body)
        glossary_asset_prefix = glossary_addr.to_site_root
        page_data.append({
            "html_path": "glossary/index.html",
            "address": glossary_addr,
            "asset_prefix": glossary_asset_prefix,
            "body_html": glossary_body,
            "nav_html": glossary_nav_html,
            "title": "Glossary",
            "description": "",
            "frontmatter_description": None,
            "css_href": glossary_asset_prefix + "style.css",
            "custom_css_href": (
                (glossary_asset_prefix + "custom.css") if has_custom_css else None
            ),
            "toc_html": glossary_toc_html,
            "breadcrumbs": _build_breadcrumbs(
                "glossary/index.html", "Glossary",
                glossary_addr.to_mount_root, all_html_paths,
                home_href=_home_href(glossary_addr, all_html_paths),
            ),
            "prev_page": None,
            "next_page": None,
            "prefix": glossary_addr.to_mount_root,
            "unversioned_prefix": glossary_addr.to_stable_mount_root,
            "home_href": _home_href(glossary_addr, all_html_paths),
            "source_path": None,
            "date_published": None,
            "date_modified": None,
            "page_feed_url": (
                (glossary_asset_prefix + feed_url) if feed_url else None
            ),
            "schema": None,
            "page_type": "glossary",
            "page_tags": [],
            "nav_group": "",
        })

    # --- Pass 2: Wrap pages ---
    # Now that all pages are processed and site_terms is fully populated,
    # wrap each page in the full HTML template.
    html_files = {}
    for pd in page_data:
        full_html = _wrap_page(
            pd["body_html"], pd["nav_html"], pd["title"],
            project_name, version,
            pd["css_href"], pd["custom_css_href"],
            toc_html=pd["toc_html"],
            breadcrumbs=pd["breadcrumbs"],
            prev_page=pd["prev_page"],
            next_page=pd["next_page"],
            prefix=pd["prefix"],
            unversioned_prefix=pd["unversioned_prefix"],
            home_href=pd["home_href"],
            asset_prefix=pd["asset_prefix"],
            repo=repo,
            source_path=pd["source_path"],
            base_url=base_url,
            url_builder=url_builder,
            page_path=pd["html_path"],
            description=pd["description"],
            lang=lang,
            date_published=pd["date_published"],
            date_modified=pd["date_modified"],
            author=author,
            feed_url=pd["page_feed_url"],
            summary=pd["frontmatter_description"],
            critical_css=critical_css,
            schema=pd["schema"],
            page_type=pd.get("page_type"),
            schema_types=schema_types,
            page_tags=pd.get("page_tags"),
            twitter_site=twitter_site,
            search=search,
            feedback=feedback,
            branch=branch,
            nav_group=pd.get("nav_group", ""),
            site_terms=site_terms,
            page_number=pd.get("page_number"),
            total_pages=pd.get("total_pages"),
            theme_meta=theme_meta,
            has_hero=pd.get("has_hero", False),
            deploy_target=deploy_target,
            page_nav=page_nav,
            page_progress=page_progress,
            mount_locale=mount_locale,
            mount_project=mount_project,
            mount_version=mount_version,
            mount_archived=mount_archived,
            available_versions=available_versions,
            available_locales=available_locales,
            version_pages=version_pages,
            current_version=current_version,
            current_locale=current_locale,
            is_latest=is_latest,
        )
        # Keyed by the output key from the address, so no caller has to
        # staple the mount on afterwards.
        html_files[pd["address"].output_key] = full_html

    return html_files


def generate_404_page(project_name=None, version=None, has_custom_css=False,
                      nav_items=None, repo=None, base_url=None, url_builder=None,
                      lang="en",
                      feed_url=None, critical_css=None, theme_meta=None,
                      mount_locale="", mount_project=""):
    """Generate a custom 404 page using the standard page template (Feature 39).

    The 404 page is written at the output root, so its assets need no
    relative hop -- but the pages it links to live under a mount, and the
    mount coordinates say which one.  Every page it links to is a current
    one, so the hop is always to the stable mount: the sidebar never
    points a lost reader into an archived version.

    Returns the full HTML string for 404.html.
    """
    if not project_name:
        project_name = "Documentation"
    if not version:
        version = ""
    if nav_items is None:
        nav_items = []

    # Hop from the output root (where 404.html sits) into the stable mount,
    # where every current page lives -- version-scoped or not.
    root_addr = page_address(
        "index.html",
        locale=mount_locale,
        project=mount_project,
    )
    mount_prefix = root_addr.stable
    unversioned_prefix = mount_prefix

    # Render sidebar navigation from nav_items
    nav_html = _render_nav(nav_items, prefix=mount_prefix,
                           current_path="404.html",
                           unversioned_prefix=unversioned_prefix)

    # Search prompt button
    search_html = (
        '<p>Try searching for what you need:</p>\n'
        '<button onclick="document.getElementById(\'search-dialog\')'
        '.showModal(); var i=document.querySelector('
        '\'.pagefind-ui__search-input\'); if(i)i.focus();" '
        'style="padding: 0.5rem 1.5rem; font-size: 1rem; cursor: pointer; '
        'border: 1px solid var(--border); border-radius: 6px; '
        'background: var(--bg-secondary, #f5f5f5); '
        'color: var(--text-primary, #333);">'
        'Search documentation</button>'
    )

    # Popular pages section (first 5 nav items, flattened)
    flat_nav = _flatten_nav(nav_items)
    popular_html = ""
    if flat_nav:
        popular_links = []
        for item in flat_nav[:5]:
            item_prefix = (
                unversioned_prefix if item.get("unversioned") else mount_prefix
            )
            popular_links.append(
                f'<li><a href="{item_prefix}{_html_path_to_url(item["path"])}">'
                f'{_escape_html(item["label"])}</a></li>'
            )
        popular_html = (
            '\n<h2>Popular pages</h2>\n'
            '<ul>\n' + "\n".join(popular_links) + '\n</ul>'
        )

    # The H1 is auto-generated by _wrap_page from the title.
    body_html = (
        '<p>The page you are looking for does not exist.</p>\n'
        f'<p><a href="{mount_prefix}index.html">Go to the homepage</a></p>\n'
        + search_html
        + popular_html
    )
    title = "Page not found"

    return _wrap_page(
        body_html, nav_html, title, project_name, version,
        css_href="style.css",
        custom_css_href="custom.css" if has_custom_css else None,
        prefix=mount_prefix,
        unversioned_prefix=unversioned_prefix,
        asset_prefix="",
        base_url=base_url,
        url_builder=url_builder,
        page_path=None,
        lang=lang,
        feed_url=feed_url,
        critical_css=critical_css,
        theme_meta=theme_meta,
    )


@dataclass(frozen=True, slots=True)
class HeadingAnchor:
    """One heading and the element id it will carry on the built page.

    ``index`` is the heading's position in the token list it came from,
    so a renderer walking the same tokens can look its anchor up.
    """

    index: int
    level: int
    text: str
    anchor: str
    is_page_title: bool


def page_title_anchor(title):
    """The element id the page-title H1 carries.

    Part of the anchor authority: the page title is rendered as an H1 by
    :func:`_wrap_page` rather than by the body renderer, so both sides ask
    this function instead of slugifying the title themselves.  Like every
    other heading, the title is slugified from its *rendered* inline form,
    so ``# The `build` command`` anchors the same way whether the words
    reach the page through frontmatter or through markdown.
    """
    return _slugify(_inline_format(title))


def assign_heading_anchors(tokens, page_title=None):
    """Assign the final element id to every heading in *tokens*.

    This is the one place heading anchors are decided.  The HTML renderer
    emits these ids and the search index links to them, so the two cannot
    drift: a repeated heading gets ``setup``, ``setup-1``, ``setup-2`` in
    both.  Because the input is the block token list, a ``#``-prefixed
    line inside a fenced code block is code and never becomes an anchor.

    The first H1 is not rendered in the body -- ``_wrap_page`` emits it as
    the page title heading, whose id comes from the page title.  Pass
    *page_title* (frontmatter title, else the H1 text) to get that id
    right; it is reported with ``is_page_title=True``.

    Returns a list of ``HeadingAnchor``, in document order.
    """
    seen_slugs = {}  # base slug -> how many times it has been used
    page_title_consumed = False
    anchors = []

    for index, token in enumerate(tokens):
        if not isinstance(token, TokHeading):
            continue

        if token.level == 1 and not page_title_consumed:
            page_title_consumed = True
            title = page_title if page_title is not None else token.text
            anchors.append(HeadingAnchor(
                index=index,
                level=token.level,
                text=token.text,
                anchor=page_title_anchor(title),
                is_page_title=True,
            ))
            continue

        slug = _slugify(_inline_format(token.text))
        if slug in seen_slugs:
            seen_slugs[slug] += 1
            slug = f"{slug}-{seen_slugs[slug]}"
        else:
            seen_slugs[slug] = 0
        anchors.append(HeadingAnchor(
            index=index,
            level=token.level,
            text=token.text,
            anchor=slug,
            is_page_title=False,
        ))

    return anchors


def _render_heading(token, heading_anchor):
    """Render a Heading token to HTML.

    Returns the HTML string, or None for the first H1 (which is consumed
    as the page title by _wrap_page).  *heading_anchor* is this token's
    entry from ``assign_heading_anchors``.
    """
    if heading_anchor.is_page_title:
        return None
    content = _inline_format(token.text)
    slug = heading_anchor.anchor
    readable = re.sub(r"<[^>]+>", "", content).replace("_", " ")
    anchor = (
        f'<a class="heading-link" href="#{slug}"'
        f' aria-label="Link to section: {_escape_html(readable)}">#</a>'
    )
    return f'<h{token.level} id="{slug}">{anchor}{content}</h{token.level}>'


def _render_table(token, tokens, idx):
    """Render a Table token to HTML, wrapped in .table-wrap with caption."""
    table_html = _parse_table(token.rows)
    # Add caption from most recent heading for accessibility
    caption_text = ""
    for prev_idx in range(idx - 1, -1, -1):
        prev_tok = tokens[prev_idx]
        if isinstance(prev_tok, TokHeading):
            # Get plain text from heading (apply inline format then strip tags)
            rendered = _inline_format(prev_tok.text)
            caption_text = re.sub(r"<[^>]+>", "", rendered).strip()
            break
    if caption_text:
        table_html = table_html.replace(
            "<table>",
            f'<table><caption class="sr-only">'
            f"{_escape_html(caption_text)}</caption>",
            1,
        )
    return (
        '<div class="table-wrap">'
        + table_html
        + '</div>'
    )


def _render_definition_list(token):
    """Render a DefinitionList token to HTML."""
    dl_items = []
    for term, defs in token.entries:
        term_html = _inline_format(term)
        dl_items.append(f"<dt><dfn>{term_html}</dfn></dt>")
        for defn_text in defs:
            dl_items.append(f"<dd>{_inline_format(defn_text)}</dd>")
    return (
        '<div class="glossary">\n<dl>\n'
        + "\n".join(dl_items)
        + "\n</dl>\n</div>"
    )


def _render_block(token, tokens, idx, heading_anchors,
                  run_button=False, line_numbers=False, code_icons="colorful"):
    """Dispatch a single block token to its HTML renderer.

    *heading_anchors* maps a token index to its ``HeadingAnchor`` (from
    ``assign_heading_anchors``).

    Returns the HTML string, or None if the token produces no output
    (e.g. BlankLine, or the first H1).
    """
    if isinstance(token, TokHeading):
        return _render_heading(token, heading_anchors[idx])

    if isinstance(token, TokCodeBlock):
        # Per-block run annotation or global run_button config
        block_run = token.run or run_button
        # Per-block line numbers annotation or global line_numbers config
        block_line_numbers = token.line_numbers or line_numbers
        return _render_code_block(
            token.lang, token.lines, token.annotations, run=block_run,
            line_numbers=block_line_numbers, line_start=token.line_start,
            code_icons=code_icons,
        )

    if isinstance(token, TokTable):
        return _render_table(token, tokens, idx)

    if isinstance(token, TokUnorderedList):
        items = "".join(
            f"<li>{_inline_format(item)}</li>" for item in token.items
        )
        return f"<ul>{items}</ul>"

    if isinstance(token, TokOrderedList):
        items = "".join(
            f"<li>{_inline_format(item)}</li>" for item in token.items
        )
        return f"<ol>{items}</ol>"

    if isinstance(token, TokBlockquote):
        return _parse_blockquote(token.lines)

    if isinstance(token, TokDefinitionList):
        return _render_definition_list(token)

    if isinstance(token, TokThematicBreak):
        return "<hr>"

    if isinstance(token, TokBlankLine):
        return None

    if isinstance(token, TokParagraph):
        para_content = _inline_format(" ".join(token.lines))
        return f"<p>{para_content}</p>"

    return None


def md_to_html(text, metadata=None, config=None):
    """Convert Markdown text to HTML.

    Handles: headings, code blocks (with tabs and annotations), inline code,
    paragraphs, unordered lists, ordered lists, links, bold, italic, tables.

    Args:
        text: Markdown source text.
        metadata: Per-page frontmatter dict (optional). Keys ``auto_steps``
            and ``auto_api`` (bool) override the corresponding global
            settings from *config*.
        config: Project config dict (optional). The ``auto_detect`` key
            (an object with optional bool keys ``steps`` and
            ``api_entries``) controls whether heuristics run globally.
            Per-page *metadata* takes precedence over global config.
    """
    tokens = tokenize_md(text)
    html_parts = []
    # The single heading scan: ids come from here, and the search index
    # reads the same assignment from the same tokens.
    heading_anchors = {
        ha.index: ha for ha in assign_heading_anchors(tokens)
    }
    cfg_run_button = config.get("run_button", False) if config else False
    cfg_line_numbers = config.get("line_numbers", False) if config else False
    cfg_code_icons = config.get("code_icons", "colorful") if config else "colorful"

    for idx, token in enumerate(tokens):
        rendered = _render_block(
            token, tokens, idx, heading_anchors,
            run_button=cfg_run_button,
            line_numbers=cfg_line_numbers,
            code_icons=cfg_code_icons,
        )
        if rendered is not None:
            html_parts.append(rendered)

    result = "\n".join(html_parts)

    # Post-process: group consecutive code blocks into tabs (Feature 31)
    result = _group_code_tabs(result)

    # Post-process: add class="steps" to <ol> after step/guide/tutorial
    # headings (Feature 33).  Skipped when opted out via frontmatter
    # (auto_steps: false) or global config (auto_detect.steps: false).
    auto_detect = config.get("auto_detect", {}) if config else {}
    auto_steps_global = auto_detect.get("steps", True) if auto_detect else True
    auto_steps_page = metadata.get("auto_steps") if metadata else None
    run_steps = auto_steps_page if auto_steps_page is not None else auto_steps_global
    if run_steps:
        result = _apply_step_guides(result)

    # Post-process: wrap h3/h4 + code block + description in API entry
    # cards (Feature 48).  Skipped when opted out via frontmatter
    # (auto_api: false) or global config (auto_detect.api_entries: false).
    auto_api_global = auto_detect.get("api_entries", False) if auto_detect else False
    auto_api_page = metadata.get("auto_api") if metadata else None
    run_api = auto_api_page if auto_api_page is not None else auto_api_global
    if run_api:
        result = _wrap_api_entries(result)

    # Post-process: auto-detect definitional patterns after headings and
    # wrap the subject in <dfn> tags (Phase 6A)
    result = _apply_definitions(result)

    # Post-process: mark the first image as high-priority LCP candidate
    # (Phase 3.3). All images start with loading="lazy" from _inline_format;
    # promote the first one to eager loading with high fetchpriority.
    result = re.sub(
        r'loading="lazy"',
        'fetchpriority="high" loading="eager"',
        result,
        count=1,
    )

    return result


def _render_code_block(lang, code_lines, annotations=None, run=False,
                       line_numbers=False, line_start=1, code_icons="colorful"):
    """Render a single fenced code block to HTML.

    Handles diff highlighting (Feature 27), inline code annotations
    (Feature 32), build-time syntax highlighting via Pygments
    (Wave 3 Phase 0), optional line numbers, and language icons.
    """
    if annotations is None:
        annotations = {}

    # Diff-style line highlighting (Feature 27)
    is_diff = lang == "diff" or any(
        cl.startswith("+") or cl.startswith("-")
        for cl in code_lines
    )

    if is_diff:
        code_content = _render_diff_lines(code_lines)
    elif HAS_PYGMENTS and lang:
        # Build-time syntax highlighting via Pygments.  The formatter
        # uses nowrap=True so we keep our own <pre><code> wrapper.
        # Pygments handles HTML escaping internally.
        try:
            lexer = get_lexer_by_name(lang)
            formatter = HtmlFormatter(nowrap=True)
            code_content = pygments_highlight(
                "\n".join(code_lines), lexer, formatter
            )
            # pygments_highlight appends a trailing newline; strip it so
            # we don't get an extra blank line inside <code>.
            code_content = code_content.rstrip("\n")
        except Exception:
            # Unknown language or Pygments error -- fall back to plain text
            code_content = _escape_html("\n".join(code_lines))
    else:
        code_content = _escape_html("\n".join(code_lines))

    # Replace annotation markers // [N] or # [N] with badge elements
    # (Feature 32)
    if annotations:
        for num, note in annotations.items():
            escaped_note = _escape_html(note)
            badge = (
                f'<span class="code-annotation" data-note="{escaped_note}" '
                f'tabindex="0">{_escape_html(num)}</span>'
            )
            # Match escaped marker patterns in the code content
            # The markers were already HTML-escaped, so match escaped forms
            code_content = code_content.replace(
                f"// [{_escape_html(num)}]", badge
            )
            code_content = code_content.replace(
                f"# [{_escape_html(num)}]", badge
            )

    # Wrap each line in a <span class="code-line"> for line numbers
    if line_numbers and not is_diff:
        wrapped_lines = []
        for raw_line in code_content.split("\n"):
            wrapped_lines.append(f'<span class="code-line">{raw_line}</span>')
        code_content = "\n".join(wrapped_lines)

    run_attr = ' data-run="true"' if run else ""
    has_ln = line_numbers and not is_diff
    ln_class = " has-line-numbers" if has_ln else ""
    ln_attr = f' data-line-start="{line_start}"' if has_ln else ""
    # Inline counter-reset so line numbering starts at the right value.
    # counter-reset sets the initial value; counter-increment fires
    # before display, so reset to (line_start - 1).
    ln_style = f' style="counter-reset:line-number {line_start - 1}"' if has_ln else ""
    if lang:
        escaped_lang = _escape_html(lang)
        icon_svg = get_icon(lang, code_icons) if code_icons != "none" else None
        icon_html = icon_svg + " " if icon_svg else ""
        label = f'<div class="code-label">{icon_html}{escaped_lang}</div>'
        return (
            f'<div class="code-block{ln_class}"{run_attr}>{label}'
            f'<pre tabindex="0" aria-label="Code: {escaped_lang}"{ln_attr}>'
            f'<code class="language-{escaped_lang}"{ln_style}>'
            f"{code_content}</code></pre></div>"
        )
    return (
        f'<div class="code-block{ln_class}"{run_attr}>'
        f'<pre tabindex="0" aria-label="Code block"{ln_attr}>'
        f'<code{ln_style}>{code_content}</code></pre>'
        f'</div>'
    )


_RE_CODE_BLOCK_WITH_LABEL = re.compile(
    r'<div class="code-block"[^>]*><div class="code-label">'
)


def _group_code_tabs(html):
    """Group consecutive code blocks into a tabbed interface (Feature 31).

    Detects runs of consecutive <div class="code-block"> elements (with
    different language labels) and wraps them in a tab container.
    Only groups blocks that have language labels.
    """
    parts = html.split("\n")
    result = []
    i = 0

    while i < len(parts):
        part = parts[i]
        # Check if this is a code block with a language label
        if _RE_CODE_BLOCK_WITH_LABEL.search(part):
            # Collect consecutive code blocks with language labels
            group = [part]
            j = i + 1
            while j < len(parts) and _RE_CODE_BLOCK_WITH_LABEL.search(parts[j]):
                group.append(parts[j])
                j += 1

            if len(group) >= 2:
                # Build tabbed interface
                tabs = []
                panels = []
                for idx, block_html in enumerate(group):
                    # Extract language text from the code-label div.
                    # The label may contain an SVG icon before the text,
                    # so we match the last text node (after any SVG).
                    label_match = re.search(
                        r'<div class="code-label">(?:<svg[^>]*>.*?</svg>\s*)?([^<]+)</div>',
                        block_html,
                        re.DOTALL,
                    )
                    lang = label_match.group(1).strip() if label_match else f"Tab {idx + 1}"
                    lang_id = lang.lower().replace(" ", "-")
                    active = " active" if idx == 0 else ""
                    selected = "true" if idx == 0 else "false"
                    escaped_lang_id = _escape_html(lang_id)
                    tabs.append(
                        f'<button class="tab{active}" '
                        f'role="tab" '
                        f'id="tab-{escaped_lang_id}" '
                        f'aria-selected="{selected}" '
                        f'aria-controls="panel-{escaped_lang_id}" '
                        f'data-lang="{escaped_lang_id}">'
                        f'{_escape_html(lang)}</button>'
                    )
                    panels.append(
                        f'<div class="tab-panel{active}" '
                        f'role="tabpanel" '
                        f'id="panel-{escaped_lang_id}" '
                        f'aria-labelledby="tab-{escaped_lang_id}" '
                        f'data-lang="{escaped_lang_id}">'
                        f'{block_html}</div>'
                    )
                tab_bar = '<div class="tab-bar" role="tablist">' + "".join(tabs) + '</div>'
                result.append(
                    '<div class="code-tabs">'
                    + tab_bar
                    + "".join(panels)
                    + '</div>'
                )
                i = j
            else:
                result.append(part)
                i += 1
        else:
            result.append(part)
            i += 1

    return "\n".join(result)


def _apply_step_guides(html):
    """Add class="steps" to <ol> elements that follow step/guide/tutorial
    headings (Feature 33).

    Uses a two-pass approach: finds each <ol> without a class, then searches
    backward (up to 200 characters) for an h2/h3 whose plain text starts with
    "step", "guide", or "tutorial" (case-insensitive). If found with no
    intervening h2/h3 between the match and the <ol>, adds class="steps".
    """
    # Matches any h2/h3 heading
    any_heading_re = re.compile(r'<h[23]\s[^>]*>.*?</h[23]>', re.IGNORECASE)
    # Pattern to strip HTML tags for plain-text extraction
    strip_tags_re = re.compile(r'<[^>]+>')
    # Keyword must be the first word of the heading's plain text
    kw_start_re = re.compile(r'^(step|guide|tutorial)\b', re.IGNORECASE)
    # Match <ol> tags without an existing class attribute
    ol_re = re.compile(r'<ol(?!\s[^>]*class=)(?:\s[^>]*)?>|<ol>')

    result = html
    offset = 0
    while True:
        ol_match = ol_re.search(result, offset)
        if not ol_match:
            break
        ol_start = ol_match.start()
        # Search backward up to 200 characters for a keyword heading
        lookback_start = max(0, ol_start - 200)
        preceding = result[lookback_start:ol_start]
        # Find all headings in the preceding text, then filter by keyword
        all_headings = list(any_heading_re.finditer(preceding))
        kw_matches = []
        for m in all_headings:
            heading_html = m.group(0)
            # Extract text between opening and closing tags
            inner_start = heading_html.index('>') + 1
            inner_end = heading_html.rindex('<')
            inner_html = heading_html[inner_start:inner_end]
            plain_text = strip_tags_re.sub('', inner_html).lstrip('#').strip()
            if kw_start_re.search(plain_text):
                kw_matches.append(m)
        if not kw_matches:
            offset = ol_match.end()
            continue
        # Use the last keyword heading found
        last_kw = kw_matches[-1]
        # Check for any intervening h2/h3 between the keyword heading and <ol>
        between = preceding[last_kw.end():]
        intervening = any_heading_re.search(between)
        if intervening:
            offset = ol_match.end()
            continue
        # Add class="steps" to this <ol>
        old_tag = ol_match.group(0)
        if old_tag == "<ol>":
            new_tag = '<ol class="steps">'
        else:
            new_tag = old_tag.replace("<ol", '<ol class="steps"', 1)
        result = result[:ol_start] + new_tag + result[ol_match.end():]
        offset = ol_start + len(new_tag)

    return result


def _wrap_api_entries(html):
    """Wrap h3/h4 + code block + description paragraph in API entry cards
    (Feature 48).

    When an h3 or h4 heading is followed by a code-block div (a function/type
    signature) and a <p> (description), with optional whitespace/newlines
    between them, wrap them together in a <div class="api-entry">.

    Guards:
    - Only wraps when the heading text looks like an identifier (snake_case,
      camelCase, PascalCase, dotted.method), not natural-language headings.
    - Only wraps when the code block is short (at most 2 newlines / 3 lines),
      indicating a signature rather than example code.
    """
    _strip_tags_re = re.compile(r'<[^>]+>')
    _identifier_re = re.compile(r'^[A-Za-z_][A-Za-z0-9_.]*(\(.*\))?$')
    pattern = re.compile(
        r'(<h[34]\s[^>]*>.*?</h[34]>)\s*'
        r'(<div class="code-block">.*?</div>)\s*'
        r'(<p>.*?</p>)',
        re.DOTALL,
    )
    result = []
    last_end = 0
    for m in pattern.finditer(html):
        heading_html = m.group(1)
        code_block = m.group(2)

        # Extract heading plain text (strip HTML tags)
        inner_start = heading_html.index('>') + 1
        inner_end = heading_html.rindex('<')
        inner_html = heading_html[inner_start:inner_end]
        plain_text = _strip_tags_re.sub('', inner_html).lstrip('#').strip()

        # Guard: heading must look like an identifier
        if not _identifier_re.match(plain_text):
            continue

        # Guard: code block must be short (at most 3 lines / 2 newlines)
        if code_block.count('\n') > 2:
            continue

        result.append(html[last_end:m.start()])
        result.append(
            '<div class="api-entry">'
            + m.group(1) + '\n' + m.group(2) + '\n' + m.group(3)
            + '</div>'
        )
        last_end = m.end()
    result.append(html[last_end:])
    return ''.join(result)


def _apply_definitions(html):
    """Wrap definitional subjects in <dfn> tags when they follow headings.

    Detects patterns like "X is a ...", "X refers to ...", "X means ...",
    "X represents ...", or the inverted "A/An X is ..." in the first <p>
    after an <h2> or <h3> heading, and wraps X in <dfn>.
    """
    # Match: <h2/h3 ...>...</h2/h3> followed by optional whitespace then <p>
    # that starts with a definitional pattern.
    #
    # The subject (X) can be:
    #   - Plain text (one or more words)
    #   - Wrapped in <code>...</code>
    #   - Wrapped in <strong>...</strong>
    #
    # Definitional verbs: "is a", "is an", "is the", "refers to",
    # "means", "represents"

    # Pattern for the subject: plain words, or <code>...</code>,
    # or <strong>...</strong>
    subject_plain = r"[A-Za-z][A-Za-z0-9 ]*?"
    subject_code = r"<code>[^<]+</code>"
    subject_strong = r"<strong>[^<]+</strong>"
    subject = rf"(?:{subject_code}|{subject_strong}|{subject_plain})"

    # Definitional verbs
    direct_verb = r"(?:is\s+(?:a|an|the)\b|refers\s+to\b|means\b|represents\b)"

    # Inverted form: "A/An Subject verb ..."
    inverted_pattern = (
        rf"(<h[23]\s[^>]*>.*?</h[23]>)\n"
        rf"<p>(?:A|An)\s+({subject})\s+({direct_verb})"
    )

    # Direct form pattern (excludes "A/An " starts to avoid overlap)
    direct_pattern = (
        rf"(<h[23]\s[^>]*>.*?</h[23]>)\n"
        rf"<p>(?!An?\s)({subject})\s+({direct_verb})"
    )

    def _wrap_subject(match_obj, inverted=False):
        heading = match_obj.group(1)
        subject_text = match_obj.group(2)
        verb = match_obj.group(3)

        # Wrap subject in <dfn>. If it's inside <code> or <strong>,
        # wrap the outer tag.
        dfn_subject = f"<dfn>{subject_text}</dfn>"

        if inverted:
            # Determine original article from context
            # Re-read the full match to get the article
            full = match_obj.group(0)
            article = "An" if full.startswith(heading + "\n<p>An ") else "A"
            return f"{heading}\n<p>{article} <dfn>{subject_text}</dfn> {verb}"
        return f"{heading}\n<p>{dfn_subject} {verb}"

    # Apply inverted form first (more specific), then direct form
    result = re.sub(inverted_pattern, lambda m: _wrap_subject(m, inverted=True), html)
    result = re.sub(direct_pattern, lambda m: _wrap_subject(m, inverted=False), result)

    return result


def _split_table_cells(line):
    """Split a markdown table line by unescaped pipes, unescaping \\| in cells."""
    # Strip leading/trailing whitespace
    stripped = line.strip()
    # Remove leading pipe if present
    if stripped.startswith("|"):
        stripped = stripped[1:]
    # Remove trailing pipe if present (but not a trailing \|)
    if stripped.endswith("|") and not stripped.endswith("\\|"):
        stripped = stripped[:-1]
    # Split on unescaped pipes and unescape \| in each cell
    parts = re.split(r"(?<!\\)\|", stripped)
    return [p.strip().replace("\\|", "|") for p in parts]


def _parse_table(table_lines):
    """Parse markdown table lines into an HTML <table>.

    Expects lines like:
        | Header1 | Header2 |
        | ------- | ------- |
        | Cell1   | Cell2   |

    The separator line (containing only |, -, :, and spaces) is detected
    and used to separate header from body rows. Alignment markers (:)
    in the separator produce text-align styles on cells. Escaped pipes
    (\\|) in cell content are treated as literal pipe characters.
    """
    if not table_lines:
        return ""

    rows = []
    for line in table_lines:
        cells = _split_table_cells(line)
        rows.append(cells)

    # Detect separator row (all cells match /^:?-+:?$/ or are empty)
    separator_idx = None
    for idx, row in enumerate(rows):
        if all(re.match(r"^:?-+:?$", cell) or cell == "" for cell in row):
            separator_idx = idx
            break

    # Extract alignment from separator cells
    alignments = []
    if separator_idx is not None:
        for cell in rows[separator_idx]:
            if cell == "":
                alignments.append(None)
            elif cell.startswith(":") and cell.endswith(":"):
                alignments.append("center")
            elif cell.startswith(":"):
                alignments.append("left")
            elif cell.endswith(":"):
                alignments.append("right")
            else:
                alignments.append(None)

    def _th(content, col_idx):
        if col_idx < len(alignments) and alignments[col_idx]:
            return f'<th style="text-align: {alignments[col_idx]}">{_inline_format(content)}</th>'
        return f"<th>{_inline_format(content)}</th>"

    def _td(content, col_idx):
        if col_idx < len(alignments) and alignments[col_idx]:
            return f'<td style="text-align: {alignments[col_idx]}">{_inline_format(content)}</td>'
        return f"<td>{_inline_format(content)}</td>"

    html = "<table>\n"

    if separator_idx is not None and separator_idx > 0:
        # Rows before separator are headers
        html += "<thead>\n"
        for row in rows[:separator_idx]:
            html += "<tr>" + "".join(_th(c, i) for i, c in enumerate(row)) + "</tr>\n"
        html += "</thead>\n"
        # Rows after separator are body
        html += "<tbody>\n"
        for row in rows[separator_idx + 1:]:
            html += "<tr>" + "".join(_td(c, i) for i, c in enumerate(row)) + "</tr>\n"
        html += "</tbody>\n"
    else:
        # No separator: all rows are body
        html += "<tbody>\n"
        for row in rows:
            html += "<tr>" + "".join(f"<td>{_inline_format(c)}</td>" for c in row) + "</tr>\n"
        html += "</tbody>\n"

    html += "</table>"
    return html


def _parse_blockquote(bq_lines):
    """Parse blockquote lines, detecting admonitions.

    If the first line matches [!TYPE] where TYPE is a recognized admonition,
    render as a styled admonition div. Otherwise render as a plain blockquote.
    """
    if not bq_lines:
        return ""

    # Check for admonition pattern: [!NOTE], [!WARNING], etc.
    admonition_match = re.match(r"^\[!(\w+)\]\s*$", bq_lines[0].strip())
    if admonition_match:
        admonition_type = admonition_match.group(1).upper()
        if admonition_type in _ADMONITION_TYPES:
            # Remaining lines are the admonition body
            body_lines = bq_lines[1:]
            # Skip leading empty lines
            while body_lines and not body_lines[0].strip():
                body_lines.pop(0)
            body_md = "\n".join(body_lines)
            # Convert body to inline-formatted paragraphs
            body_parts = []
            for para in body_md.split("\n\n"):
                para = para.strip()
                if para:
                    body_parts.append(f"<p>{_inline_format(para)}</p>")
            body_html = "\n".join(body_parts) if body_parts else ""
            title = admonition_type.capitalize()
            css_class = admonition_type.lower()
            return (
                f'<div class="admonition {css_class}">\n'
                f'<p class="admonition-title">{title}</p>\n'
                f'{body_html}\n'
                f'</div>'
            )

    # Plain blockquote
    content = _inline_format(" ".join(line for line in bq_lines if line.strip()))
    return f"<blockquote><p>{content}</p></blockquote>"


def _render_diff_lines(code_lines):
    """Render code lines with diff-style highlighting.

    Lines starting with '+' get class "line-add", lines starting with '-'
    get class "line-remove". Other lines get a plain "line" span.
    """
    parts = []
    for line in code_lines:
        escaped = _escape_html(line)
        if line.startswith("+"):
            parts.append(f'<span class="line line-add">{escaped}</span>')
        elif line.startswith("-"):
            parts.append(f'<span class="line line-remove">{escaped}</span>')
        else:
            parts.append(f'<span class="line">{escaped}</span>')
    return "\n".join(parts)


def _inline_format(text):
    """Apply inline formatting: links, bold, italic, inline code."""
    # Inline code first (protect from other transformations)
    parts = []
    segments = text.split("`")
    for idx, seg in enumerate(segments):
        if idx % 2 == 1:
            # Inside backticks -- render as code, no further processing
            parts.append(f"<code>{_escape_html(seg)}</code>")
        else:
            # Outside backticks -- apply other inline formatting
            formatted = seg
            # Images: ![alt](src) -- must come before links
            formatted = re.sub(
                r"!\[([^\]]*)\]\(([^)]+)\)",
                r'<img src="\2" alt="\1" loading="lazy">',
                formatted,
            )
            # Links: [text](url)
            formatted = re.sub(
                r"\[([^\]]+)\]\(([^)]+)\)",
                r'<a href="\2">\1</a>',
                formatted,
            )
            # Inline stat/data markup: ==value== -> <data value="value">value</data>
            formatted = re.sub(
                r"==([^=]+?)==",
                r'<data value="\1">\1</data>',
                formatted,
            )
            # Bold: **text**
            formatted = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", formatted)
            # Italic: *text*
            formatted = re.sub(r"\*(.+?)\*", r"<em>\1</em>", formatted)
            parts.append(formatted)
    return "".join(parts)


def _apply_cross_page_terms(body_html, site_terms, current_page, prefix):
    """Link the first occurrence of each cross-page term in body HTML.

    For every term defined on a DIFFERENT page, finds the first occurrence
    in *body_html* that is NOT inside ``<a>``, ``<code>``, ``<pre>``,
    ``<dfn>``, ``<dt>``, or ``<h1>``-``<h6>`` tags, and wraps it in an
    ``<a class="term-link">`` pointing to the definition page.

    Only the first match per term is linked to avoid link spam.
    """
    if not site_terms:
        return body_html

    # Tags whose content must be skipped
    _SKIP_TAGS = {"a", "code", "pre", "dfn", "dt", "h1", "h2", "h3", "h4", "h5", "h6"}

    # Collect terms defined on other pages, sorted longest-first so longer
    # multi-word terms match before shorter substrings.
    cross_terms = [
        info for info in site_terms.values()
        if info["page"] != current_page
    ]
    cross_terms.sort(key=lambda t: -len(t["term"]))

    for info in cross_terms:
        term_text = info["term"]
        target_page = info["page"]
        anchor = info["anchor"]

        # Both current_page and target_page are mount-relative html_paths,
        # so the target is reached through this page's own hop to the
        # mount root -- which the caller already has from the address.
        href = f"{prefix}{_html_path_to_url(target_page)}#{anchor}"

        # Page title for the tooltip: derive from target_page filename
        target_slug = _html_to_md_path(target_page).replace(".md", "")
        page_title = target_slug.replace("-", " ").replace("_", " ").title()

        # Build a pattern that matches the term text (case-insensitive for
        # the first character so "resolver" matches "Resolver"), but only
        # outside of HTML tags we want to skip.
        # Strategy: walk the HTML splitting on tags, only replace in text
        # segments that are not inside a skipped tag.
        result_parts = []
        replaced = False
        # Track nesting of skipped tags
        # Split HTML into tags and text segments
        segments = re.split(r"(<[^>]+>)", body_html)
        skip_stack = []

        for segment in segments:
            if replaced:
                result_parts.append(segment)
                continue

            if segment.startswith("<"):
                # Check if this is an opening or closing tag
                close_match = re.match(r"^</(\w+)", segment)
                open_match = re.match(r"^<(\w+)", segment)
                if close_match:
                    tag_name = close_match.group(1).lower()
                    if skip_stack and skip_stack[-1] == tag_name:
                        skip_stack.pop()
                elif open_match:
                    tag_name = open_match.group(1).lower()
                    # Self-closing tags (like <br/>, <img/>) don't need tracking
                    if tag_name in _SKIP_TAGS and not segment.endswith("/>"):
                        skip_stack.append(tag_name)
                result_parts.append(segment)
                continue

            # Text segment -- only replace if not inside a skipped tag
            if skip_stack:
                result_parts.append(segment)
                continue

            # Try to find the term in this text segment (case-insensitive
            # match but preserve original casing in the link text)
            pattern = re.compile(re.escape(term_text), re.IGNORECASE)
            match = pattern.search(segment)
            if match:
                original_text = match.group(0)
                escaped_title = _escape_html(f"Defined in: {page_title}")
                link = (
                    f'<a href="{href}" class="term-link" '
                    f'title="{escaped_title}">{original_text}</a>'
                )
                # Replace only the first occurrence
                new_segment = segment[:match.start()] + link + segment[match.end():]
                result_parts.append(new_segment)
                replaced = True
                continue

            result_parts.append(segment)

        if replaced:
            body_html = "".join(result_parts)

    return body_html


def _escape_html(text):
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _md_to_html_path(md_path):
    """Convert a .md path to a directory-index HTML path.

    ``guide.md`` becomes ``guide/index.html`` (served as ``/guide/``).
    ``index.md`` stays ``index.html`` (root page, not ``index/index.html``).
    Subdirectory pages follow the same rule: ``api/endpoints.md`` becomes
    ``api/endpoints/index.html``.
    """
    stem = md_path[:-3] if md_path.endswith(".md") else md_path
    if stem == "index":
        return "index.html"
    return f"{stem}/index.html"


def _html_path_to_url(html_path):
    """Convert an HTML file path to its clean URL form.

    ``guide/index.html`` becomes ``guide/``.
    ``index.html`` stays ``index.html`` (root page).
    Used for link hrefs, canonical URLs, and sitemap entries.
    """
    if html_path == "index.html":
        return "index.html"
    if html_path.endswith("/index.html"):
        return html_path[: -len("index.html")]
    return html_path


def _html_to_md_path(html_path):
    """Reverse of ``_md_to_html_path``: convert HTML path back to .md path.

    ``guide/index.html`` becomes ``guide.md``.
    ``index.html`` becomes ``index.md``.
    ``api/endpoints/index.html`` becomes ``api/endpoints.md``.
    """
    if html_path == "index.html":
        return "index.md"
    if html_path.endswith("/index.html"):
        stem = html_path[: -len("/index.html")]
        return f"{stem}.md"
    # Fallback for non-directory paths
    return html_path.replace(".html", ".md")


def _home_href(addr, own_pages):
    """Document-relative href to the home page, seen from *addr*'s page.

    ``own_pages`` is the set of HTML paths this build emits under the
    same mount.  Two cases, decided by what exists:

    * The mount has its own ``index.html``.  Home is that page -- an
      archive page's home is the same archived version's index, so a
      reader browsing v0.1.0 stays in v0.1.0.
    * It does not, which is what a build of only the site-level or
      ``versioned: false`` pages looks like.  Home is the current
      version's index at the stable mount, which every build writes.
    """
    if "index.html" in own_pages:
        return addr.to_mount_root + "index.html"
    stable_home = page_address(
        "index.html", locale=addr.locale, project=addr.project,
    ).stable
    return addr.to_site_root + stable_home + "index.html"


def _build_nav(markdown_files, frontmatter=None,
               unversioned_pages=None, unversioned_frontmatter=None):
    """Build navigation items from the markdown file list.

    Sorts by frontmatter 'order' (lower = first), then alphabetically
    (Feature 35). Index.md is always first regardless of order.

    Pages in subdirectories are grouped under collapsible nav groups.
    Group title defaults to the titlecased directory name but can be
    overridden via ``nav_group`` frontmatter.  ``nav_order`` frontmatter
    controls sort order within a group (default 0, ties broken
    alphabetically).

    When ``unversioned_pages`` is provided (a dict of md_path -> content),
    those pages are appended as a "General" nav group at the end.  This
    is used by versioned builds to include persistent unversioned pages
    in the sidebar navigation.

    Returns list of dicts.  Ungrouped items:
        {"label": str, "path": str, "md_path": str}
    Group items:
        {"group": str, "slug": str, "items": [ungrouped-style dicts]}
    """
    if frontmatter is None:
        frontmatter = {}

    # Collect all items with their metadata
    ungrouped = []  # top-level pages (no subdirectory)
    groups = {}     # dir_name -> list of item dicts

    for md_path in markdown_files:
        meta = frontmatter.get(md_path, {})
        label = meta.get("title") or md_path.replace(".md", "").replace("/", " / ")
        item = {
            "label": label,
            "path": _md_to_html_path(md_path),
            "md_path": md_path,
        }

        # Determine group membership
        parts = md_path.split("/")
        if len(parts) > 1:
            # Subdirectory page -- group by first directory component
            dir_name = parts[0]
            # nav_group frontmatter overrides group title
            group_title = meta.get("nav_group") or dir_name.replace(
                "-", " ").replace("_", " ").title()
            nav_order = meta.get("nav_order", 0)
            if not isinstance(nav_order, (int, float)):
                nav_order = 0
            item["_nav_order"] = nav_order

            if dir_name not in groups:
                groups[dir_name] = {"title": group_title, "items": []}
            # If a later page overrides the group title, update it
            if meta.get("nav_group"):
                groups[dir_name]["title"] = meta["nav_group"]
            groups[dir_name]["items"].append(item)
        else:
            # Top-level page
            order = meta.get("order")
            if isinstance(order, (int, float)):
                item["_sort_key"] = (0, order, md_path)
            else:
                item["_sort_key"] = (1, 0, md_path)
            ungrouped.append(item)

    # Sort ungrouped: index.md always first, then by order/alpha
    nav = []
    # Pull out index.md
    index_item = None
    rest = []
    for item in ungrouped:
        if item["md_path"] == "index.md":
            index_item = item
        else:
            rest.append(item)

    if index_item:
        index_item["label"] = "Home"
        nav.append(index_item)

    rest.sort(key=lambda x: x["_sort_key"])
    nav.extend(rest)

    # Clean up internal sort keys
    for item in nav:
        item.pop("_sort_key", None)

    # Build sorted groups: groups sorted alphabetically by group title
    sorted_group_keys = sorted(
        groups.keys(), key=lambda k: groups[k]["title"].lower()
    )

    for dir_name in sorted_group_keys:
        group_data = groups[dir_name]
        # Sort items within group by nav_order then alphabetically
        group_data["items"].sort(
            key=lambda x: (x.get("_nav_order", 0), x["md_path"])
        )
        # Clean up internal keys
        for item in group_data["items"]:
            item.pop("_nav_order", None)
            item.pop("_sort_key", None)

        slug = re.sub(r"[^a-z0-9]+", "-", group_data["title"].lower()).strip("-")
        nav.append({
            "group": group_data["title"],
            "slug": slug,
            "items": group_data["items"],
        })

    # Append unversioned pages as persistent nav groups at the end.
    # Used by versioned builds so that unversioned pages appear in
    # the sidebar regardless of which version is selected.
    # Posts (type: post) are separated into their own "Posts" group,
    # sorted by date descending (newest first).
    if unversioned_pages:
        uv_fm = unversioned_frontmatter or {}
        uv_items = []
        post_items = []
        for md_path in sorted(unversioned_pages.keys()):
            meta = uv_fm.get(md_path, {})
            label = meta.get("title") or md_path.replace(".md", "").replace("/", " / ")
            nav_order = meta.get("nav_order", 0)
            if not isinstance(nav_order, (int, float)):
                nav_order = 0
            item = {
                "label": label,
                "path": _md_to_html_path(md_path),
                "md_path": md_path,
                "unversioned": True,
                "_nav_order": nav_order,
                "_date": str(meta.get("date", "")),
            }
            if meta.get("type") == "post":
                post_items.append(item)
            else:
                uv_items.append(item)

        # Posts group: sorted by date descending (newest first)
        if post_items:
            post_items.sort(key=lambda x: x["_date"], reverse=True)
            for item in post_items:
                item.pop("_nav_order", None)
                item.pop("_date", None)
            nav.append({
                "group": "Posts",
                "slug": "posts",
                "items": post_items,
                "unversioned": True,
            })

        # General group: non-post unversioned pages
        if uv_items:
            uv_items.sort(key=lambda x: (x.get("_nav_order", 0), x["md_path"]))
            for item in uv_items:
                item.pop("_nav_order", None)
                item.pop("_date", None)
            nav.append({
                "group": "General",
                "slug": "general",
                "items": uv_items,
                "unversioned": True,
            })

    return nav


def _flatten_nav(nav_items):
    """Flatten grouped nav items into a simple page list.

    Groups are expanded in order so that prev/next links work across
    group boundaries.  Returns a list of dicts with ``label``, ``path``,
    and ``md_path`` keys (no group wrappers).
    """
    flat = []
    for item in nav_items:
        if "group" in item:
            flat.extend(item["items"])
        else:
            flat.append(item)
    return flat


def _render_nav(nav_items, prefix, current_path="", *, unversioned_prefix):
    """Render the sidebar navigation HTML.

    Ungrouped items render as flat ``<li><a>`` elements.  Grouped items
    render inside ``<details>/<summary>`` wrappers with a
    ``nav-group`` class.  The group containing the active page gets the
    ``open`` attribute so it auto-expands.

    Link hrefs use clean directory URLs (e.g. ``guide/`` instead of
    ``guide/index.html``).

    Two hops, because the sidebar spans two mounts: *prefix* reaches the
    rendering page's own mount, and *unversioned_prefix* reaches the
    version-free mount where every item carrying the ``unversioned``
    marker was built.  Inside a version those differ by one level, and
    addressing an unversioned page with the versioned hop names a file
    no build ever writes.
    """
    items_html = []
    for item in nav_items:
        if "group" in item:
            # Check if the active page is in this group
            is_active_group = any(
                sub["path"] == current_path for sub in item["items"]
            )
            open_attr = " open" if is_active_group else ""
            sub_items = []
            for sub in item["items"]:
                sub_prefix = (
                    unversioned_prefix if sub.get("unversioned") else prefix
                )
                href = sub_prefix + _html_path_to_url(sub["path"])
                active_cls = (
                    ' class="active"' if sub["path"] == current_path else ""
                )
                sub_items.append(
                    f'<li><a href="{href}"{active_cls}>'
                    f'{_escape_html(sub["label"])}</a></li>'
                )
            items_html.append(
                f'<li class="nav-group">'
                f'<details{open_attr}>'
                f'<summary class="nav-group-title">'
                f'{_escape_html(item["group"])}</summary>'
                f'<ul class="nav-group-items">'
                f'{"".join(sub_items)}'
                f'</ul>'
                f'</details>'
                f'</li>'
            )
        else:
            item_prefix = (
                unversioned_prefix if item.get("unversioned") else prefix
            )
            href = item_prefix + _html_path_to_url(item["path"])
            active_cls = (
                ' class="active"' if item["path"] == current_path else ""
            )
            items_html.append(
                f'<li><a href="{href}"{active_cls}>'
                f'{_escape_html(item["label"])}</a></li>'
            )
    return "".join(items_html)


def _extract_title(md_content, fallback):
    """Extract the first H1 heading from markdown content as the page title."""
    tokens = tokenize_md(md_content)
    for tok in tokens:
        if isinstance(tok, TokHeading) and tok.level == 1:
            return tok.text
    return fallback


def _extract_first_paragraph(body_html):
    """Extract the text of the first ``<p>`` element from rendered HTML.

    Returns the plain text (tags stripped) or an empty string if no
    paragraph is found.
    """
    match = re.search(r"<p>(.*?)</p>", body_html, re.DOTALL)
    if not match:
        return ""
    # Strip any inline HTML tags to get plain text
    text = re.sub(r"<[^>]+>", "", match.group(1))
    return text.strip()


def _build_toc(body_html):
    """Extract h2/h3 headings from body HTML and build a TOC nested list.

    Returns HTML string for the TOC, or empty string if fewer than 2 headings.
    """
    headings = re.findall(
        r'<(h[23])\s+id="([^"]+)">[^<]*(?:<[^>]+>[^<]*)*?'
        r'<a[^>]*class="heading-link"[^>]*>[^<]*</a>(.*?)</\1>',
        body_html,
    )
    if len(headings) < 2:
        return ""

    items = []
    for tag, slug, text in headings:
        # Strip any remaining HTML tags from the heading text
        clean_text = re.sub(r"<[^>]+>", "", text).strip()
        level = tag  # "h2" or "h3"
        indent_cls = " toc-h3" if level == "h3" else ""
        items.append(
            f'<li class="toc-item{indent_cls}">'
            f'<a href="#{slug}">{_escape_html(clean_text)}</a></li>'
        )

    return '<nav class="toc-nav" aria-label="Table of contents"><ul>' + "\n".join(items) + "</ul></nav>"


def _build_breadcrumbs(html_path, page_title, prefix, existing_pages=None,
                       *, home_href):
    """Build breadcrumb HTML for a non-index page.

    For flat pages like ``guide.html``, produces ``Home / Guide``.
    For subdirectory pages like ``api/endpoints.html``, produces
    ``Home / Api / Endpoints`` with intermediate directory links.
    If an intermediate directory index page does not exist in
    *existing_pages*, the segment is rendered as a ``<span>``
    instead of a link.

    Args:
        html_path: The current page's html path (e.g. "guide.html"
            or "api/endpoints.html").
        page_title: The page title extracted from the first heading.
        prefix: Relative hop to this page's own mount root, used for the
            intermediate directory crumbs (which are pages of this mount).
        existing_pages: Optional set of HTML paths that actually exist.
        home_href: Href for the "Home" crumb, from :func:`_home_href` --
            not every mount has an index page of its own.

    Returns:
        Breadcrumb HTML string.
    """
    if existing_pages is None:
        existing_pages = set()
    # With directory-index URLs, html_path is e.g. "guide/index.html" or
    # "api/endpoints/index.html".  Strip the trailing /index.html to get
    # the logical path segments for breadcrumb construction.
    logical_path = html_path
    if logical_path.endswith("/index.html"):
        logical_path = logical_path[: -len("/index.html")]
    parts = logical_path.split("/")
    crumbs = [f'<a href="{home_href}">Home</a>']
    # Add intermediate directory breadcrumbs
    for i, dir_name in enumerate(parts[:-1]):
        dir_path = "/".join(parts[:i + 1])
        label = _escape_html(dir_name.capitalize())
        target = f'{dir_path}/index.html'
        if target in existing_pages:
            crumbs.append(f'<a href="{prefix}{_html_path_to_url(target)}">{label}</a>')
        else:
            crumbs.append(f'<span>{label}</span>')
    # Final segment is the current page (no link)
    crumbs.append(f'<span>{_escape_html(page_title)}</span>')
    return (
        '<nav class="breadcrumbs" aria-label="Breadcrumbs">'
        + " / ".join(crumbs)
        + '</nav>'
    )


def _render_seo_tags(title, base_url, page_path, description, body_html,
                     author, project_name, repo, date_published,
                     date_modified, lang, breadcrumbs, schema,
                     twitter_site, deploy_target,
                     available_locales=None, current_locale="",
                     mount_locale="", mount_project="", mount_version="",
                     url_builder=None,
                     page_type=None, schema_types=None,
                     page_tags=None):
    """Build SEO tags: JSON-LD structured data, OG meta, canonical, hreflang, security."""
    if url_builder is None and base_url is not None:
        url_builder = SimpleURLBuilder(base_url)
    seo_tags = ""
    escaped_title = _escape_html(title)
    escaped_project = _escape_html(project_name)
    # The canonical is the stable address, from every version including the
    # archived ones: one page, one canonical URL, and an archived copy tells
    # a crawler which address supersedes it.
    if page_path:
        page_url = page_address(
            page_path,
            locale=mount_locale,
            project=mount_project,
            version=mount_version,
        ).stable
        canonical_url = (
            url_builder.page_url(page_url)
            if url_builder
            else f"{base_url}/{page_url}"
        )
    else:
        canonical_url = None

    # TechArticle JSON-LD -- emitted when page_path is set
    if page_path:
        # Build author object for TechArticle
        if author and author.get("name"):
            author_obj = {
                "@type": author.get("type") or "Organization",
                "name": author["name"],
            }
            if author.get("url"):
                author_obj["url"] = author["url"]
        else:
            author_obj = {"@type": "Organization", "name": project_name}

        # Resolve schema.org @type from page type via schema_types mapping
        _default_schema_types = {
            "guide": "TechArticle",
            "tutorial": "TechArticle",
            "post": "BlogPosting",
            "changelog": "WebPage",
        }
        _merged = dict(_default_schema_types)
        if schema_types:
            _merged.update(schema_types)
        schema_type = _merged.get(page_type or "guide", "Article")

        ld_obj = {
            "@context": "https://schema.org",
            "@type": schema_type,
            "headline": title,
            "author": author_obj,
        }
        if canonical_url:
            ld_obj["url"] = canonical_url
        if description:
            ld_obj["description"] = description
        if date_modified:
            ld_obj["dateModified"] = date_modified
            ld_obj["datePublished"] = date_published or date_modified

        # Publisher must always be an Organization per Google's spec
        if author and author.get("type") == "Organization":
            ld_obj["publisher"] = author_obj
        else:
            ld_obj["publisher"] = {
                "@type": "Organization",
                "name": project_name,
            }

        ld_obj["inLanguage"] = lang

        # BlogPosting: add keywords from frontmatter tags
        if schema_type == "BlogPosting" and page_tags:
            ld_obj["keywords"] = ", ".join(page_tags)

        seo_tags += (
            f'\n<script type="application/ld+json">\n'
            f'{json.dumps(ld_obj)}'
            f'\n</script>'
        )

    # BreadcrumbList JSON-LD for non-index pages
    if breadcrumbs and page_path:
        def _crumb_url(crumb_page_path):
            """Absolute URL for a crumb, at its stable address.

            Structured data names the address a crawler should keep, which
            is the stable one -- the same address this page's canonical
            points at, archived copy or not.
            """
            stable = page_address(
                crumb_page_path,
                locale=mount_locale,
                project=mount_project,
            ).stable
            if url_builder:
                return url_builder.page_url(stable)
            return f"{base_url}/{stable}"

        items = [{
            "@type": "ListItem",
            "position": 1,
            "name": "Home",
            "item": _crumb_url("index.html"),
        }]
        # Use logical path (strip trailing /index.html) for breadcrumb
        logical_page_path = page_path
        if logical_page_path.endswith("/index.html"):
            logical_page_path = logical_page_path[: -len("/index.html")]
        parts = logical_page_path.split("/")
        # Intermediate directory entries
        for i, dir_name in enumerate(parts[:-1]):
            dir_path = "/".join(parts[:i + 1])
            entry = {
                "@type": "ListItem",
                "position": len(items) + 1,
                "name": dir_name.capitalize(),
                "item": _crumb_url(f"{dir_path}/index.html"),
            }
            items.append(entry)
        # Final page entry (no item URL per Google spec)
        items.append({
            "@type": "ListItem",
            "position": len(items) + 1,
            "name": title,
        })
        breadcrumb_ld = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": items,
        }
        seo_tags += (
            f'\n<script type="application/ld+json">\n'
            f'{json.dumps(breadcrumb_ld)}'
            f'\n</script>'
        )

    # WebSite JSON-LD on the homepage.  It carries no SearchAction: that
    # node advertised a ?q= URL pattern which serves the same page for every
    # query, so it published a duplicate-content address for each search term
    # and pointed crawlers at it.  The site's search is client-side and has no
    # crawlable result URL to advertise.
    if page_path == "index.html":
        website_ld = {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": project_name,
            "url": url_builder.page_url("") if url_builder else f"{base_url}/",
        }
        seo_tags += (
            f'\n<script type="application/ld+json">\n'
            f'{json.dumps(website_ld)}'
            f'\n</script>'
        )

    # Standalone Organization/Person JSON-LD on homepage
    if page_path == "index.html":
        # Use Person schema when author.type is "Person"
        entity_type = "Organization"
        if author and author.get("type") == "Person":
            entity_type = "Person"

        entity_name = project_name
        if entity_type == "Person" and author and author.get("name"):
            entity_name = author["name"]

        org_ld = {
            "@context": "https://schema.org",
            "@type": entity_type,
            "name": entity_name,
        }
        # Determine URL: prefer author URL, fall back to base_url
        if author and author.get("url"):
            org_ld["url"] = author["url"]
        else:
            org_ld["url"] = url_builder.base() if url_builder else base_url

        # sameAs: collect social profile URLs
        same_as = []
        if author:
            twitter_handle = author.get("twitter")
            if twitter_handle:
                handle = twitter_handle.lstrip("@")
                same_as.append(f"https://twitter.com/{handle}")
        if same_as:
            org_ld["sameAs"] = same_as

        seo_tags += (
            f'\n<script type="application/ld+json">\n'
            f'{json.dumps(org_ld)}'
            f'\n</script>'
        )

    # SoftwareSourceCode JSON-LD when code blocks with language annotations exist
    lang_matches = re.findall(r'class="language-(\w+)"', body_html)
    if lang_matches:
        unique_langs = list(dict.fromkeys(lang_matches))
        prog_lang = unique_langs[0] if len(unique_langs) == 1 else unique_langs
        source_code_ld = {
            "@context": "https://schema.org",
            "@type": "SoftwareSourceCode",
            "name": title,
            "programmingLanguage": prog_lang,
        }
        if repo:
            source_code_ld["codeRepository"] = repo
        seo_tags += (
            f'\n<script type="application/ld+json">\n'
            f'{json.dumps(source_code_ld)}'
            f'\n</script>'
        )

    # DefinedTermSet JSON-LD from glossary blocks and standalone <dfn> tags
    defined_terms = []
    seen_names = set()

    # 1. Glossary terms: <dt><dfn>X</dfn></dt><dd>Y</dd>
    if '<div class="glossary">' in body_html:
        dfn_terms = re.findall(
            r"<dt><dfn>(.*?)</dfn></dt>\s*<dd>(.*?)</dd>",
            body_html,
        )
        for term_name, term_desc in dfn_terms:
            if term_name not in seen_names:
                seen_names.add(term_name)
                defined_terms.append({
                    "@type": "DefinedTerm",
                    "name": term_name,
                    "description": term_desc,
                })

    # 2. Standalone <dfn> tags from _apply_definitions (inside <p> tags,
    #    outside glossary blocks). Extract term and containing paragraph.
    for p_match in re.finditer(r"<p>(.*?)</p>", body_html, re.DOTALL):
        p_content = p_match.group(1)
        dfn_match = re.search(r"<dfn>(.*?)</dfn>", p_content)
        if not dfn_match:
            continue
        # Skip if this <p> is inside a glossary block
        p_start = p_match.start()
        # Find the last glossary-open before this <p>
        glossary_open = body_html.rfind('<div class="glossary">', 0, p_start)
        if glossary_open != -1:
            glossary_close = body_html.find('</div>', glossary_open)
            if glossary_close == -1 or glossary_close > p_start:
                continue  # inside a glossary block
        term_name = dfn_match.group(1)
        # Strip HTML tags from term name (e.g. <code>, <strong>)
        clean_name = re.sub(r"<[^>]+>", "", term_name).strip()
        if clean_name in seen_names:
            continue
        seen_names.add(clean_name)
        # Use full paragraph text (stripped of HTML) as description
        clean_desc = re.sub(r"<[^>]+>", "", p_content).strip()
        defined_terms.append({
            "@type": "DefinedTerm",
            "name": clean_name,
            "description": clean_desc,
        })

    if defined_terms:
        term_set_ld = {
            "@context": "https://schema.org",
            "@type": "DefinedTermSet",
            "name": f"{title} Glossary",
            "hasDefinedTerm": defined_terms,
        }
        seo_tags += (
            f'\n<script type="application/ld+json">\n'
            f'{json.dumps(term_set_ld)}'
            f'\n</script>'
        )

    # ItemList auto-detection: if schema is not set and the page is
    # list-heavy (more <li> than <p>, with at least 5 <li>), auto-set
    # schema to trigger ItemList JSON-LD.
    if not schema:
        li_count = body_html.count('<li>')
        p_count = body_html.count('<p>')
        if li_count > p_count and li_count >= 5:
            schema = "itemlist"

    # ItemList JSON-LD when frontmatter schema == "itemlist"
    if schema == "itemlist":
        li_matches = re.findall(r"<li>(.*?)</li>", body_html)
        if li_matches:
            item_list_elements = []
            for pos, li_content in enumerate(li_matches, start=1):
                # Strip HTML tags from each list item
                plain_text = re.sub(r"<[^>]+>", "", li_content).strip()
                entry = {
                    "@type": "ListItem",
                    "position": pos,
                    "name": plain_text,
                }
                # Extract URL from <a href="..."> if present
                href_match = re.search(r'<a\s+href="([^"]+)"', li_content)
                if href_match:
                    entry["item"] = href_match.group(1)
                item_list_elements.append(entry)
            item_list_ld = {
                "@context": "https://schema.org",
                "@type": "ItemList",
                "itemListElement": item_list_elements,
            }
            seo_tags += (
                f'\n<script type="application/ld+json">\n'
                f'{json.dumps(item_list_ld)}'
                f'\n</script>'
            )

    # OG tags -- emitted when page_path exists
    if page_path:
        # Fall back to the auto-extracted first sentence when description is
        # empty (a complete, naturally bounded unit -- matches the meta tag).
        og_description = description or first_sentence(
            _extract_first_paragraph(body_html)
        )
        escaped_desc = _escape_html(og_description)
        og_desc_tag = (
            f'\n<meta property="og:description" content="{escaped_desc}">'
            if og_description else ""
        )
        twitter_desc_tag = (
            f'\n<meta name="twitter:description" content="{escaped_desc}">'
            if og_description else ""
        )

        twitter_card_type = "summary_large_image"

        og_type = "website" if page_path == "index.html" else "article"
        twitter_site_tag = (
            f'\n<meta name="twitter:site" content="{_escape_html(twitter_site)}">'
            if twitter_site else ""
        )

        # og:locale -- map lang code to locale string
        _LANG_TO_LOCALE = {
            "en": "en_US", "es": "es_ES", "fr": "fr_FR", "de": "de_DE",
            "it": "it_IT", "pt": "pt_BR", "ja": "ja_JP", "ko": "ko_KR",
            "zh": "zh_CN", "ru": "ru_RU", "ar": "ar_SA", "fa": "fa_IR",
            "nl": "nl_NL", "pl": "pl_PL", "tr": "tr_TR", "sv": "sv_SE",
        }
        effective_lang = lang if lang else "en"
        og_locale = _LANG_TO_LOCALE.get(
            effective_lang,
            f"{effective_lang}_{effective_lang.upper()}",
        )

        seo_tags += (
            f'\n<meta property="og:title" content="{escaped_title}'
            f' - {escaped_project}">'
            f'\n<meta property="og:type" content="{og_type}">'
            f'\n<meta property="og:site_name" content="{escaped_project}">'
            f'\n<meta property="og:locale" content="{og_locale}">'
            f'{og_desc_tag}'
            f'\n<meta name="twitter:card" content="{twitter_card_type}">'
            f'\n<meta name="twitter:title" content="{escaped_title}'
            f' - {escaped_project}">'
            f'{twitter_desc_tag}'
            f'{twitter_site_tag}'
        )

        slug = _html_to_md_path(page_path).replace(".md", "")
        # og:image:alt -- use description if available, otherwise title
        og_image_alt = _escape_html(description if description else title)
        og_image_url = url_builder.asset_url(f"og-{slug}.png") if url_builder else f"{base_url}/og-{slug}.png"
        seo_tags += (
            f'\n<meta property="og:image" content="{og_image_url}">'
            f'\n<meta property="og:image:type" content="image/png">'
            f'\n<meta property="og:image:width" content="1200">'
            f'\n<meta property="og:image:height" content="630">'
            f'\n<meta property="og:image:alt" content="{og_image_alt}">'
            f'\n<meta property="og:url" content="{canonical_url}">'
            f'\n<meta name="twitter:image" content="{og_image_url}">'
        )

    # Canonical URL -- needs base_url
    if canonical_url:
        seo_tags += f'\n<link rel="canonical" href="{canonical_url}">'

    # hreflang tags -- only when multiple locales are configured
    if available_locales and len(available_locales) > 1 and page_path and base_url:
        def _locale_href(code):
            """This same page's stable address in another locale."""
            stable = page_address(
                page_path,
                locale=code,
                project=mount_project,
            ).stable
            if url_builder:
                return url_builder.page_url(stable)
            return f"{base_url}/{stable}"

        default_locale_code = None
        for loc in available_locales:
            code = loc["code"]
            if loc.get("default") is True:
                default_locale_code = code
            seo_tags += (
                f'\n<link rel="alternate" hreflang="{code}" '
                f'href="{_locale_href(code)}">'
            )

        # x-default points to the default locale (or first locale)
        if default_locale_code is None:
            default_locale_code = available_locales[0]["code"]
        seo_tags += (
            f'\n<link rel="alternate" hreflang="x-default" '
            f'href="{_locale_href(default_locale_code)}">'
        )

    # Security meta tags for GitHub Pages (Phase 7.1)
    # Cloudflare Pages uses _headers file instead; HSTS and Permissions-Policy
    # are not supported as meta tags.
    security_meta = ""
    if deploy_target == "github-pages":
        security_meta = (
            '\n<meta http-equiv="X-Content-Type-Options" content="nosniff">'
            '\n<meta http-equiv="X-Frame-Options" content="DENY">'
            '\n<meta http-equiv="Content-Security-Policy" content="'
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self'"
            '">'
        )

    return seo_tags, security_meta


def _render_page_footer(edit_link_html, date_display_html,
                        feedback_html, page_nav_html):
    """Assemble the page footer from edit link, dates, feedback, and nav."""
    footer_parts = []
    meta_parts = []
    if edit_link_html:
        meta_parts.append(edit_link_html)
    if date_display_html:
        meta_parts.append(f'Last updated {date_display_html}')
    if meta_parts:
        footer_parts.append(
            f'<div class="page-meta">{"".join("<span>" + p + "</span>" for p in meta_parts)}</div>'
        )
    footer_parts.append(feedback_html)
    if page_nav_html:
        footer_parts.append(page_nav_html)
    return (
        f'<footer class="page-footer">'
        f'{"".join(footer_parts)}'
        f'</footer>'
    )


def _page_href(addr, target):
    """Document-relative href from *addr*'s page to another emitted address.

    Both sides come from the addressing authority: ``to_site_root`` walks
    out to the output root and the target's own emitted URL walks back in,
    so the link is correct under every mount point.  An empty result means
    "this same directory", which is written ``./`` rather than ``""``.
    """
    return (addr.to_site_root + target.url) or "./"


def _render_version_picker(addr, available_versions, version_pages):
    """Build the version picker for a version-scoped page.

    Every option carries the href the browser should go to, computed here
    from the addressing authority: the current version's option addresses
    the stable page, an older version's option addresses its archive copy.
    Nothing is left for the client to work out from ``location.pathname``,
    which was only ever right when the site was served from an origin root.

    ``version_pages`` maps a version to the set of page paths it has; a
    version that does not have this page is not offered, because the link
    would point at a file no build wrote.  ``None`` means the caller cannot
    distinguish them and every version is offered.
    """
    if not available_versions or not addr.version:
        return ""
    latest_version = available_versions[-1]["version"]
    options = []
    for entry in available_versions:
        ver = entry["version"]
        if version_pages is not None:
            if addr.page_path not in version_pages.get(ver, set()):
                continue
        target = page_address(
            addr.page_path,
            locale=addr.locale,
            project=addr.project,
            version=ver,
            archived=(ver != latest_version),
        )
        selected = " selected" if ver == addr.version else ""
        options.append(
            f'<option value="{_escape_html(ver)}"'
            f' data-href="{_escape_html(_page_href(addr, target))}"'
            f'{selected}>v{_escape_html(ver)}</option>'
        )
    if len(options) <= 1:
        return ""
    return (
        '<select class="version-picker" aria-label="Documentation version">\n'
        + "\n".join(options)
        + "\n</select>\n"
    )


def _render_locale_picker(addr, available_locales, current_locale):
    """Build the locale picker, with a server-side href per locale.

    Rendered only for a genuinely multi-locale site: with one locale there
    is no locale segment in any address and nothing for the control to
    switch between.
    """
    if not available_locales or len(available_locales) <= 1:
        return ""
    options = []
    for loc in available_locales:
        code = loc["code"]
        target = page_address(
            addr.page_path,
            locale=code,
            project=addr.project,
            version=addr.version,
            archived=addr.archived,
        )
        selected = " selected" if code == current_locale else ""
        options.append(
            f'<option value="{_escape_html(code)}"'
            f' data-href="{_escape_html(_page_href(addr, target))}"'
            f'{selected}>{_escape_html(loc["label"])}</option>'
        )
    return (
        '<select class="locale-picker" aria-label="Language">\n'
        + "\n".join(options)
        + "\n</select>\n"
    )


def _render_version_notice(addr):
    """Build the "this is a superseded version" notice for an archive page.

    Rendered server-side, dismissable, and the dismissal is keyed per
    version: dismissing the notice on v0.1.0 says nothing about v0.2.0, so
    a reader who lands on a different old version is told again.
    """
    if not addr.archived:
        return ""
    current = page_address(
        addr.page_path, locale=addr.locale, project=addr.project,
    )
    href = _page_href(addr, current)
    ver = _escape_html(addr.version)
    return (
        f'<div class="version-notice" role="note" data-notice-key="{ver}">'
        f'<p>You are reading v{ver} of this page, which has been superseded. '
        f'<a href="{href}">Go to the current version</a>.</p>'
        f'<button type="button" class="version-notice-dismiss"'
        f' aria-label="Dismiss this notice">Dismiss</button>'
        f'</div>'
    )


def _render_share_control(addr, url_builder, base_url):
    """Build the share control for a version-scoped page.

    Explicit choices, never one guessed for the reader: the evergreen
    address, which always shows the current version, and -- on an archive
    page -- the pinned address, which always shows this exact version.
    Both are absolute -- a shared link leaves the site -- so they come
    from the URL builder rather than from a relative hop.

    The pinned choice is offered only where the pinned address is a page
    this build wrote.  The current version is emitted at the stable
    address and nowhere else: its ``v/<version>/`` address is where it
    *will* live once a newer version supersedes it, so offering it today
    would hand the reader a 404.  A control that offers a dead address is
    worse than one that offers fewer, so the current version offers the
    evergreen address alone -- which, for it, is the address it is served
    at anyway.
    """
    if not addr.version:
        return ""

    def _absolute(path):
        if url_builder:
            return url_builder.page_url(path)
        if base_url:
            return f"{base_url}/{path}"
        return ""

    evergreen = _absolute(addr.stable)
    if not evergreen:
        return ""
    choices = [
        (evergreen, "Evergreen link (always current)"),
    ]
    if addr.archived:
        pinned = _absolute(addr.pinned)
        if not pinned:
            return ""
        choices.append((pinned, f"Pinned link (v{_escape_html(addr.version)})"))
    buttons = "".join(
        f'<button type="button" class="share-address-copy"'
        f' data-share-url="{_escape_html(url)}">{label}</button>'
        for url, label in choices
    )
    return (
        '<div class="share-address">'
        '<span class="share-address-label">Share this page</span>'
        f'{buttons}'
        '</div>'
    )


def _render_topbar(project_name, version_badge, topbar_page_title_html,
                   search_trigger_html, home_href,
                   version_picker_html="", locale_picker_html=""):
    """Build the topbar header with hamburger, project name, theme toggle, search.

    ``home_href`` is where the site-name link points -- the home page as
    seen from the rendering page, which is not always this mount's own
    index (see :func:`_home_href`).  The two pickers are rendered by
    :func:`_render_version_picker` and :func:`_render_locale_picker`,
    which is where their links are decided.
    """
    # Theme toggle SVG icons (Feature 6)
    sun_icon = (
        '<svg class="icon-sun" width="18" height="18" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="5"/>'
        '<line x1="12" y1="1" x2="12" y2="3"/>'
        '<line x1="12" y1="21" x2="12" y2="23"/>'
        '<line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>'
        '<line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>'
        '<line x1="1" y1="12" x2="3" y2="12"/>'
        '<line x1="21" y1="12" x2="23" y2="12"/>'
        '<line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>'
        '<line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>'
        '</svg>'
    )
    moon_icon = (
        '<svg class="icon-moon" width="18" height="18" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>'
        '</svg>'
    )
    auto_icon = (
        '<svg class="icon-auto" width="18" height="18" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="M12 2a10 10 0 0 1 0 20z" fill="currentColor"/>'
        '</svg>'
    )

    return (
        f'<header class="topbar">\n'
        f'<div class="topbar-inner">\n'
        f'<button class="hamburger" aria-label="Toggle navigation" aria-expanded="false">\n'
        f'<span></span><span></span><span></span>\n'
        f'</button>\n'
        f'<a class="project-name" href="{home_href}">{_escape_html(project_name)}</a>\n'
        f'{version_badge}\n'
        f'{version_picker_html}'
        f'{locale_picker_html}'
        f'{topbar_page_title_html}\n'
        f'<button class="theme-toggle" aria-label="Toggle theme">\n'
        f'{sun_icon}{moon_icon}{auto_icon}\n'
        f'</button>\n'
        f'{search_trigger_html}'
        f'</div>\n'
        f'</header>'
    )


def _generate_post_read_indicator_script(last_updated):
    """Generate a small inline script for post read-tracking via localStorage.

    Shows an "Updated" badge if the post was modified since the reader's
    last visit, and displays a "Last updated" line.  On page load, records
    the current timestamp so future visits know this version was seen.

    Args:
        last_updated: ISO date or datetime string for the post's last
            modification (e.g. "2026-07-05" or "2026-07-05T14:30:00Z").
            Empty string if unknown.
    """
    if not last_updated:
        return ""

    # Escape for safe embedding in a JS string literal
    escaped = _escape_html(last_updated)

    return (
        f'<div class="post-meta" id="post-read-indicator">'
        f'<span class="post-last-updated">Last updated: {escaped}</span>'
        f'</div>\n'
        f'<script>\n'
        f'(function(){{\n'
        f'  var slug=location.pathname.split("/").filter(Boolean).pop()||"";\n'
        f'  var key="post-read-"+slug;\n'
        f'  var updated=new Date("{escaped}").getTime();\n'
        f'  if(updated){{var lastRead=parseInt(localStorage.getItem(key)||"0",10);\n'
        f'    if(updated>lastRead){{\n'
        f'      var badge=document.createElement("span");\n'
        f'      badge.className="post-updated-badge";\n'
        f'      badge.textContent="Updated";\n'
        f'      var el=document.getElementById("post-read-indicator");\n'
        f'      if(el)el.prepend(badge);\n'
        f'    }}\n'
        f'  }}\n'
        f'  localStorage.setItem(key,Date.now().toString());\n'
        f'}})();\n'
        f'</script>'
    )


#: The facets the corpus carries, in the order they are emitted.  Every one
#: is a Pagefind filter, so every one is selectable in the search UI; ``tags``
#: is last because it is the only multi-valued key.
PAGEFIND_FACET_KEYS = (
    "version", "locale", "group", "type", "target", "project", "tags",
)


def pagefind_head_tags(asset_prefix):
    """Return the <head> tags that load the Pagefind UI bundle.

    The bundle is what the indexer itself wrote into ``pagefind/`` at the
    output root, never a CDN copy: a built site answers its own searches
    with no network at all.

    Args:
        asset_prefix: The hop from this page back to the output root, as
            :func:`selfdoc_core.address.page_address` computed it.
    """
    return (
        f'<link href="{asset_prefix}pagefind/pagefind-ui.css" rel="stylesheet">\n'
        f'<script src="{asset_prefix}pagefind/pagefind-ui.js"></script>\n'
    )


def pagefind_facets_html(*, version="", locale="", group="", page_type="",
                         target="", project="", tags=None):
    """Return the hidden facet elements Pagefind reads its filters from.

    Pagefind takes one ``data-pagefind-filter`` per element, so each facet
    value is its own empty element.  That is also the shape multi-valued
    ``tags`` needs, and it means no value is ever escaped into a
    comma-separated list where a comma inside a tag or a nav group name
    would split it in two.

    Empty values are omitted: an empty filter value is a filter group the
    UI offers and nothing matches.

    The elements must sit inside the ``data-pagefind-body`` region, which
    is the ``<article>`` -- a filter outside the indexed body is not read.
    """
    values = {
        "version": version,
        "locale": locale,
        "group": group,
        "type": page_type,
        "target": target,
        "project": project,
    }
    parts = []
    for key in PAGEFIND_FACET_KEYS:
        if key == "tags":
            continue
        value = values[key]
        if value:
            parts.append(
                f'<span class="pagefind-facet" '
                f'data-pagefind-filter="{key}:{_escape_html(str(value))}"></span>'
            )
    for tag in tags or []:
        if tag:
            parts.append(
                f'<span class="pagefind-facet" '
                f'data-pagefind-filter="tags:{_escape_html(str(tag))}"></span>'
            )
    return "".join(parts)


def pagefind_meta_html(*, project="", page_type="", date=""):
    """Return the hidden elements carrying Pagefind result metadata.

    Metadata is what a result *shows*, as opposed to what it filters by.
    One element per key for the same reason the facets get one each: an
    element carries a single ``data-pagefind-meta`` attribute, and the
    comma-separated form would split a value that contains a comma.
    """
    pairs = (("project", project), ("type", page_type), ("date", date))
    return "".join(
        f'<span class="pagefind-facet" '
        f'data-pagefind-meta="{key}:{_escape_html(str(value))}"></span>'
        for key, value in pairs if value
    )


def pagefind_init_script(asset_prefix):
    """Return inline script that initializes Pagefind UI and wires Cmd+K.

    ``bundlePath`` is passed explicitly from the page's own hop back to the
    output root rather than left to the UI's guess, so the dialog finds the
    index under any mount point.
    """
    bundle_path = f"{asset_prefix}pagefind/"
    return (
        '<script>\n'
        'document.addEventListener("DOMContentLoaded", function() {\n'
        '  new PagefindUI({ element: "#pagefind-container", showSubResults: true, '
        f'showImages: false, bundlePath: "{bundle_path}" }});\n'
        '  var dialog = document.getElementById("search-dialog");\n'
        '  document.addEventListener("keydown", function(e) {\n'
        '    if ((e.metaKey || e.ctrlKey) && e.key === "k") {\n'
        '      e.preventDefault();\n'
        '      if (dialog.open) { dialog.close(); } else {\n'
        '        dialog.showModal();\n'
        '        var input = dialog.querySelector(".pagefind-ui__search-input");\n'
        '        if (input) input.focus();\n'
        '      }\n'
        '    }\n'
        '    if (e.key === "Escape" && dialog.open) { dialog.close(); }\n'
        '  });\n'
        '  var closeBtn = dialog.querySelector(".search-close");\n'
        '  if (closeBtn) closeBtn.addEventListener("click", function() { dialog.close(); });\n'
        '  dialog.addEventListener("click", function(e) {\n'
        '    if (e.target === dialog) dialog.close();\n'
        '  });\n'
        '});\n'
        '</script>'
    )


def pagefind_dialog_html():
    """Build the search dialog the Pagefind UI mounts into.

    The dialog itself is chrome: the input, the results list and the filter
    controls are all rendered by the Pagefind UI inside
    ``#pagefind-container``.
    """
    return (
        '<dialog class="search-dialog" id="search-dialog" aria-label="Search documentation">\n'
        '<div class="search-inner">\n'
        '<div class="search-header">\n'
        '<span class="search-header-title">Search</span>\n'
        '<button class="search-close" aria-label="Close search" type="button">X</button>\n'
        '</div>\n'
        '<div id="pagefind-container"></div>\n'
        '</div>\n'
        '</dialog>'
    )


def _build_page_meta(body_html, nav_html, title, prefix, repo, source_path,
                     branch, breadcrumbs, prev_page, next_page, page_nav,
                     page_progress, page_number, total_pages, feedback,
                     toc_html, summary, date_modified, feed_url, page_path,
                     site_terms, has_custom_css_href, version, project_name,
                     description, has_hero, custom_css_href, theme_meta,
                     asset_prefix="", unversioned_prefix=None,
                     mount_locale="", mount_project="", mount_version="",
                     available_versions=None, available_locales=None,
                     current_version="", current_locale="",
                     is_latest=True, page_type=None):
    """Compute all page metadata variables needed by the template.

    Returns a dict with: body_html (possibly modified by cross-page terms),
    version_badge, custom_css_tag, feed_tag, description_tag, breadcrumbs_html,
    edit_link_html, content_date_html, page_nav_html, feedback_html,
    date_display_html, footer_html, toc_aside, mobile_toc_html, summary_html,
    topbar_page_title_html, font_tags, auto_h1_html, search_trigger_html,
    meta_description, feed_footer_html.
    """
    if unversioned_prefix is None:
        unversioned_prefix = prefix

    # Cross-page term linking: wrap first occurrence of terms defined on
    # other pages in <a class="term-link"> before template wrapping.
    if site_terms and page_path:
        body_html = _apply_cross_page_terms(
            body_html, site_terms, page_path, prefix,
        )

    version_badge = (
        f'<span class="version-badge">v{_escape_html(version)}</span>'
        if version else ""
    )
    custom_css_tag = (
        f'\n<link rel="stylesheet" href="{custom_css_href}">'
        if has_custom_css_href else ""
    )
    # Atom feed link tag
    feed_tag = ""
    if feed_url:
        feed_tag = (
            f'\n<link rel="alternate" type="application/atom+xml" '
            f'title="{_escape_html(project_name)} Feed" href="{feed_url}">'
        )
    # Meta description tag (Feature 34)
    # Fall back to the auto-extracted first sentence when frontmatter
    # description is absent (a complete unit), matching og:description.
    meta_description = description or first_sentence(
        _extract_first_paragraph(body_html)
    )
    description_tag = ""
    if meta_description:
        description_tag = (
            f'\n<meta name="description" content="{_escape_html(meta_description)}">'
        )

    # Breadcrumbs (Feature 9)
    breadcrumbs_html = breadcrumbs if breadcrumbs else ""

    # Edit link (Feature 14)
    edit_link_html = ""
    edit_url = ""
    if repo and source_path:
        repo_url = repo.rstrip("/")
        edit_url = f"{repo_url}/edit/{branch}/{source_path}"
        edit_link_html = (
            f'<a class="edit-link" href="{edit_url}" target="_blank" rel="noopener">'
            f'Edit this page on GitHub</a>'
        )

    # Top edit link: right-aligned near breadcrumbs
    top_edit_link_html = ""
    if edit_url:
        top_edit_link_html = (
            f'<a class="edit-link edit-link-top" href="{edit_url}" target="_blank" rel="noopener">Edit</a>'
        )

    # Format date_modified for content header display (e.g. "Updated May 1, 2026")
    content_date_html = ""
    if date_modified:
        try:
            dt = datetime.strptime(date_modified, "%Y-%m-%d")
            formatted_date = dt.strftime("%B %-d, %Y")
        except (ValueError, TypeError):
            formatted_date = date_modified
        content_date_html = (
            f'<span class="content-date">Updated '
            f'<time datetime="{_escape_html(date_modified)}">'
            f'{_escape_html(formatted_date)}</time></span>'
        )

    # Content header: wraps breadcrumbs, top edit link, and date
    header_right_parts = []
    if content_date_html:
        header_right_parts.append(content_date_html)
    if top_edit_link_html:
        header_right_parts.append(top_edit_link_html)
    header_right_html = "\n".join(header_right_parts)

    if breadcrumbs_html and header_right_html:
        breadcrumbs_html = (
            f'<div class="content-header">\n'
            f'{breadcrumbs_html}\n'
            f'{header_right_html}\n'
            f'</div>'
        )
    elif header_right_html:
        breadcrumbs_html = (
            f'<div class="content-header">\n'
            f'{header_right_html}\n'
            f'</div>'
        )

    # Prev/next page navigation (Feature 8)
    page_nav_html = ""
    if page_nav and (prev_page or next_page):
        prev_link = ""
        next_link = ""
        if prev_page:
            # A neighbour marked unversioned lives at the version-free
            # mount, one level up from this page's own.
            prev_hop = (
                unversioned_prefix if prev_page.get("unversioned") else prefix
            )
            prev_href = prev_hop + _html_path_to_url(prev_page["path"])
            prev_label = _escape_html(prev_page["label"])
            prev_link = (
                f'<a class="page-nav-prev" href="{prev_href}">'
                f'<span class="page-nav-label">Previous</span>'
                f'&larr; {prev_label}</a>'
            )
        # Page progress indicator (e.g. "Page 2 of 5")
        progress_html = ""
        if (page_progress and page_number is not None
                and total_pages is not None and total_pages > 1):
            progress_html = (
                f'<span class="page-progress">'
                f'Page {page_number} of {total_pages}</span>'
            )
        if next_page:
            next_hop = (
                unversioned_prefix if next_page.get("unversioned") else prefix
            )
            next_href = next_hop + _html_path_to_url(next_page["path"])
            next_label = _escape_html(next_page["label"])
            next_link = (
                f'<a class="page-nav-next" href="{next_href}">'
                f'<span class="page-nav-label">Next</span>'
                f'{next_label} &rarr;</a>'
            )
        page_nav_html = (
            f'<nav class="page-nav">{prev_link}{progress_html}{next_link}</nav>'
        )

    # Feedback widget (Feature 30): only rendered when feedback config is set
    feedback_html = ""
    if feedback is not None:
        data_attrs = ""
        if feedback.get("webhook"):
            data_attrs += f' data-webhook="{_escape_html(feedback["webhook"])}"'
        if feedback.get("ga"):
            data_attrs += f' data-ga="{_escape_html(feedback["ga"])}"'
        feedback_html = (
            f'<div class="feedback"{data_attrs}>'
            '<span>Was this page helpful?</span>'
            '<button class="feedback-yes" aria-label="Yes">Yes</button>'
            '<button class="feedback-no" aria-label="No">No</button>'
            '</div>'
        )

    # Format date_modified for display (e.g. "May 1, 2026")
    date_display_html = ""
    if date_modified:
        try:
            dt = datetime.strptime(date_modified, "%Y-%m-%d")
            formatted_date = dt.strftime("%B %-d, %Y")
        except (ValueError, TypeError):
            formatted_date = date_modified
        date_display_html = (
            f'<time datetime="{_escape_html(date_modified)}">'
            f'{_escape_html(formatted_date)}</time>'
        )

    # Page footer (Feature 18): combines edit link, feedback, and prev/next nav
    footer_html = _render_page_footer(
        edit_link_html, date_display_html, feedback_html, page_nav_html,
    )

    # TOC aside (Feature 2) -- desktop only
    toc_aside = ""
    if toc_html:
        toc_aside = f'<aside class="toc">{toc_html}</aside>'

    # Mobile TOC disclosure (Feature 26) -- shown only on mobile via CSS
    mobile_toc_html = ""
    if toc_html:
        mobile_toc_html = (
            f'<details class="mobile-toc">'
            f'<summary>On this page</summary>'
            f'{toc_html}'
            f'</details>'
        )

    # Page summary block from frontmatter description (Phase 2.6)
    summary_html = ""
    if summary:
        summary_html = (
            f'<div class="page-summary">\n'
            f'  <p>{_escape_html(summary)}</p>\n'
            f'</div>'
        )

    # Page title in topbar for non-index pages (Issue 51)
    topbar_page_title_html = ""
    if page_path and page_path != "index.html":
        topbar_page_title_html = (
            f'<span class="topbar-sep">/</span>'
            f'<span class="topbar-page-title">{_escape_html(title)}</span>'
        )

    # Build font loading tags from theme metadata (or omit when no fonts_url)
    font_tags = ""
    if theme_meta and theme_meta.get("fonts_url"):
        fonts_url = theme_meta["fonts_url"]
        preconnect_lines = ""
        for pc_url in theme_meta.get("fonts_preconnect") or []:
            # The first preconnect is same-origin; subsequent ones get crossorigin
            if pc_url == (theme_meta.get("fonts_preconnect") or [None])[0]:
                preconnect_lines += (
                    f'<link rel="preconnect" href="{pc_url}">\n'
                )
            else:
                preconnect_lines += (
                    f'<link rel="preconnect" href="{pc_url}" crossorigin>\n'
                )
        font_tags = (
            f'{preconnect_lines}'
            f'<link rel="preload" href="{fonts_url}" as="style">\n'
            f'<link rel="stylesheet" href="{fonts_url}" media="print"'
            f" onload=\"this.media='all'\">"
            f'<noscript><link rel="stylesheet" href="{fonts_url}"></noscript>\n'
        )

    # Phase 3: auto-generate H1 from the page title. When the hero section
    # is present, it already provides the H1 so we suppress the auto H1.
    auto_h1_html = ""
    if not has_hero:
        # One implementation assigns every anchor on the page, the page
        # title's included -- see page_title_anchor.
        h1_slug = page_title_anchor(title)
        h1_readable = _escape_html(title)
        h1_anchor = (
            f'<a class="heading-link" href="#{h1_slug}"'
            f' aria-label="Link to section: {h1_readable}">#</a>'
        )
        auto_h1_html = (
            f'<h1 id="{h1_slug}">{h1_anchor}{_escape_html(title)}</h1>'
        )

    # Feed link in site footer (Feature 9.5)
    feed_footer_html = ""
    if feed_url:
        feed_footer_html = (
            '\n<p><a class="feed-link" href="' + _escape_html(feed_url) + '">'
            '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">'
            '<circle cx="6.18" cy="17.82" r="2.18"/>'
            '<path d="M4 4.44v2.83c7.03 0 12.73 5.7 12.73 12.73h2.83c0-8.59-6.97-15.56-15.56-15.56z'
            'm0 5.66v2.83c3.9 0 7.07 3.17 7.07 7.07h2.83c0-5.47-4.43-9.9-9.9-9.9z"/>'
            '</svg>'
            'Subscribe via RSS</a></p>'
        )

    # Search trigger HTML (configurable: "icon", "bar", or "hidden")
    # Note: search parameter is passed via the caller; we use has_custom_css_href
    # as a proxy -- but actually search is not in this function's params.
    # The search_trigger_html is computed by the caller and passed to _render_topbar.

    return {
        "body_html": body_html,
        "version_badge": version_badge,
        "custom_css_tag": custom_css_tag,
        "feed_tag": feed_tag,
        "description_tag": description_tag,
        "breadcrumbs_html": breadcrumbs_html,
        "footer_html": footer_html,
        "toc_aside": toc_aside,
        "mobile_toc_html": mobile_toc_html,
        "summary_html": summary_html,
        "topbar_page_title_html": topbar_page_title_html,
        "font_tags": font_tags,
        "auto_h1_html": auto_h1_html,
        "feed_footer_html": feed_footer_html,
    }


def _wrap_page(body_html, nav_html, title, project_name, version,
               css_href="style.css", custom_css_href=None,
               toc_html="", breadcrumbs=None, prev_page=None,
               next_page=None, prefix="", asset_prefix="",
               unversioned_prefix=None, home_href=None,
               repo=None, source_path=None,
               base_url=None, url_builder=None, page_path=None, description="",
               lang="en", date_published=None, date_modified=None, author=None,
               feed_url=None, summary=None, critical_css=None,
               schema=None, page_type=None, schema_types=None,
               page_tags=None, twitter_site=None, search=None,
               feedback=None, branch="main", nav_group="",
               site_terms=None, page_number=None, total_pages=None,
               theme_meta=None, has_hero=False, deploy_target=None,
               page_nav=True, page_progress=True,
               mount_locale="", mount_project="", mount_version="",
               mount_archived=False,
               available_versions=None, available_locales=None,
               version_pages=None,
               current_version="", current_locale="",
               is_latest=True):
    """Wrap converted HTML body in the full page template.

    ``prefix`` reaches this page's own mount root (sibling pages);
    ``asset_prefix`` reaches the output root (shared assets);
    ``unversioned_prefix`` reaches the version-free mount (pages marked
    ``versioned: false``).  All three come from
    :func:`selfdoc_core.address.page_address`.  ``home_href`` addresses
    the page the site calls home, which is not always this mount's
    index -- see :func:`_home_href`.

    ``unversioned_prefix`` and ``home_href`` default to the mount hop:
    on a page whose sidebar holds no unversioned item, the two hops are
    the same answer.
    """
    # Use default theme metadata when none provided (backward compatible)
    if theme_meta is None:
        theme_meta = get_theme_meta("minimal")
    if unversioned_prefix is None:
        unversioned_prefix = prefix
    if home_href is None:
        home_href = prefix + "index.html"

    # The page's own address decides every control that names another
    # address: the two pickers, the superseded-version notice, and the
    # share control.  Pages with no path of their own (404.html) have no
    # address and get none of them.
    if page_path:
        addr = page_address(
            page_path,
            locale=mount_locale,
            project=mount_project,
            version=mount_version,
            archived=mount_archived,
        )
        version_picker_html = _render_version_picker(
            addr, available_versions, version_pages,
        )
        locale_picker_html = _render_locale_picker(
            addr, available_locales, current_locale,
        )
        version_notice_html = _render_version_notice(addr)
        share_html = _render_share_control(addr, url_builder, base_url)
    else:
        version_picker_html = ""
        locale_picker_html = ""
        version_notice_html = ""
        share_html = ""

    # Compute all page metadata variables
    meta = _build_page_meta(
        body_html=body_html, nav_html=nav_html, title=title, prefix=prefix,
        repo=repo, source_path=source_path, branch=branch,
        breadcrumbs=breadcrumbs, prev_page=prev_page, next_page=next_page,
        page_nav=page_nav, page_progress=page_progress,
        page_number=page_number, total_pages=total_pages, feedback=feedback,
        toc_html=toc_html, summary=summary, date_modified=date_modified,
        feed_url=feed_url, page_path=page_path, site_terms=site_terms,
        has_custom_css_href=custom_css_href, version=version,
        project_name=project_name, description=description,
        has_hero=has_hero, custom_css_href=custom_css_href,
        theme_meta=theme_meta,
        asset_prefix=asset_prefix,
        unversioned_prefix=unversioned_prefix,
        mount_locale=mount_locale,
        mount_project=mount_project,
        mount_version=mount_version,
        available_versions=available_versions,
        available_locales=available_locales,
        current_version=current_version,
        current_locale=current_locale,
        is_latest=is_latest,
        page_type=page_type,
    )
    body_html = meta["body_html"]

    # Build SEO tags and security meta
    seo_tags, security_meta = _render_seo_tags(
        title=title, base_url=base_url, url_builder=url_builder,
        page_path=page_path,
        description=description, body_html=body_html, author=author,
        project_name=project_name, repo=repo, date_published=date_published,
        date_modified=date_modified, lang=lang, breadcrumbs=breadcrumbs,
        schema=schema, page_type=page_type, schema_types=schema_types,
        page_tags=page_tags,
        twitter_site=twitter_site,
        deploy_target=deploy_target,
        available_locales=available_locales,
        current_locale=current_locale,
        mount_locale=mount_locale,
        mount_project=mount_project,
        mount_version=mount_version,
    )

    # Search trigger HTML (configurable: "icon", "bar", or "hidden")
    effective_search = search if search else "icon"
    if effective_search == "icon":
        search_trigger_html = (
            '<button class="search-trigger" aria-label="Search documentation" title="Search (Cmd+K)">\n'
            '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>\n'
            '</button>\n'
        )
    elif effective_search == "bar":
        search_trigger_html = (
            '<button class="search-bar-trigger" aria-label="Search documentation">\n'
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>\n'
            '<span class="search-bar-text">Search...</span>\n'
            '<kbd class="search-bar-kbd">Cmd+K</kbd>\n'
            '</button>\n'
        )
    else:
        # "hidden" -- no trigger in topbar
        search_trigger_html = ""

    # Build topbar
    topbar_html = _render_topbar(
        project_name=project_name,
        version_badge=meta["version_badge"],
        topbar_page_title_html=meta["topbar_page_title_html"],
        search_trigger_html=search_trigger_html,
        home_href=home_href,
        version_picker_html=version_picker_html,
        locale_picker_html=locale_picker_html,
    )

    # Build search dialog
    search_dialog_html = pagefind_dialog_html()

    # Load JS from external files via the loader module
    from selfdoc_core.js.loader import load_js, assemble_body_js

    head_js = load_js("head")

    # Assemble body JS from external files via the loader
    body_js = _minify_js(assemble_body_js(
        body_html, toc_html, meta["footer_html"],
        extras_html=version_notice_html + share_html,
    ))

    # Google Analytics script (injected when feedback.ga is configured)
    ga_head_script = ""
    if feedback and feedback.get("ga"):
        ga_id = _escape_html(feedback["ga"])
        ga_js = load_js("ga")
        ga_head_script = (
            f'<script async src="https://www.googletagmanager.com/gtag/js?id={ga_id}"></script>\n'
            f'<script data-ga-id="{ga_id}">{ga_js}</script>\n'
        )

    # The article is the indexed region; the facet and meta values sit
    # inside it as their own elements, because one element carries one
    # data-pagefind-filter and one data-pagefind-meta attribute.
    pagefind_block = (
        pagefind_facets_html(
            version=version,
            locale=current_locale or mount_locale,
            group=nav_group or "",
            page_type=page_type or "",
            target=deploy_target or "",
            project=project_name,
            tags=page_tags,
        )
        + pagefind_meta_html(
            project=project_name,
            page_type=page_type or "",
            date=date_published or "",
        )
    )

    # Post read-indicator script: localStorage-based "Updated" badge
    # and "Last updated" display for post pages.
    post_read_script = ""
    if page_type == "post":
        post_read_script = _generate_post_read_indicator_script(
            date_modified or date_published or "",
        )

    return (
        f'<!DOCTYPE html>\n'
        f'<html lang="{lang}">\n'
        f'<head>\n'
        f'<meta charset="UTF-8">\n'
        f'<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f'<title>{_escape_html(title)} - {_escape_html(project_name)}</title>{meta["description_tag"]}\n'
        f'<link rel="icon" type="image/svg+xml" href="{asset_prefix}favicon.svg">\n'
        f'{meta["font_tags"]}'
        f'{"<style>" + critical_css + "</style>" + chr(10) if critical_css else ""}'
        f'<link rel="preload" href="{css_href}" as="style">\n'
        f'<link rel="stylesheet" href="{css_href}" media="print"'
        f" onload=\"this.media='all'\">"
        f'<noscript><link rel="stylesheet" href="{css_href}"></noscript>'
        f'{meta["custom_css_tag"]}{meta["feed_tag"]}{seo_tags}{security_meta}\n'
        f'<script>{head_js}</script>\n'
        f'{ga_head_script}'
        f'{pagefind_head_tags(asset_prefix)}'
        f'</head>\n'
        f'<body>\n'
        f'<a class="skip-link" href="#main-content">Skip to content</a>\n'
        f'{topbar_html}\n'
        f'<div class="reading-progress" id="reading-progress"></div>\n'
        f'<div class="layout{" layout--narrow" if page_type == "post" else ""}">\n'
        f'<nav class="sidebar" id="sidebar" aria-label="Site navigation">\n'
        f'<ul class="nav-list">\n'
        f'{nav_html}\n'
        f'</ul>\n'
        f'</nav>\n'
        f'<main class="content" id="main-content">\n'
        f'{version_notice_html}\n'
        f'<article data-pagefind-body>\n'
        f'{pagefind_block}\n'
        f'{meta["breadcrumbs_html"]}\n'
        f'{meta["mobile_toc_html"]}\n'
        f'{meta["summary_html"]}\n'
        f'{meta["auto_h1_html"]}\n'
        f'{body_html}\n'
        f'{share_html}\n'
        f'{meta["footer_html"]}\n'
        f'</article>\n'
        f'{post_read_script}\n'
        f'</main>\n'
        f'{meta["toc_aside"] if page_type != "post" else ""}\n'
        f'</div>\n'
        f'<footer class="site-footer">\n'
        f'<p>Built with <a href="https://github.com/smm-h/selfdoc">selfdoc</a></p>\n'
        f'{meta["feed_footer_html"]}\n'
        f'</footer>\n'
        f'<script>{body_js}</script>\n'
        f'{search_dialog_html}\n'
        f'{pagefind_init_script(asset_prefix)}\n'
        f'</body>\n'
        f'</html>\n'
    )

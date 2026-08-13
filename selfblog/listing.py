"""The home project's curated project listing: one declared source, two renderings.

The assembled site shows the projects it serves in two places -- the front
page's cards and the generated ``/projects/`` page -- and both read this one
document, ``docs/projects.toml`` in the home project.  The listing is content,
and content is the home project's territory, so it is authored there rather
than in the assembly repository.

Curation means selection: a roster project the listing leaves out simply does
not appear, which is legal and deliberate.  The reverse is not: a listed slug
with no manifest at assembly time is a hard error naming it, because the
listing would otherwise print a card for a project the site cannot serve.
"""

from __future__ import annotations

import dataclasses
import html
import json

#: The file, relative to the home project's root, that declares the listing.
LISTING_SOURCE = "docs/projects.toml"

#: Where the assembly keeps the copy the deploy grafted, as a manifest
#: sidecar belonging to the home slug.
LISTING_SIDECAR_SUFFIX = "-listing.json"

LISTING_FORMAT_VERSION = 1

#: Every key a ``[[category]]`` block may carry.
CATEGORY_KEYS = ("name", "project")

#: Every key a ``[[category.project]]`` block may carry.  ``slug`` and
#: ``blurb`` are required; ``url`` marks an entry the assembly does not serve
#: (a project with no docs section), and ``name`` is required for exactly
#: those -- an entry the assembly does serve takes its name from its manifest,
#: so declaring one here would be a second source for the same fact.
#: ``repo`` is the project's repository, rendered as a second link on the
#: card beside the one the title carries.
PROJECT_KEYS = ("slug", "blurb", "url", "name", "repo")


@dataclasses.dataclass(frozen=True)
class ListingProject:
    """One curated entry.

    ``url`` empty means the entry names a project the assembly serves: its
    display name and version come from its manifest and its address is its
    section on this site.  ``url`` set means an external project with no docs
    section here, which therefore carries its own ``name``.  ``repo`` is the
    project's repository, which a card links to beside its documentation.
    """

    slug: str
    blurb: str
    url: str = ""
    name: str = ""
    repo: str = ""

    @property
    def external(self) -> bool:
        return bool(self.url)


@dataclasses.dataclass(frozen=True)
class ListingCategory:
    """One named group of curated entries, in declared order."""

    name: str
    projects: tuple[ListingProject, ...]


@dataclasses.dataclass(frozen=True)
class Listing:
    """The whole curated listing, in declared order."""

    categories: tuple[ListingCategory, ...]

    @property
    def slugs(self) -> list[str]:
        return [p.slug for c in self.categories for p in c.projects]

    def entries(self):
        for category in self.categories:
            for project in category.projects:
                yield category, project


def parse_listing(text: str, *, source: str = LISTING_SOURCE) -> Listing:
    """Return the :class:`Listing` the document *text* declares.

    Validation is strict in every direction: an unknown top-level key, an
    unknown key on any block, a missing or empty required key, a category
    with no entries, a duplicate category name and a duplicate slug are each
    a hard error naming the offending declaration.
    """
    import tomllib

    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"{source} is not valid TOML: {exc}") from exc

    unknown = sorted(set(data) - {"category"})
    if unknown:
        raise RuntimeError(
            f"{source} declares unknown top-level key(s) "
            f"{', '.join(repr(k) for k in unknown)}. The listing holds "
            f"nothing but [[category]] blocks."
        )

    raw_categories = data.get("category")
    if not isinstance(raw_categories, list) or not raw_categories:
        raise RuntimeError(
            f"{source} declares no [[category]] block. The listing is the "
            f"site's curated project index and there is no empty default."
        )

    categories: list[ListingCategory] = []
    seen_categories: set[str] = set()
    seen_slugs: dict[str, str] = {}

    for index, raw in enumerate(raw_categories, start=1):
        where = f"{source}: [[category]] #{index}"
        if not isinstance(raw, dict):
            raise RuntimeError(f"{where} is not a table.")
        unknown_keys = sorted(set(raw) - set(CATEGORY_KEYS))
        if unknown_keys:
            raise RuntimeError(
                f"{where} declares unknown key(s) "
                f"{', '.join(repr(k) for k in unknown_keys)}. A [[category]] "
                f"block carries {', '.join(CATEGORY_KEYS)}."
            )
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise RuntimeError(f"{where} is missing a non-empty 'name'.")
        name = name.strip()
        if name in seen_categories:
            raise RuntimeError(
                f"{where} repeats the category name {name!r}, which an "
                f"earlier block already declares."
            )
        seen_categories.add(name)

        raw_projects = raw.get("project")
        if not isinstance(raw_projects, list) or not raw_projects:
            raise RuntimeError(
                f"{where} ({name!r}) declares no [[category.project]] block. "
                f"An empty category would render as a heading over nothing."
            )

        projects: list[ListingProject] = []
        for position, item in enumerate(raw_projects, start=1):
            spot = f"{where} ({name!r}): [[category.project]] #{position}"
            if not isinstance(item, dict):
                raise RuntimeError(f"{spot} is not a table.")
            unknown_keys = sorted(set(item) - set(PROJECT_KEYS))
            if unknown_keys:
                raise RuntimeError(
                    f"{spot} declares unknown key(s) "
                    f"{', '.join(repr(k) for k in unknown_keys)}. A listed "
                    f"project carries {', '.join(PROJECT_KEYS)}."
                )
            slug = item.get("slug")
            if not isinstance(slug, str) or not slug.strip():
                raise RuntimeError(f"{spot} is missing a non-empty 'slug'.")
            slug = slug.strip()
            blurb = item.get("blurb")
            if not isinstance(blurb, str) or not blurb.strip():
                raise RuntimeError(
                    f"{spot} ({slug}) is missing a non-empty 'blurb'. The "
                    f"listing is curated prose, not a directory dump."
                )
            url = str(item.get("url") or "").strip()
            entry_name = str(item.get("name") or "").strip()
            if url and not entry_name:
                raise RuntimeError(
                    f"{spot} ({slug}) declares a url, so it is a project this "
                    f"site does not serve and has no manifest to take a "
                    f"display name from. Declare 'name'."
                )
            if entry_name and not url:
                raise RuntimeError(
                    f"{spot} ({slug}) declares a name but no url. A project "
                    f"this site serves takes its name from its manifest, so "
                    f"declaring one here would be a second source for it."
                )
            repo = str(item.get("repo") or "").strip()
            if repo and repo == url:
                raise RuntimeError(
                    f"{spot} ({slug}) declares the same address as 'url' and "
                    f"'repo', so the card would print two links to one place. "
                    f"An entry whose only address is its repository needs "
                    f"'url' alone."
                )
            if slug in seen_slugs:
                raise RuntimeError(
                    f"{spot} repeats the slug {slug!r}, already listed under "
                    f"{seen_slugs[slug]!r}. One project, one card."
                )
            seen_slugs[slug] = name
            projects.append(ListingProject(
                slug=slug, blurb=blurb.strip(), url=url, name=entry_name,
                repo=repo,
            ))

        categories.append(ListingCategory(name=name, projects=tuple(projects)))

    return Listing(categories=tuple(categories))


def load_listing_source(path: str) -> Listing:
    """Return the listing declared in the TOML document at *path*."""
    with open(path, "r", encoding="utf-8") as f:
        return parse_listing(f.read(), source=path)


def render_listing_sidecar(listing: Listing, slug: str) -> str:
    """Return the JSON the assembly keeps beside the manifests."""
    return json.dumps(
        {
            "format_version": LISTING_FORMAT_VERSION,
            "slug": slug,
            "categories": [
                {
                    "name": category.name,
                    "projects": [
                        dataclasses.asdict(project)
                        for project in category.projects
                    ],
                }
                for category in listing.categories
            ],
        },
        indent=2,
    ) + "\n"


def parse_listing_sidecar(text: str, *, source: str) -> Listing:
    """Return the listing a sidecar document holds.

    The sidecar is written by the deploy, never by hand, so the only thing
    checked here is that it is the format this selfblog understands -- a
    wrong or absent ``format_version`` is a hard error, never a guess.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{source} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{source} must contain a JSON object.")
    version = data.get("format_version")
    if version != LISTING_FORMAT_VERSION:
        raise RuntimeError(
            f"{source} declares format_version {version!r}; this selfblog "
            f"reads {LISTING_FORMAT_VERSION}. Re-deploy the home project to "
            f"rewrite the sidecar."
        )
    categories = []
    for category in data.get("categories") or []:
        categories.append(ListingCategory(
            name=str(category.get("name") or ""),
            projects=tuple(
                ListingProject(
                    slug=str(p.get("slug") or ""),
                    blurb=str(p.get("blurb") or ""),
                    url=str(p.get("url") or ""),
                    name=str(p.get("name") or ""),
                    repo=str(p.get("repo") or ""),
                )
                for p in category.get("projects") or []
            ),
        ))
    return Listing(categories=tuple(categories))


def load_listing_sidecar(path: str) -> Listing:
    with open(path, "r", encoding="utf-8") as f:
        return parse_listing_sidecar(f.read(), source=path)


def check_listing_against(listing: Listing, manifests, *, home_slug: str,
                          source: str = LISTING_SOURCE) -> None:
    """Raise unless every listed slug can actually be rendered.

    Two failures, both naming the slug: an entry the assembly is supposed to
    serve but has no manifest for, and the home project listing itself --
    the front page is not one of the projects the front page lists.
    """
    known = {str(m.get("slug") or "") for m in manifests}
    missing = [
        p.slug for _c, p in listing.entries()
        if not p.external and p.slug not in known
    ]
    if missing:
        served = ", ".join(sorted(known)) or "(none)"
        raise RuntimeError(
            f"{source} lists {', '.join(sorted(missing))}, which the assembly "
            f"has no manifest for, so the listing would print a card for a "
            f"project this site does not serve. Either the project has never "
            f"deployed, or the entry names an external project and is missing "
            f"its 'url' and 'name'. Served projects: {served}."
        )
    if home_slug and home_slug in listing.slugs:
        raise RuntimeError(
            f"{source} lists {home_slug!r}, which is the home project -- the "
            f"page the listing appears on. The home project is left out of "
            f"the listing it renders."
        )


def render_listing_html(listing: Listing, manifests, site_hop: str, *,
                        home_slug: str = "", heading: str = "") -> str:
    """Return the curated listing as one HTML fragment.

    This is the single renderer behind both surfaces: the generated
    ``/projects/`` page passes a heading, the front page's cards directive
    does not.  Version badges come from the manifests, so a card is as
    current as the last deploy of the project it names.

    *site_hop* is the hop from the page holding the fragment back to the
    site root, and every card for a project the site serves is addressed
    through it.  A card for an *external* project keeps the absolute URL
    the listing declares: that one really does name somebody else's
    server.

    The cards are stated in the framework's own card vocabulary --
    ``.card-grid`` for the responsive grid, ``.card`` for the box,
    ``.card-title-row``/``.card-title`` for the head, ``.card-badges`` and
    ``.badge`` for the version chip -- with ``.project-*`` hooks riding
    alongside for the rules only a project card needs.  A private class
    surface no theme knew about is what made these render as full-width
    unstyled boxes.
    """
    check_listing_against(listing, manifests, home_slug=home_slug)
    by_slug = {str(m.get("slug") or ""): m for m in manifests}

    parts = ['<section class="project-list">']
    if heading:
        parts.append(f"  <h1>{html.escape(heading)}</h1>")
    for category in listing.categories:
        parts.append('  <section class="project-category">')
        parts.append(f"    <h2>{html.escape(category.name)}</h2>")
        parts.append('    <div class="card-grid project-grid">')
        for project in category.projects:
            if project.external:
                name = project.name
                href = project.url
                version = ""
            else:
                manifest = by_slug[project.slug]
                name = str(manifest.get("name") or project.slug)
                href = f"{site_hop}{project.slug}/"
                version = str(manifest.get("version") or "")
            parts.append('      <article class="card project-card">')
            parts.append('        <div class="card-title-row">')
            parts.append(
                f'          <h3 class="card-title">'
                f'<a href="{html.escape(href)}">'
                f"{html.escape(name)}</a></h3>"
            )
            parts.append("        </div>")
            badges = []
            if version:
                label = "monorepo" if version == "0.0.0" else f"v{version}"
                badges.append(
                    f'<span class="badge badge-neutral version-badge">'
                    f"{html.escape(label)}</span>"
                )
            if project.external:
                badges.append(
                    '<span class="badge badge-neutral external-badge">'
                    "external</span>"
                )
            if badges:
                parts.append(
                    '        <div class="card-badges">'
                    + "".join(badges)
                    + "</div>"
                )
            parts.append(
                f'        <p class="project-blurb">'
                f"{html.escape(project.blurb)}</p>"
            )
            if project.repo:
                # The arrow is what makes the line read as a link rather than
                # as a label; it is decorative, so it is hidden from the
                # accessibility tree and the link's name stays "Repository".
                parts.append(
                    f'        <a class="project-repo" '
                    f'href="{html.escape(project.repo)}">Repository'
                    f'<span aria-hidden="true">&#8599;</span></a>'
                )
            parts.append("      </article>")
        parts.append("    </div>")
        parts.append("  </section>")
    parts.append("</section>")
    return "\n".join(parts)

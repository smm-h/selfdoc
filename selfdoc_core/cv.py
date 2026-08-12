"""The CV as data: one declared document, rendered as a page and as a Person.

A curriculum vitae is a record, not prose that happens to look like one --
every part of it is a field somebody could ask for by name.  It is therefore
declared in a TOML document and rendered from there, so the page a reader
sees and the ``Person`` a crawler reads are two renderings of one source
rather than two texts that have to be kept in agreement by hand.

The document is validated strictly: an unknown key anywhere, a missing
required field, or an empty section is a hard error naming the offending
declaration.  Every section is required and non-empty, for the reason the
curated project listing gives for the same rule -- an absent section would
render as a heading over nothing, and there is no sensible default for a
fact about a person.

Two renderings, both from :class:`CV`:

* :func:`render_cv_markdown` -- the page body, as Markdown, which the build
  converts like any other page content.
* :func:`cv_person_jsonld` -- a ``Person`` carrying what the CV knows on top
  of the site's declared author: the job title, the summary, the languages,
  the schools, and every external profile.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import re

from selfdoc_core.identity import person_entity

#: Where the home project declares its CV, relative to the project root.
CV_SOURCE = "docs/cv.toml"

#: The document format this module reads.  A line carrying anything else is
#: a hard error, never a guess about which shape was meant.
CV_FORMAT_VERSION = 1

#: The page type a CV page declares in its frontmatter, which the schema-type
#: mapping turns into ``ProfilePage``.
CV_PAGE_TYPE = "cv"

TOP_LEVEL_KEYS = (
    "format_version", "identity", "skills", "projects", "interests",
    "education", "experience", "languages", "contact",
)
IDENTITY_KEYS = (
    "name", "headline", "location", "email", "photo", "summary", "updated",
    "profile",
)
PROFILE_KEYS = ("label", "url")
SKILL_KEYS = ("category", "items")
PROJECT_KEYS = ("name", "notes", "technologies")
INTEREST_KEYS = ("title", "body")
EDUCATION_KEYS = (
    "degree", "years", "institute", "institute_url", "location", "focus",
    "thesis", "course_url",
)
EXPERIENCE_KEYS = (
    "role", "period", "company", "company_url", "location", "body",
)
LANGUAGE_KEYS = ("name", "url", "level")
CONTACT_KEYS = ("body",)


@dataclasses.dataclass(frozen=True)
class Profile:
    """One external address the CV's owner is reachable at."""

    label: str
    url: str


@dataclasses.dataclass(frozen=True)
class Identity:
    """Who the CV is about."""

    name: str
    headline: str
    location: str
    email: str
    summary: str
    photo: str = ""
    updated: str = ""
    profiles: tuple[Profile, ...] = ()


@dataclasses.dataclass(frozen=True)
class SkillGroup:
    category: str
    items: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Project:
    name: str
    notes: tuple[str, ...] = ()
    technologies: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class Interest:
    title: str
    body: str


@dataclasses.dataclass(frozen=True)
class Education:
    degree: str
    years: str
    institute: str
    location: str
    institute_url: str = ""
    focus: str = ""
    thesis: str = ""
    course_url: str = ""


@dataclasses.dataclass(frozen=True)
class Experience:
    role: str
    period: str
    company: str
    location: str
    company_url: str = ""
    body: str = ""


@dataclasses.dataclass(frozen=True)
class Language:
    name: str
    level: str
    url: str = ""


@dataclasses.dataclass(frozen=True)
class CV:
    """The whole declared document, in declared order."""

    identity: Identity
    skills: tuple[SkillGroup, ...]
    projects: tuple[Project, ...]
    interests: tuple[Interest, ...]
    education: tuple[Education, ...]
    experience: tuple[Experience, ...]
    languages: tuple[Language, ...]
    contact: str


# -- parsing ------------------------------------------------------------------


def _reject_unknown(where: str, block: dict, known: tuple[str, ...]) -> None:
    unknown = sorted(set(block) - set(known))
    if unknown:
        raise RuntimeError(
            f"{where} declares unknown key(s) "
            f"{', '.join(repr(k) for k in unknown)}. It carries "
            f"{', '.join(known)}."
        )


def _text(where: str, block: dict, key: str, *, required: bool = True) -> str:
    value = block.get(key)
    if value is None:
        if required:
            raise RuntimeError(f"{where} is missing a non-empty {key!r}.")
        return ""
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{where} is missing a non-empty {key!r}.")
    return value.strip()


def _strings(where: str, block: dict, key: str, *,
             required: bool = True) -> tuple[str, ...]:
    value = block.get(key)
    if value is None:
        if required:
            raise RuntimeError(
                f"{where} is missing {key!r}, a non-empty list of strings."
            )
        return ()
    if not isinstance(value, list) or not value:
        raise RuntimeError(
            f"{where}: {key!r} must be a non-empty list of strings."
        )
    out = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise RuntimeError(
                f"{where}: every entry of {key!r} must be a non-empty string."
            )
        out.append(item.strip())
    return tuple(out)


def _reject_repeat(
    where: str,
    seen: set[tuple[str, ...]],
    key: tuple[str, ...],
    label: str,
    kind: str,
) -> None:
    """Refuse a section entry that repeats one already declared.

    A CV lists each thing once: a repeated entry renders twice and states
    the same fact twice, which is a mistake in the document rather than
    something to render faithfully.  *key* is what identifies the entry --
    one field where that is enough, several where it is not -- and *label*
    is how the entry is named back to whoever wrote it.
    """
    if key in seen:
        raise RuntimeError(f"{where} repeats the {kind} {label!r}.")
    seen.add(key)


def _blocks(source: str, data: dict, key: str) -> list[tuple[str, dict]]:
    """Return the ``[[key]]`` blocks, each with the place to name in errors."""
    raw = data.get(key)
    if not isinstance(raw, list) or not raw:
        raise RuntimeError(
            f"{source} declares no [[{key}]] block. Every CV section is "
            f"declared and non-empty; an absent one would render as a "
            f"heading over nothing."
        )
    out = []
    for index, item in enumerate(raw, start=1):
        where = f"{source}: [[{key}]] #{index}"
        if not isinstance(item, dict):
            raise RuntimeError(f"{where} is not a table.")
        out.append((where, item))
    return out


def parse_cv(text: str, *, source: str = CV_SOURCE) -> CV:
    """Return the :class:`CV` the document *text* declares.

    Raises:
        RuntimeError: naming the offending declaration for a syntax error, an
            unknown key, a missing or empty required field, an empty section,
            or a format version this module does not read.
    """
    import tomllib

    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"{source} is not valid TOML: {exc}") from exc

    _reject_unknown(source, data, TOP_LEVEL_KEYS)

    version = data.get("format_version")
    if version != CV_FORMAT_VERSION:
        raise RuntimeError(
            f"{source} declares format_version {version!r}; this selfdoc "
            f"reads {CV_FORMAT_VERSION}."
        )

    raw_identity = data.get("identity")
    if not isinstance(raw_identity, dict):
        raise RuntimeError(
            f"{source} declares no [identity] table -- the name, headline, "
            f"location, email and summary the page opens with."
        )
    where = f"{source}: [identity]"
    _reject_unknown(where, raw_identity, IDENTITY_KEYS)
    profiles = []
    raw_profiles = raw_identity.get("profile") or []
    if not isinstance(raw_profiles, list):
        raise RuntimeError(f"{where}: 'profile' must be a list of tables.")
    for index, item in enumerate(raw_profiles, start=1):
        spot = f"{source}: [[identity.profile]] #{index}"
        if not isinstance(item, dict):
            raise RuntimeError(f"{spot} is not a table.")
        _reject_unknown(spot, item, PROFILE_KEYS)
        profiles.append(Profile(
            label=_text(spot, item, "label"),
            url=_text(spot, item, "url"),
        ))
    identity = Identity(
        name=_text(where, raw_identity, "name"),
        headline=_text(where, raw_identity, "headline"),
        location=_text(where, raw_identity, "location"),
        email=_text(where, raw_identity, "email"),
        summary=_text(where, raw_identity, "summary"),
        photo=_text(where, raw_identity, "photo", required=False),
        updated=_text(where, raw_identity, "updated", required=False),
        profiles=tuple(profiles),
    )

    skills = []
    seen_categories: set[tuple[str, ...]] = set()
    for spot, block in _blocks(source, data, "skills"):
        _reject_unknown(spot, block, SKILL_KEYS)
        category = _text(spot, block, "category")
        _reject_repeat(
            spot, seen_categories, (category,), category, "skill category",
        )
        skills.append(SkillGroup(
            category=category, items=_strings(spot, block, "items"),
        ))

    projects = []
    seen_projects: set[tuple[str, ...]] = set()
    for spot, block in _blocks(source, data, "projects"):
        _reject_unknown(spot, block, PROJECT_KEYS)
        name = _text(spot, block, "name")
        _reject_repeat(spot, seen_projects, (name,), name, "project")
        notes = _strings(spot, block, "notes", required=False)
        technologies = _strings(spot, block, "technologies", required=False)
        if not notes and not technologies:
            raise RuntimeError(
                f"{spot} ({name}) declares neither 'notes' nor "
                f"'technologies', so the entry would be a bare heading."
            )
        projects.append(Project(
            name=name, notes=notes, technologies=technologies,
        ))

    interests = []
    seen_interests: set[tuple[str, ...]] = set()
    for spot, block in _blocks(source, data, "interests"):
        _reject_unknown(spot, block, INTEREST_KEYS)
        title = _text(spot, block, "title")
        _reject_repeat(spot, seen_interests, (title,), title, "interest")
        interests.append(Interest(
            title=title,
            body=_text(spot, block, "body"),
        ))

    education = []
    seen_education: set[tuple[str, ...]] = set()
    for spot, block in _blocks(source, data, "education"):
        _reject_unknown(spot, block, EDUCATION_KEYS)
        degree = _text(spot, block, "degree")
        institute = _text(spot, block, "institute")
        # Degree and school together identify the entry: two degrees from
        # one university, and one degree from two universities, are both
        # ordinary; the same degree twice at the same place is a mistake.
        _reject_repeat(
            spot, seen_education, (degree, institute),
            f"{degree} at {institute}", "education entry",
        )
        education.append(Education(
            degree=degree,
            years=_text(spot, block, "years"),
            institute=institute,
            location=_text(spot, block, "location"),
            institute_url=_text(spot, block, "institute_url", required=False),
            focus=_text(spot, block, "focus", required=False),
            thesis=_text(spot, block, "thesis", required=False),
            course_url=_text(spot, block, "course_url", required=False),
        ))

    experience = []
    seen_experience: set[tuple[str, ...]] = set()
    for spot, block in _blocks(source, data, "experience"):
        _reject_unknown(spot, block, EXPERIENCE_KEYS)
        role = _text(spot, block, "role")
        company = _text(spot, block, "company")
        period = _text(spot, block, "period")
        # Two stints in one role at one employer are a real career shape,
        # so the period is part of the identity; all three the same is one
        # post declared twice.
        _reject_repeat(
            spot, seen_experience, (role, company, period),
            f"{role} at {company} ({period})", "post",
        )
        experience.append(Experience(
            role=role,
            period=period,
            company=company,
            location=_text(spot, block, "location"),
            company_url=_text(spot, block, "company_url", required=False),
            body=_text(spot, block, "body", required=False),
        ))

    languages = []
    seen_languages: set[tuple[str, ...]] = set()
    for spot, block in _blocks(source, data, "languages"):
        _reject_unknown(spot, block, LANGUAGE_KEYS)
        name = _text(spot, block, "name")
        _reject_repeat(spot, seen_languages, (name,), name, "language")
        languages.append(Language(
            name=name,
            level=_text(spot, block, "level"),
            url=_text(spot, block, "url", required=False),
        ))

    raw_contact = data.get("contact")
    if not isinstance(raw_contact, dict):
        raise RuntimeError(
            f"{source} declares no [contact] table -- how a reader reaches "
            f"the person the CV is about."
        )
    contact_where = f"{source}: [contact]"
    _reject_unknown(contact_where, raw_contact, CONTACT_KEYS)

    return CV(
        identity=identity,
        skills=tuple(skills),
        projects=tuple(projects),
        interests=tuple(interests),
        education=tuple(education),
        experience=tuple(experience),
        languages=tuple(languages),
        contact=_text(contact_where, raw_contact, "body"),
    )


def load_cv(path: str) -> CV:
    """Return the CV declared in the TOML document at *path*."""
    with open(path, "r", encoding="utf-8") as f:
        return parse_cv(f.read(), source=path)


# -- rendering ----------------------------------------------------------------


def _link(text: str, url: str) -> str:
    return f"[{text}]({url})" if url else text


def render_cv_markdown(cv: CV) -> str:
    """Return the CV as the Markdown body of a page.

    Section headings are fixed, because they are the document's structure
    rather than one of its facts.
    """
    identity = cv.identity
    parts: list[str] = [f"# {identity.name}", ""]
    if identity.photo:
        parts += [f"![Profile picture]({identity.photo})", ""]

    header = [identity.headline, identity.location,
              _link(identity.email, f"mailto:{identity.email}")]
    header += [_link(p.label, p.url) for p in identity.profiles]
    parts += header + ["", identity.summary, ""]

    parts += ["## Skills", ""]
    for group in cv.skills:
        parts.append(f"- **{group.category}:** {', '.join(group.items)}")
    parts.append("")

    parts += ["## Projects", ""]
    for project in cv.projects:
        parts += [f"### {project.name}", ""]
        for note in project.notes:
            parts.append(f"- {note}")
        if project.technologies:
            parts.append(
                f"- **Technologies used:** {', '.join(project.technologies)}"
            )
        parts.append("")

    parts += ["## Hobbies & interests", ""]
    for interest in cv.interests:
        parts += [f"### {interest.title}", "", interest.body, ""]

    parts += ["## Education", ""]
    for entry in cv.education:
        parts += [f"### {entry.degree}", ""]
        parts.append(f"- **Year:** {entry.years}")
        parts.append(
            f"- **Institute:** {_link(entry.institute, entry.institute_url)}"
        )
        parts.append(f"- **Location:** {entry.location}")
        if entry.focus:
            parts.append(f"- **Focus:** {entry.focus}")
        if entry.thesis:
            parts.append(f"- **Thesis:** {entry.thesis}")
        if entry.course_url:
            parts.append(f"- [Course details]({entry.course_url})")
        parts.append("")

    parts += ["## Work experience", ""]
    for entry in cv.experience:
        parts += [f"### {entry.role}", ""]
        parts.append(f"- **Period:** {entry.period}")
        parts.append(
            f"- **Company:** {_link(entry.company, entry.company_url)}"
        )
        parts.append(f"- **Location:** {entry.location}")
        parts.append("")
        if entry.body:
            parts += [entry.body, ""]

    parts += ["## Languages", ""]
    for language in cv.languages:
        parts.append(
            f"- {_link(language.name, language.url)} – {language.level}"
        )
    parts.append("")

    parts += ["## Contact information", "", cv.contact, ""]

    if identity.updated:
        parts += [f"Last updated on {identity.updated}", ""]

    return "\n".join(parts).rstrip("\n") + "\n"


def cv_person_jsonld(cv: CV, author) -> dict:
    """Return the ``Person`` a CV page states, as a JSON-LD document.

    The identity itself -- name, url, sameAs -- comes from the site's declared
    author, so a CV page and the front page name the same person.  What the CV
    adds is what a CV knows: the job title, the summary, the languages, the
    schools, and the external profiles it lists (folded into ``sameAs`` after
    the declared ones, without repeating any).
    """
    declared_same_as = [str(u) for u in ((author or {}).get("same_as") or [])]
    same_as = list(declared_same_as)
    for profile in cv.identity.profiles:
        if profile.url not in same_as:
            same_as.append(profile.url)

    extra = {
        # The identity's name is the site's, so it stays the same on every
        # page; a CV that spells the same person's name out more fully
        # contributes that spelling as an alternate rather than a second
        # entity with a different name.
        "alternateName": (
            cv.identity.name
            if cv.identity.name != (author or {}).get("name") else ""
        ),
        "jobTitle": cv.identity.headline,
        "description": cv.identity.summary,
        "email": f"mailto:{cv.identity.email}",
        "address": {
            "@type": "PostalAddress",
            "addressLocality": cv.identity.location,
        },
        "knowsLanguage": [
            {"@type": "Language", "name": language.name}
            for language in cv.languages
        ],
        "alumniOf": [
            {
                "@type": "EducationalOrganization",
                "name": entry.institute,
                **({"url": entry.institute_url} if entry.institute_url else {}),
            }
            for entry in cv.education
        ],
    }
    person = person_entity(
        {**(author or {}), "same_as": same_as}, context=True, extra=extra,
    )
    return person


#: The attribute the rendered page carries its Person in, for the SEO tag
#: builder to lift into the head.
#:
#: A directive resolves *before* the Markdown converter runs, so anything it
#: emits is text the converter will rewrite: a JSON-LD script in body position
#: comes back with the summary's link turned into an anchor tag inside a JSON
#: string, and an HTML-escaped attribute fares no better, because the inline
#: transforms run across attribute values too.  The payload therefore crosses
#: the conversion base64-encoded -- an alphabet with no Markdown meaning --
#: and is decoded into real structured data in the head, where the page's
#: other JSON-LD is emitted.
CV_PERSON_ATTR = "data-cv-person"

_PERSON_ATTR_RE = re.compile(rf'{CV_PERSON_ATTR}="([A-Za-z0-9+/=]*)"')


def render_cv_page(cv: CV, author) -> str:
    """Return the page body: the CV, carrying the Person it states."""
    person = json.dumps(cv_person_jsonld(cv, author))
    payload = base64.b64encode(person.encode("utf-8")).decode("ascii")
    marker = f'<div class="cv-person" {CV_PERSON_ATTR}="{payload}"></div>'
    return f"{marker}\n\n{render_cv_markdown(cv)}"


def extract_cv_person(body_html: str) -> str | None:
    """Return the Person JSON a rendered CV page carries, or None.

    Raises:
        RuntimeError: when the attribute is there but does not decode to a
            JSON object -- a page that carried a broken entity would publish
            it as if it were a fact.
    """
    match = _PERSON_ATTR_RE.search(body_html or "")
    if not match:
        return None
    try:
        text = base64.b64decode(match.group(1), validate=True).decode("utf-8")
        data = json.loads(text)
    except Exception as exc:
        raise RuntimeError(
            f"the CV page's {CV_PERSON_ATTR} attribute does not decode to "
            f"JSON: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise RuntimeError(
            f"the CV page's {CV_PERSON_ATTR} attribute must hold a JSON "
            f"object naming one Person."
        )
    return json.dumps(data)

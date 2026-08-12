"""The site's declared author, as the one Person its structured data names.

A selfdoc site has exactly one author, declared in ``selfdoc.json`` under
``author`` and required there.  Every emitter that needs an identity -- the
per-page article's author and publisher, the front page's standalone entity,
the CV page's profile -- reads it through this module, so a site states the
same Person everywhere and states it once.

What used to happen instead is why the block is required: with no author
declared, the emitters minted ``{"@type": "Organization", "name":
<project_name>}``, inventing an organisation out of a directory name and
publishing it as fact.  That path is gone.  A caller that reaches these
functions without a declared author gets a refusal naming the config key.
"""

from __future__ import annotations

#: Every key an ``author`` block may carry, mirroring the config schema.
AUTHOR_KEYS = ("name", "url", "same_as")


def _require(author) -> dict:
    """Return the author block, or raise naming what is missing."""
    if not isinstance(author, dict) or not author.get("name") \
            or not author.get("url"):
        raise ValueError(
            "structured data needs the declared author, and this build has "
            "none with both 'name' and 'url'. selfdoc.json requires "
            '"author": {"name": ..., "url": ...}; there is no inferred '
            "author and no organisation is minted from the project name."
        )
    return author


def person_entity(author, *, context: bool = False, extra: dict | None = None) -> dict:
    """Return the declared author as a schema.org ``Person``.

    ``context`` adds ``@context`` for an entity emitted as its own JSON-LD
    document rather than nested inside one.  ``extra`` carries the properties
    only a particular page knows -- a CV's occupation, languages and schools
    -- and is merged after the identity properties so the identity itself is
    never overwritten by a caller.

    Raises:
        ValueError: when no author is declared, naming the config key.
    """
    declared = _require(author)
    entity: dict = {}
    if context:
        entity["@context"] = "https://schema.org"
    entity["@type"] = "Person"
    entity["name"] = declared["name"]
    entity["url"] = declared["url"]
    same_as = [str(u) for u in (declared.get("same_as") or []) if str(u).strip()]
    if same_as:
        entity["sameAs"] = same_as
    for key, value in (extra or {}).items():
        if value:
            entity[key] = value
    return entity

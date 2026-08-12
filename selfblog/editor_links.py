"""Cross-repository link targets, addressed the way a post has to address them.

A post is a site citizen.  It is emitted at ``blog/<post-slug>/`` on the
site root -- in a standalone build and on the assembled site alike -- while
a project's documentation is served under that project's own slug.  So a
link from a post to a project page is not the address that project's own
pages use between themselves: it is the project-mounted address, reached
from two directories down.

Both halves of that sentence are read from the authority rather than
restated here.  :func:`selfblog.shared.page_target` decides where a
manifest page lives on the site, and :func:`selfblog.shared.post_target`
decides where a post lives; the number of hops back to the site root is
derived from the second, so a change to either address scheme moves these
links with it.

What is offered
---------------

Every local registry entry's ``.selfdoc/manifest.json``: each page (title
and address) and each of its headings (the manifests carry heading anchors,
and the anchor a manifest records is the id the built page really has).
The result is one flat list across every repository, because a post's link
does not care which project wrote the page it points at.

The home project
----------------

The assembly's roster names one project served at the site root instead of
under its slug, and its pages carry no project segment.  The editor cannot
know which project that is: the roster lives in the assembly repository,
and the editor never contacts it.  So every target is offered at its
project-mounted address -- which is the right answer for every project but
one, and a wrong answer the deploy's own reference check reports rather
than a wrong page silently served.
"""

from __future__ import annotations

import json
import os

from selfblog.shared import page_target, post_target, target_output_path

#: How many directories a post sits below the site root.  Derived from the
#: post address itself (``blog/<slug>/index.html`` -> 2) so the hop and the
#: address can never disagree.
POST_DEPTH = len(target_output_path(post_target("slug")).split("/")) - 1

#: The relative hop from a post's own directory back to the site root.
TO_SITE_ROOT = "../" * POST_DEPTH

#: Where a project keeps the manifest the editor reads.
MANIFEST_REL = os.path.join(".selfdoc", "manifest.json")


class ManifestError(RuntimeError):
    """A manifest exists but cannot be read, and the message says how."""


def target_href(project_slug, page_path, anchor=""):
    """The link a post writes to reach *page_path* of *project_slug*.

    Document-relative, from the post's own emitted directory: the site has
    to resolve under any mount point, so an origin-absolute link would be
    a defect the reference check reports.
    """
    href = TO_SITE_ROOT + page_target(project_slug, page_path)
    return f"{href}#{anchor}" if anchor else href


def load_manifest(path):
    """Read one project manifest, or refuse.

    Returns:
        The parsed manifest, or None when there is no manifest at *path*.
        Absence is genuine: a project that has never been built has no
        manifest, and offering nothing from it is the correct answer.

    Raises:
        ManifestError: The file exists and is not readable JSON.  It was
            written by a build that meant something by it, so guessing is
            worse than saying so.
    """
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"{path} is not a readable manifest: {exc}") from None


def manifest_targets(manifest, repo_name):
    """Every link target one manifest offers, pages first, then sections.

    Each target carries the address twice: ``address`` is site-relative
    (what the assembly serves it at) and ``href`` is what a post writes to
    reach it.  Both are derived, never typed out.
    """
    slug = manifest.get("slug") or ""
    project = manifest.get("name") or slug
    targets = []
    for page in manifest.get("pages") or []:
        path = page.get("path") or ""
        if not path:
            continue
        title = page.get("title") or path
        targets.append({
            "kind": "page",
            "repo": repo_name,
            "slug": slug,
            "project": project,
            "title": title,
            "page": path,
            "anchor": "",
            "address": page_target(slug, path),
            "href": target_href(slug, path),
        })
        for heading in page.get("headings") or []:
            anchor = heading.get("anchor") or ""
            text = heading.get("text") or ""
            if not anchor or not text:
                continue
            targets.append({
                "kind": "section",
                "repo": repo_name,
                "slug": slug,
                "project": project,
                "title": text,
                "page": path,
                "page_title": title,
                "level": heading.get("level"),
                "anchor": anchor,
                "address": f"{page_target(slug, path)}#{anchor}",
                "href": target_href(slug, path, anchor),
            })
    return targets


class TargetIndex:
    """Every registry entry's link targets, re-read when a manifest changes.

    The editor asks for completions on a keystroke, so the manifests are
    not re-parsed each time -- but they are also not cached forever: the
    key is the manifest's own size and modification time, so a build that
    rewrites one is picked up on the next keystroke with no restart.
    """

    def __init__(self, registry):
        self.registry = registry
        self._cache = {}

    def _entry_targets(self, entry):
        if getattr(entry, "kind", "") != "local":
            # A remote entry is validated but not served; its manifest is
            # in a repository this editor does not fetch.
            return []
        path = os.path.join(entry.path, MANIFEST_REL)
        try:
            stat = os.stat(path)
        except OSError:
            self._cache.pop(entry.name, None)
            return []
        stamp = (stat.st_mtime_ns, stat.st_size)
        cached = self._cache.get(entry.name)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        manifest = load_manifest(path)
        targets = [] if manifest is None else manifest_targets(
            manifest, entry.name,
        )
        self._cache[entry.name] = (stamp, targets)
        return targets

    def all_targets(self):
        """Every target from every local registry entry, in registry order."""
        found = []
        for entry in self.registry:
            found.extend(self._entry_targets(entry))
        return found

    def search(self, query="", limit=40):
        """The targets matching *query*, pages before their own sections.

        The match is a case-insensitive substring over what an author would
        type: the title, the address, and the project's name.  An empty
        query matches everything, which is what makes the popup useful the
        moment a link is opened rather than only after some prefix is typed.
        """
        needle = (query or "").strip().lower()
        found = []
        for target in self.all_targets():
            if needle and not any(
                needle in str(target.get(field) or "").lower()
                for field in ("title", "address", "project", "page")
            ):
                continue
            found.append(target)
            if len(found) >= limit:
                break
        return found

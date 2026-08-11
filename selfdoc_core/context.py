"""The search index entry dataclass.

Pages carry their own state through the build as the address plus
the per-page dict :func:`selfdoc_core.html.generate_html` builds; a
search entry is the one record that outlives a single build, so it
is the one that gets a type.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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

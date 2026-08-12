"""The crawler policy, declared once for every robots.txt this repo writes.

Two generators emit a robots.txt: a project's own build writes one at its
output root, and the assembly's shared-element generator writes the
site-wide one that is actually served.  They read the policy from here, so
a crawler the site allows cannot be one its projects disallow -- and a
disallow written into one of them cannot leave the other allowing it.
"""

from __future__ import annotations

#: Every crawler the generated robots.txt names, in the order it names them.
#: The wildcard already allows all of them; naming each one is what keeps a
#: future disallow from being written once and applying to everybody by
#: accident.
ROBOTS_AGENTS: tuple[str, ...] = (
    "*", "GPTBot", "ChatGPT-User", "Google-Extended", "PerplexityBot",
    "ClaudeBot", "Googlebot", "OAI-SearchBot",
)


def render_robots_txt(sitemap_url: str) -> str:
    """Return robots.txt text allowing :data:`ROBOTS_AGENTS` and naming a sitemap.

    Args:
        sitemap_url: Absolute URL of the sitemap this robots.txt points at.
            Crawlers find a sitemap by being told where it is, and the
            ``Sitemap:`` directive takes an absolute URL.
    """
    lines: list[str] = []
    for agent in ROBOTS_AGENTS:
        lines.append(f"User-agent: {agent}")
        lines.append("Allow: /")
        lines.append("")
    lines.append(f"Sitemap: {sitemap_url}")
    return "\n".join(lines) + "\n"

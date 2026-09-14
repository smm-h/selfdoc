// Package robots holds the crawler policy, declared once for every robots.txt
// this repository writes.
//
// Two generators emit a robots.txt: a project's own build writes one at its
// output root, and the assembly's shared-element generator writes the site-wide
// one that is actually served. They read the policy from here, so a crawler the
// site allows cannot be one its projects disallow -- and a disallow written
// into one of them cannot leave the other allowing it.
package robots

import "strings"

// Agents names every crawler the generated robots.txt names, in the order it
// names them.
//
// The wildcard already allows all of them; naming each one is what keeps a
// future disallow from being written once and applying to everybody by
// accident.
//
// The slice is package state a caller must not write to: mutating an element
// would change what every generated robots.txt says. Read it, never assign into
// it.
var Agents = []string{
	"*", "GPTBot", "ChatGPT-User", "Google-Extended", "PerplexityBot",
	"ClaudeBot", "Googlebot", "OAI-SearchBot", "Claude-SearchBot",
}

// RenderRobotsTxt returns robots.txt text allowing every agent in [Agents] and
// naming a sitemap.
//
// sitemapURL is the absolute URL of the sitemap this robots.txt points at.
// Crawlers find a sitemap by being told where it is, and the "Sitemap:"
// directive takes an absolute URL.
func RenderRobotsTxt(sitemapURL string) string {
	var lines []string
	for _, agent := range Agents {
		lines = append(lines, "User-agent: "+agent)
		lines = append(lines, "Allow: /")
		lines = append(lines, "")
	}
	lines = append(lines, "Sitemap: "+sitemapURL)
	return strings.Join(lines, "\n") + "\n"
}

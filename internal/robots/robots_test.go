package robots

import (
	"strings"
	"testing"
)

// TestAgentsAreNamedInOrder pins the declared order. The order is what the
// rendered file reproduces, and a generator that reordered them would produce a
// file that no longer matches the one the Python emitted.
func TestAgentsAreNamedInOrder(t *testing.T) {
	t.Parallel()
	want := []string{
		"*", "GPTBot", "ChatGPT-User", "Google-Extended", "PerplexityBot",
		"ClaudeBot", "Googlebot", "OAI-SearchBot", "Claude-SearchBot",
	}
	if len(Agents) != len(want) {
		t.Fatalf("Agents = %q, want %q", Agents, want)
	}
	for i := range want {
		if Agents[i] != want[i] {
			t.Errorf("Agents[%d] = %q, want %q", i, Agents[i], want[i])
		}
	}
}

// TestEveryAgentIsAllowed is the ported assertion from the assembly root-files
// suite: one declaration of the policy, read by both generators, so a disallow
// added to one cannot leave the other allowing it.
func TestEveryAgentIsAllowed(t *testing.T) {
	t.Parallel()
	got := RenderRobotsTxt("https://docs.example.com/sitemap.xml")
	for _, agent := range Agents {
		want := "User-agent: " + agent + "\nAllow: /"
		if !strings.Contains(got, want) {
			t.Errorf("robots.txt does not contain %q:\n%s", want, got)
		}
	}
}

// TestNamesTheAICrawlersExplicitly ports the assertion that the allowlist is
// deliberate: naming each one is the whole point.
func TestNamesTheAICrawlersExplicitly(t *testing.T) {
	t.Parallel()
	got := RenderRobotsTxt("https://docs.example.com/sitemap.xml")
	for _, agent := range []string{
		"GPTBot", "ChatGPT-User", "Google-Extended", "PerplexityBot",
		"ClaudeBot", "Googlebot", "OAI-SearchBot", "Claude-SearchBot",
	} {
		if !strings.Contains(got, "User-agent: "+agent) {
			t.Errorf("robots.txt does not name %q:\n%s", agent, got)
		}
	}
}

// TestNamesTheSitemap ports the build suite's assertion that the sitemap line
// is present and absolute.
func TestNamesTheSitemap(t *testing.T) {
	t.Parallel()
	got := RenderRobotsTxt("https://example.com/sitemap.xml")
	if !strings.Contains(got, "User-agent: *\nAllow: /") {
		t.Errorf("missing wildcard stanza:\n%s", got)
	}
	if !strings.Contains(got, "Sitemap: https://example.com/sitemap.xml") {
		t.Errorf("missing sitemap line:\n%s", got)
	}
}

// TestRenderedTextIsByteForByte pins the whole document, which is what the
// Python emitted for the same argument.
func TestRenderedTextIsByteForByte(t *testing.T) {
	t.Parallel()
	want := "User-agent: *\nAllow: /\n\n" +
		"User-agent: GPTBot\nAllow: /\n\n" +
		"User-agent: ChatGPT-User\nAllow: /\n\n" +
		"User-agent: Google-Extended\nAllow: /\n\n" +
		"User-agent: PerplexityBot\nAllow: /\n\n" +
		"User-agent: ClaudeBot\nAllow: /\n\n" +
		"User-agent: Googlebot\nAllow: /\n\n" +
		"User-agent: OAI-SearchBot\nAllow: /\n\n" +
		"User-agent: Claude-SearchBot\nAllow: /\n\n" +
		"Sitemap: https://example.com/sitemap.xml\n"
	if got := RenderRobotsTxt("https://example.com/sitemap.xml"); got != want {
		t.Errorf("RenderRobotsTxt() = %q, want %q", got, want)
	}
}

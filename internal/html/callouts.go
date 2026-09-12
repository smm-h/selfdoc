package html

import "sort"

// The framework's icon set this build emits, copied verbatim from its own
// sources so a server-emitted component and a factory-built one carry the
// same glyph.
const (
	// ChevronIcon is the framework's own chevron.
	ChevronIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
		`stroke-width="2.5"><path d="M6 9l6 6 6-6"/></svg>`
	// CloseIcon dismisses a dialog or a notice.
	CloseIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
		`stroke-width="2"><path d="M5 5l14 14M19 5L5 19"/></svg>`
	// MenuIcon opens the mobile sidebar.
	MenuIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
		`stroke-width="2"><path d="M3 6h18M3 12h18M3 18h18"/></svg>`
	// InfoIcon marks the "info" callout kind.
	InfoIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
		`stroke-width="2"><rect x="3" y="3" width="18" height="18"/>` +
		`<path d="M12 10v6M12 7v.5"/></svg>`
	// WarnIcon marks the "warn" and "danger" callout kinds.
	WarnIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
		`stroke-width="2"><path d="M12 3L2 21h20z"/>` +
		`<path d="M12 10v5M12 18v.5"/></svg>`
	// NoteIcon marks the "note" callout kind.
	NoteIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
		`stroke-width="2"><path d="M17 3l4 4L8 20H4v-4z"/></svg>`
	// CheckIcon marks the "tip" callout kind.
	CheckIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
		`stroke-width="2.5"><path d="M4 12.5l5 5L20 6"/></svg>`
	// NoticeIcon is the superseded-version banner's glyph. The banner is
	// the "warn" kind, so it carries the warn glyph.
	NoticeIcon = WarnIcon
)

// CalloutKind is how one admonition type is painted: the framework kind it
// maps to, the glyph it carries, and the ARIA role it takes.
type CalloutKind struct {
	// Kind is the framework callout kind, as in "tm-callout-note".
	Kind string
	// Icon is the inline SVG the callout's title carries.
	Icon string
	// Role is the ARIA role the callout element takes.
	Role string
}

// calloutKinds maps selfdoc's five admonition types onto the framework's
// five callout kinds. "danger" is the one that interrupts, so it is the one
// that gets role="alert".
var calloutKinds = map[string]CalloutKind{
	"NOTE":      {"note", NoteIcon, "note"},
	"TIP":       {"tip", CheckIcon, "note"},
	"IMPORTANT": {"info", InfoIcon, "note"},
	"WARNING":   {"warn", WarnIcon, "note"},
	"CAUTION":   {"danger", WarnIcon, "alert"},
}

// AdmonitionTypes returns, sorted, every admonition name a GitHub-flavored
// blockquote marker may name -- the "TYPE" in a leading "> [!TYPE]" line.
//
// A blockquote whose marker names anything else is a plain blockquote.
func AdmonitionTypes() []string {
	out := make([]string, 0, len(calloutKinds))
	for name := range calloutKinds {
		out = append(out, name)
	}
	sort.Strings(out)
	return out
}

// CalloutKindFor returns how the named admonition type is painted, and
// whether it is one this build recognizes.
func CalloutKindFor(admonitionType string) (CalloutKind, bool) {
	kind, ok := calloutKinds[admonitionType]
	return kind, ok
}

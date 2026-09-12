package shared

import "strings"

// EscapeHTML escapes text for insertion into HTML: the ampersand, the angle
// brackets, the double quote as "&quot;" and the apostrophe as "&#x27;".
//
// It reproduces Python's html.escape(text, quote=True), which is what every
// emitter in this module used. It is deliberately not util.EscapeHTML: that
// one leaves the apostrophe alone, because the page chrome it serves was
// written against a private escaper that does, and Go's own
// html.EscapeString spells the apostrophe "&#39;" rather than "&#x27;".
// A shared page carrying a project blurb with an apostrophe is the ordinary
// case, so the difference is on every deploy.
func EscapeHTML(text string) string {
	text = strings.ReplaceAll(text, "&", "&amp;")
	text = strings.ReplaceAll(text, "<", "&lt;")
	text = strings.ReplaceAll(text, ">", "&gt;")
	text = strings.ReplaceAll(text, `"`, "&quot;")
	return strings.ReplaceAll(text, "'", "&#x27;")
}

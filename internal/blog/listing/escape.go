package listing

import "strings"

// escape escapes text for insertion into HTML, reproducing Python's
// html.escape(text, quote=True): the ampersand, the angle brackets, the double
// quote as &quot; and the apostrophe as &#x27;.
//
// This is deliberately not util.EscapeHTML, which leaves the apostrophe alone
// because the page emitters it serves were written against a private escaper
// that does. The listing's cards were written against the standard library's
// function, and a curated blurb carrying an apostrophe is the ordinary case.
func escape(text string) string {
	text = strings.ReplaceAll(text, "&", "&amp;")
	text = strings.ReplaceAll(text, "<", "&lt;")
	text = strings.ReplaceAll(text, ">", "&gt;")
	text = strings.ReplaceAll(text, `"`, "&quot;")
	return strings.ReplaceAll(text, "'", "&#x27;")
}

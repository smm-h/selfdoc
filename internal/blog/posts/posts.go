// Package posts discovers and validates a project's blog posts.
//
// A post is a dated Markdown file with frontmatter, sitting under the posts
// directory. This package is the whole of what makes one a post: the required
// fields, the required directive declaration, the derived slug and its
// immutability once published, and the type and version keys a post carries
// without declaring them.
//
// # Two callers, one meaning
//
// [Discover] reads the files on disk; [Parse] takes one post's source as a
// string. The editor's render path calls Parse on a buffer that may never be
// saved, so both agree on what a post's source means -- there is one
// definition of a valid post rather than one per entry point.
//
// # The refusals carry coordinates
//
// Every refusal is a [PostError] naming the post's path relative to the posts
// directory, and the line inside the post file when the defect sits at one.
// The check surface turns one of these into a POST diagnostic, and a
// diagnostic's file and line are read by editors, CI annotations and the JSON
// output -- none of which parse prose.
package posts

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"unicode"

	"github.com/smm-h/selfdoc/internal/directives"
	"github.com/smm-h/selfdoc/internal/effects"
	"github.com/smm-h/selfdoc/internal/manifest"
	"github.com/smm-h/selfdoc/internal/util"
)

// dateRe is the accepted spelling of a post's date: four digits, two, two,
// hyphen-separated and nothing else.
var dateRe = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}$`)

// PostError reports an invalid post, with the coordinates of where it is
// invalid.
//
// Path is relative to the posts directory, as a Post's own path is. Line is
// the post file's own line number, or nil for a defect that sits at no
// particular line (a missing frontmatter field).
type PostError struct {
	Message string
	Path    string
	Line    *int
}

// Error renders the refusal.
func (e *PostError) Error() string { return e.Message }

// Post is one post's metadata, in the shape the build, the listing pages and
// the editor read it.
type Post struct {
	// Path is the post's path relative to the posts directory, with
	// forward slashes.
	Path string
	// Title is the post's declared title.
	Title string
	// Date is the post's publication date, YYYY-MM-DD.
	Date string
	// Slug is the address the post is published at: its declared slug,
	// else its title kebab-cased.
	Slug string
	// Tags are the post's tags, empty when it declares none.
	Tags []string
	// Draft reports whether the post is withheld from a build that did not
	// ask for drafts.
	Draft bool
	// Directives is the post's own declaration of whether it may carry
	// directive markers. It is required in the frontmatter and has no
	// default.
	Directives bool
	// Type is always "post", and Versioned always false: a post is a page
	// discovered from a different directory, served from one address
	// forever rather than once per version.
	Type      string
	Versioned bool

	// The pass-through fields, carried verbatim from the frontmatter for
	// whatever reads them. They are untyped because the frontmatter
	// dialect yields a string, a bool, a number or a list depending on how
	// the value was written, and this package interprets none of them.
	Locale       any
	Version      any
	PrevVersion  any
	BumpType     any
	ReleaseURL   any
	RegistryURLs any

	// Content is the post's body: its source with the frontmatter block
	// stripped and its directives NOT resolved.
	Content string
	// Frontmatter is the post's parsed metadata block with the injected
	// keys applied -- "type", "versioned" and a defaulted "tags".
	Frontmatter util.Frontmatter
	// FrontmatterKeys is the order the frontmatter's keys are written back
	// in: the order they appeared in the source, then whichever injected
	// keys the source did not declare.
	//
	// Go maps carry no order, and the page the build injects for this post
	// is rendered by writing the frontmatter back out -- so the order has
	// to be carried rather than recovered.
	FrontmatterKeys []string
}

// ManifestPost narrows p to the slice a project's manifest records.
func (p Post) ManifestPost() manifest.Post {
	return manifest.Post{
		Path:  p.Path,
		Title: p.Title,
		Date:  p.Date,
		Slug:  p.Slug,
		Tags:  p.Tags,
	}
}

// ManifestPosts converts a whole discovery result for the manifest writer,
// keeping the order it came in.
func ManifestPosts(all []Post) []manifest.Post {
	out := make([]manifest.Post, 0, len(all))
	for _, post := range all {
		out = append(out, post.ManifestPost())
	}
	return out
}

// Parse parses and validates one post's Markdown source.
//
// relPath is the post's path relative to the posts directory; it is named in
// every refusal and carried on the result. publishedSlug is the slug this
// post was published under, when it has one -- a different derived slug is a
// slug immutability violation. Pass "" when the post has never been
// published.
func Parse(raw, relPath, publishedSlug string) (Post, error) {
	frontmatter, content, _ := util.ParseFrontmatter(raw)
	keys := frontmatterKeyOrder(raw)

	// -- Validate required fields --------------------------------------

	title, titleDeclared := frontmatter["title"]
	if !titleDeclared || !pyTruthy(title) {
		return Post{}, &PostError{
			Message: fmt.Sprintf(
				"Post %s: 'title' is required and must be non-empty", relPath),
			Path: relPath,
		}
	}

	rawDate, dateDeclared := frontmatter["date"]
	if !dateDeclared || !pyTruthy(rawDate) {
		return Post{}, &PostError{
			Message: fmt.Sprintf("Post %s: 'date' is required", relPath),
			Path:    relPath,
		}
	}
	date := pyStrValue(rawDate)
	if !dateRe.MatchString(date) {
		return Post{}, &PostError{
			Message: fmt.Sprintf(
				"Post %s: 'date' must be YYYY-MM-DD, got %s",
				relPath, pythonRepr(date)),
			Path: relPath,
		}
	}

	// -- The directive declaration -------------------------------------
	//
	// Required, boolean, no default. A post is authored content that may
	// or may not carry executable markers, and which of the two it is
	// cannot be inferred from the file: a post about directive syntax
	// reads like a post that uses it. So the author declares, and a post
	// that declares nothing is refused rather than guessed at.
	// Documentation pages carry no such key -- the whole docs tree is
	// directive territory.

	rawDeclaration, declarationDeclared := frontmatter["directives"]
	if !declarationDeclared {
		return Post{}, &PostError{
			Message: fmt.Sprintf(
				"Post %s: 'directives' is required and has no default. "+
					"Declare 'directives: true' if the post carries directive "+
					"markers, or 'directives: false' if it is plain prose.",
				relPath),
			Path: relPath,
		}
	}
	declaration, isBool := rawDeclaration.(bool)
	if !isBool {
		return Post{}, &PostError{
			Message: fmt.Sprintf(
				"Post %s: 'directives' must be true or false, got %s.",
				relPath, pythonRepr(rawDeclaration)),
			Path: relPath,
		}
	}

	if !declaration {
		// Line numbers are the post file's own: the scan runs over the
		// body, so the frontmatter it sits behind is added back.
		frontmatterOffset := strings.Count(raw, "\n") - strings.Count(content, "\n")
		if found := directives.FindDirectiveMarkers(content); len(found) > 0 {
			line := found[0].LineNumber + frontmatterOffset
			return Post{}, &PostError{
				Message: fmt.Sprintf(
					"Post %s: declares 'directives: false' but line "+
						"%d carries the directive marker '%s'. Declare "+
						"'directives: true' to have it resolved, or remove "+
						"the marker.",
					relPath, line, found[0].Marker),
				Path: relPath,
				Line: &line,
			}
		}
	}

	// -- Auto-generate slug if missing ----------------------------------

	slug := ""
	if declared, ok := frontmatter["slug"]; ok && pyTruthy(declared) {
		slug = pyStrValue(declared)
	} else {
		slug = manifest.ToKebab(pyStrValue(title))
	}

	// -- Slug immutability check ----------------------------------------

	if publishedSlug != "" && publishedSlug != slug {
		return Post{}, &PostError{
			Message: fmt.Sprintf(
				"Post %s: slug changed from %s to %s. Slug immutability "+
					"violation -- slugs cannot change once published.",
				relPath, pythonRepr(publishedSlug), pythonRepr(slug)),
			Path: relPath,
		}
	}

	// -- Inject type and versioned --------------------------------------

	keys = withKey(keys, frontmatter, "type")
	frontmatter["type"] = "post"
	keys = withKey(keys, frontmatter, "versioned")
	frontmatter["versioned"] = false

	// -- Defaults for optional fields -----------------------------------

	if _, declared := frontmatter["tags"]; !declared {
		keys = append(keys, "tags")
		frontmatter["tags"] = []string{}
	}
	tags := frontmatterStrings(frontmatter, "tags")

	draft := pyTruthy(frontmatter["draft"])

	return Post{
		Path:            relPath,
		Title:           pyStrValue(title),
		Date:            date,
		Slug:            slug,
		Tags:            tags,
		Draft:           draft,
		Directives:      declaration,
		Type:            "post",
		Versioned:       false,
		Locale:          frontmatter["locale"],
		Version:         frontmatter["version"],
		PrevVersion:     frontmatter["prev_version"],
		BumpType:        frontmatter["bump_type"],
		ReleaseURL:      frontmatter["release_url"],
		RegistryURLs:    frontmatter["registry_urls"],
		Content:         content,
		Frontmatter:     frontmatter,
		FrontmatterKeys: keys,
	}, nil
}

// Discover discovers, validates and returns the posts under postsDir, sorted
// newest-first and then by slug.
//
// A postsDir that is not a directory holds no posts, which is an answer rather
// than a failure.
//
// manifestPath optionally names an existing manifest file. When it is given,
// slug immutability is enforced against the COMMITTED manifest read out of git
// HEAD rather than the copy on disk, because gen may already have rewritten
// that copy with the new slug by the time this runs. A directory that is not a
// repository, a repository with no commits, and a manifest that was never
// committed each leave the check with nothing to compare against, and it is
// skipped.
//
// Files are read in sorted order, so a duplicate-slug refusal always names the
// same pair in the same direction. The Python walked in directory-listing
// order and could name either post as the second one.
func Discover(postsDir, manifestPath string, handle *effects.Handle) ([]Post, error) {
	info, err := os.Stat(postsDir)
	if err != nil || !info.IsDir() {
		return []Post{}, nil
	}

	// Build a lookup from path -> slug for the committed manifest's posts.
	publishedSlugs := map[string]string{}
	if manifestPath != "" {
		dirPath := filepath.Dir(filepath.Dir(manifestPath))
		committed, err := manifest.LoadFromGit(dirPath, handle)
		if err != nil {
			return nil, err
		}
		if committed != nil {
			for _, entry := range committed.Posts {
				publishedSlugs[entry.Path] = entry.Slug
			}
		}
	}

	posts := []Post{}
	if err := walkPosts(postsDir, postsDir, func(relPath, raw string) error {
		post, err := Parse(raw, relPath, publishedSlugs[relPath])
		if err != nil {
			return err
		}
		posts = append(posts, post)
		return nil
	}); err != nil {
		return nil, err
	}

	// -- Validate slug uniqueness ---------------------------------------

	seen := map[string]string{}
	for _, post := range posts {
		if first, ok := seen[post.Slug]; ok {
			return nil, &PostError{
				Message: fmt.Sprintf(
					"Duplicate slug %s: used by both %s and %s",
					pythonRepr(post.Slug), pythonRepr(first),
					pythonRepr(post.Path)),
				Path: post.Path,
			}
		}
		seen[post.Slug] = post.Path
	}

	// -- Sort: newest first, then slug ascending for ties ---------------

	sort.SliceStable(posts, func(i, j int) bool {
		left, right := dateSortKey(posts[i].Date), dateSortKey(posts[j].Date)
		if left != right {
			return left > right
		}
		return posts[i].Slug < posts[j].Slug
	})

	return posts, nil
}

// walkPosts visits every .md file under dir, top-down and in sorted order,
// calling visit with the file's path relative to root (forward slashes) and
// its contents.
func walkPosts(dir, root string, visit func(relPath, raw string) error) error {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return err
	}
	sort.Slice(entries, func(i, j int) bool { return entries[i].Name() < entries[j].Name() })

	var subdirs []string
	for _, entry := range entries {
		name := entry.Name()
		if entry.IsDir() {
			subdirs = append(subdirs, filepath.Join(dir, name))
			continue
		}
		if !strings.HasSuffix(name, ".md") {
			continue
		}
		fullPath := filepath.Join(dir, name)
		raw, err := os.ReadFile(fullPath)
		if err != nil {
			return err
		}
		relPath, err := filepath.Rel(root, fullPath)
		if err != nil {
			return err
		}
		if err := visit(filepath.ToSlash(relPath), string(raw)); err != nil {
			return err
		}
	}
	for _, subdir := range subdirs {
		if err := walkPosts(subdir, root, visit); err != nil {
			return err
		}
	}
	return nil
}

// dateSortKey turns a YYYY-MM-DD date into the integer the sort compares. The
// date has already been validated against the accepted spelling, so it always
// parses.
func dateSortKey(date string) int64 {
	value, err := strconv.ParseInt(strings.ReplaceAll(date, "-", ""), 10, 64)
	if err != nil {
		return 0
	}
	return value
}

// withKey appends key to the recorded order when the frontmatter does not
// already carry it. A key the source declared keeps the position it was
// written at, which is what assigning to an existing dict key does in Python.
func withKey(keys []string, frontmatter util.Frontmatter, key string) []string {
	if _, declared := frontmatter[key]; declared {
		return keys
	}
	return append(keys, key)
}

// frontmatterKeyOrder returns the keys of a document's frontmatter block in
// the order they were written, each key once.
//
// The line rules are the frontmatter parser's own -- a leading "---", a
// closing line that is "---" after trimming, and a key taken from before the
// first colon of a line that is neither blank nor a comment -- so this returns
// the keys of what the parser produced and nothing else. A test pins the two
// against each other.
func frontmatterKeyOrder(text string) []string {
	if !strings.HasPrefix(text, "---") {
		return nil
	}
	lines := strings.Split(text, "\n")
	end := -1
	for index := 1; index < len(lines); index++ {
		if strings.TrimSpace(lines[index]) == "---" {
			end = index
			break
		}
	}
	if end == -1 {
		return nil
	}
	var keys []string
	seen := map[string]bool{}
	for _, raw := range lines[1:end] {
		line := strings.TrimSpace(raw)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		colon := strings.Index(line, ":")
		if colon == -1 {
			continue
		}
		key := strings.TrimSpace(line[:colon])
		if seen[key] {
			continue
		}
		seen[key] = true
		keys = append(keys, key)
	}
	return keys
}

// frontmatterStrings reads a frontmatter key as a list of strings.
//
// The bracket syntax yields a list; a bare value yields the one-element list
// holding it, which is how every other reader of a tags-like key interprets
// one. The Python carried a bare value through as the scalar it was written
// as, and a manifest then recorded a string where a list belonged.
func frontmatterStrings(frontmatter util.Frontmatter, key string) []string {
	switch typed := frontmatter[key].(type) {
	case []string:
		return append([]string{}, typed...)
	case nil:
		return []string{}
	case string:
		if typed == "" {
			return []string{}
		}
		return []string{typed}
	default:
		return []string{pyStrValue(typed)}
	}
}

// pyTruthy reports whether a frontmatter value is truthy the way Python's
// bool() judges it: an absent value, a false, an empty string, a zero and an
// empty list are all false.
func pyTruthy(value any) bool {
	switch typed := value.(type) {
	case nil:
		return false
	case bool:
		return typed
	case string:
		return typed != ""
	case int64:
		return typed != 0
	case float64:
		return typed != 0
	case []string:
		return len(typed) > 0
	default:
		return true
	}
}

// pyStrValue renders a frontmatter value the way Python's str() does.
func pyStrValue(value any) string {
	switch typed := value.(type) {
	case nil:
		return "None"
	case string:
		return typed
	case bool:
		if typed {
			return "True"
		}
		return "False"
	case int64:
		return strconv.FormatInt(typed, 10)
	case float64:
		return util.PythonFloatRepr(typed)
	case []string:
		return pythonRepr(typed)
	default:
		return fmt.Sprintf("%v", typed)
	}
}

// pythonRepr renders a frontmatter value the way Python's repr does, for the
// refusals that quote an offending value.
func pythonRepr(value any) string {
	switch typed := value.(type) {
	case nil:
		return "None"
	case bool:
		if typed {
			return "True"
		}
		return "False"
	case string:
		return pythonStrRepr(typed)
	case int64:
		return strconv.FormatInt(typed, 10)
	case float64:
		return util.PythonFloatRepr(typed)
	case []string:
		parts := make([]string, len(typed))
		for index, item := range typed {
			parts[index] = pythonStrRepr(item)
		}
		return "[" + strings.Join(parts, ", ") + "]"
	default:
		return fmt.Sprintf("%v", typed)
	}
}

// pythonStrRepr quotes s the way Python's repr(str) does: single quotes
// unless the string contains a single quote and no double quote, the short
// escapes for backslash, tab, newline and carriage return, a \xNN escape for
// every other non-printable below U+0100, and \uXXXX or \UXXXXXXXX above it.
func pythonStrRepr(s string) string {
	quote := byte('\'')
	if strings.Contains(s, "'") && !strings.Contains(s, `"`) {
		quote = '"'
	}
	var builder strings.Builder
	builder.WriteByte(quote)
	for _, r := range s {
		switch {
		case r == rune(quote) || r == '\\':
			builder.WriteByte('\\')
			builder.WriteRune(r)
		case r == '\t':
			builder.WriteString(`\t`)
		case r == '\n':
			builder.WriteString(`\n`)
		case r == '\r':
			builder.WriteString(`\r`)
		case r < 0x20 || r == 0x7f:
			fmt.Fprintf(&builder, `\x%02x`, r)
		case r < 0x7f:
			builder.WriteRune(r)
		case unicode.IsPrint(r):
			builder.WriteRune(r)
		case r < 0x100:
			fmt.Fprintf(&builder, `\x%02x`, r)
		case r < 0x10000:
			fmt.Fprintf(&builder, `\u%04x`, r)
		default:
			fmt.Fprintf(&builder, `\U%08x`, r)
		}
	}
	builder.WriteByte(quote)
	return builder.String()
}

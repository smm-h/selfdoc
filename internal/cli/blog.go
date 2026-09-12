package cli

// registerBlog registers the blog group: the post commands, the authoring
// app, and the documentation publish.
//
// The three used to be top-level groups (`post`, `editor`, `docs publish`),
// which spread one subject -- what this project publishes to the unified site
// and what it writes to get there -- across three places in `--help`. They are
// one group now, and `docs publish` is `blog publish-docs`, a command rather
// than a one-command group.
func (c *cli) registerBlog() {
	group := c.app.Group("blog",
		"Blog posts, the authoring app, and publishing this project's documentation to the unified site")

	c.registerPost(group)
	c.registerEditor(group)
	c.registerPublishDocs(group)
}

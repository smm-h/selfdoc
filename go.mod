module github.com/smm-h/selfdoc

go 1.26.3

require (
	github.com/BurntSushi/toml v1.6.0
	github.com/smm-h/strictcli/go v0.33.0
	github.com/smm-h/stricttest/go v0.2.0
)

// Declared ahead of the packages that will import them, so every later layer
// builds against one resolved set: chroma highlights code blocks, tinymoon
// composes the themes, brotli compresses the build output, strictspec
// generates the document validators, and x/text supplies the Unicode
// collation the search index needs.
require (
	github.com/alecthomas/chroma/v2 v2.27.0
	github.com/andybalholm/brotli v1.2.4
	github.com/smm-h/strictspec/go v0.2.3
	github.com/smm-h/tinymoon v0.11.0
	golang.org/x/text v0.42.0
)

require (
	github.com/dlclark/regexp2/v2 v2.2.1 // indirect
	github.com/smm-h/go-toml-edit v0.3.0 // indirect
)

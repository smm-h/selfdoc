# Go rewrite campaign

Rewrite selfdoc, selfdoc-core and selfblog in Go as one module, `github.com/smm-h/selfdoc`, with one binary, `selfdoc`. Every line of Python is deleted at the end. The Python install on this machine is pinned to the released selfdoc 0.38.1 and selfblog 0.5.0 for the duration; the editable install is restored after the release ships.

## Rulings

All of these were made by the orchestrating session, not by the user, and are freely reversible.

- Effects: an explicit `*effects.Handle` parameter threaded through every engine function that mutates or spawns. No package-level handle.
- Custom directives: the `directives` config key keeps its `resolve(attrs, config, body)` Python contract. selfdoc runs `python3` with an embedded driver script that loads the consumer's file and calls `resolve`, passing attrs/config/body as JSON on stdin and reading Markdown from stdout. A non-zero exit or missing `resolve` is a hard error, never an inline sentinel.
- Python extractor: an embedded Python driver run via `python3` that uses the stdlib `ast` module and emits JSON; the Go side formats it. No tree-sitter, no cgo.
- EXAMPLE001 Python syntax check: `python3 -c` with `ast.parse`.
- Markdown converter: line-for-line port of `selfdoc_core/html.py` and `tokenizer.py`. No goldmark.
- Highlighting: chroma replaces pygments. The three-way custom-property stylesheet is generated from chroma's style definitions. Class names change; accepted.
- OG images: the basic hand-written PNG path only. The predraw rich path is dropped.
- Hash store: version 3 retained. Schema hashes use a Go canonical JSON encoder that reproduces Python `json.dumps(obj, sort_keys=True, separators=(",",":"))` with `ensure_ascii=True`.
- Extractors other than Python: faithful ports of the regex scanners. The Go extractor stays a scanner for now; a `go/ast` port is later work.
- Regexes RE2 cannot express become hand scanners. Where Python `\w` semantics are needed, use `[\p{L}\p{N}_]`.
- HTML escaping: a local escaper that escapes `& < > "` and not `'`, matching Python.
- Command tree of the one binary: `init`, `build --target site|posts|unified|home`, `serve`, `deploy`, `check`, `baseline accept`, `gen`, `gen-data`, `spell-corpus`, `quality`, `post new|list|generate|publish`, `docs publish`, `assembly init|push|status|rebuild|retire|redirects|generate-shared|integrate|verify|preview|sync-workflow`, `editor list-repos|serve`. `check` handles every project kind. All cross-CLI refusals are deleted.
- The assembly deploy workflow installs the Go binary with `go install github.com/smm-h/selfdoc/cmd/selfdoc@v<version>` instead of pip-installing two packages; pagefind stays pip-installed. `sync-workflow` pins one version.
- The `unified` build path and the `deploy` providers are ported for parity.
- Editor: ported with the project directory passed explicitly, no `os.chdir`, no stdout redirection. Publish runs the command in-process through strictcli's programmatic call with an injected writer.
- Distribution: `go install`, plus an npm package and a PyPI package that are thin launchers downloading the matching release binary from the GitHub Release on first run into a per-user cache. No per-platform package names.
- Tests: Go tests per package, ported from the Python tests. The browser suite uses playwright-go behind an `e2e` build tag. Environment isolation via `github.com/smm-h/stricttest/go/hygiene`.
- Repository: stays an rlsbl workspace. The `selfdoc` releasable keeps its `v{version}` history and becomes the root member's releasable; `selfdoc-core` and `selfblog` release histories are closed with `rlsbl transition record`. Version file is `VERSION` at the root. Next version is a minor bump of 0.38.1.

## Dependencies

`github.com/smm-h/strictcli/go` v0.33.0, `github.com/smm-h/strictspec/go` v0.2.3, `github.com/smm-h/stricttest/go` v0.2.0, `github.com/smm-h/tinymoon` v0.11.0, `github.com/alecthomas/chroma/v2`, `github.com/BurntSushi/toml`, `github.com/andybalholm/brotli`, `golang.org/x/text`, `github.com/playwright-community/playwright-go` (tests only).

## Layers

Each layer's packages may be built in parallel; a layer starts after the previous one is committed. Package paths are under `internal/`.

| Layer | Package | Ports |
| --- | --- | --- |
| 0 | `effects`, `util` (frontmatter, atomic write, python-compatible JSON, python-like string and date helpers), `cmd/selfdoc` stub, `go.mod` | `selfdoc_core/effects.py`, `selfdoc_core/utils.py` |
| 1 | `config`, `identity`, `excludes`, `fleet` | `selfdoc_core/config.py`, `identity.py`, `excludes.py`, `fleet.py` |
| 1 | `tokenizer`, `prose`, `tables`, `icons`, `address`, `urls`, `robots` | the same-named `selfdoc_core` modules |
| 1 | `directives`, `catalog` (embedded `directives.toml` + strictspec-generated validator), `lints` (embedded `lints.toml` + validator) | `selfdoc_core/directives.py`, `catalog.py`, `lints.py`, both TOML documents and schemas |
| 1 | `extractors` (base, protocol, registry), `extractors/python` (driver), `extractors/golang` | `selfdoc_core/extractors/{__init__,base,protocol,python,go}.py` |
| 1 | `extractors/typescript`, `extractors/svelte`, `extractors/zig` | the same-named extractor modules |
| 1 | `extractors/dart`, `extractors/kotlin`, `extractors/swift`, `extractors/sql` | the same-named extractor modules |
| 2 | `html` (converter: md_to_html, code blocks via chroma, tables, callouts, glossary, inline, minifiers, heading anchors) | `selfdoc_core/html.py` lines 1-2200 |
| 2 | `page` (chrome: wrap_page, seo tags, nav, toc, breadcrumbs, pickers, notices, search scripts, page meta, pagefind facets) | `selfdoc_core/html.py` lines 2200-end |
| 2 | `themes` (embedded css/json, tinymoon composition), `js` (embedded scripts, loader) | `selfdoc_core/themes/`, `selfdoc_core/js/` |
| 2 | `content`, `resolver` (with the custom-directive python driver) | `selfdoc_core/content.py`, `selfdoc/content.py`, `resolver.py`, `resolution.py` |
| 2 | `staleness`, `ownership`, `manifest`, `revisions`, `spelling` (embedded wordlist) | the same-named modules |
| 2 | `cv`, `gendata`, `gitcommit`, `deploy` | `selfdoc_core/cv.py`, `gendata.py`, `git.py`, `deploy.py` |
| 3 | `build`, `render`, `docs` | `selfdoc_core/build.py`, `render.py`, `docs.py` |
| 3 | `gen`, `strictclisupport` | `selfdoc/gen.py`, `strictcli_support.py` |
| 3 | `check`, `quality`, `spellcorpus` | `selfdoc/check.py`, `quality.py`, `spell_corpus.py` |
| 3 | `blog/posts`, `blog/listing`, `blog/shared`, `blog/chrome`, `blog/sitedirectives`, `blog/check` | the same-named `selfblog` modules |
| 3 | `blog/assembly`, `blog/verify`, `blog/unified` | `selfblog/assembly.py`, `verify.py`, `unified.py` |
| 3 | `blog/preview`, `blog/serving`, `blog/editor` (server, registry, links, analysis, publish, assets, embedded `editor_ui`) | the same-named `selfblog` modules |
| 4 | `cli` (every command), `cmd/selfdoc/main.go`, payload schemas | `selfdoc/cli.py`, `selfblog/cli.py`, `payload_schemas.py` |
| 5 | e2e tests (playwright-go), fleet diff harness under `scripts/`, own-docs build parity | `tests/test_rendered_reality.py`, `tests/rendered_site.py` |
| 6 | Delete Python; convert the repository (rlsbl workspace, CI via `rlsbl scaffold`, `selfdoc.json`, `docs/`, root templates, hooks, npm and PyPI launchers); changelog entries; release file | |

## Brief essentials for every implementor

Faithful port: same behavior, same emitted strings byte for byte where the Python emits text, same error messages. Every subprocess and every write goes through the effects handle. Port the corresponding `tests/test_*.py` into Go table tests in the same package. Scope builds and tests to the package. Commit with `safegit commit -m "<msg>" -- <files>`, one commit per package. Never touch another layer's package. Report exported API and deviations in under 80 lines.

# Orama search as alternative search engine

Pagefind was chosen as the initial search engine. Orama was evaluated and deferred.

## Key findings

- Orama: 22KB bundle, <15ms queries after load, faceted search, vector search, typo tolerance
- Pagefind: chunked lazy-loading, <300KB for 10K pages, WASM-based
- Orama requires loading full index upfront (~2-5MB compressed for 30 projects)
- Web Worker lazy loading makes this invisible to users (2-4s background load)
- Service Worker cache makes repeat visits near-instant

## Implementation approach

- Add "orama" to VALID_SEARCH_ENGINES
- Build index at build time (orama supports save/load)
- Load index in Web Worker (not Service Worker)
- Progressive enhancement: "loading" state, activates when Worker ready
- Pagefind remains default; Orama opt-in via search_engine config

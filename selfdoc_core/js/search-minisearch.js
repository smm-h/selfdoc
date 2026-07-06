// MiniSearch search engine adapter
var _miniSearch = null;
function initSearchEngine(entries) {
  _miniSearch = new MiniSearch({
    fields: ['title', 'body'],
    storeFields: ['title', 'path', 'body'],
    searchOptions: { fuzzy: 0.2, prefix: true }
  });
  entries.forEach(function(entry, idx) {
    entry.id = idx;
  });
  _miniSearch.addAll(entries);
}
function searchEntries(query) {
  if (!_miniSearch || !query) return [];
  return _miniSearch.search(query).slice(0, 10).map(function(result) {
    var highlights = [];
    if (result.match) {
      Object.keys(result.match).forEach(function(term) {
        result.match[term].forEach(function(field) {
          highlights.push({field: field, indices: []});
        });
      });
    }
    var snippet = result.body ? result.body.substring(0, 100) +
      (result.body.length > 100 ? '...' : '') : '';
    return {
      title: result.title,
      path: result.path,
      snippet: snippet,
      score: result.score || 0,
      highlights: highlights
    };
  });
}

// Fuse.js search engine adapter
var _fuse = null;
function initSearchEngine(entries) {
  _fuse = new Fuse(entries, {
    keys: [{name: 'title', weight: 2}, {name: 'body', weight: 1}],
    threshold: 0.3,
    includeMatches: true,
    includeScore: true
  });
}
function searchEntries(query) {
  if (!_fuse || !query) return [];
  return _fuse.search(query).slice(0, 10).map(function(result) {
    var highlights = [];
    if (result.matches) {
      result.matches.forEach(function(m) {
        var indices = m.indices.map(function(pair) { return pair[0]; });
        highlights.push({field: m.key, indices: indices});
      });
    }
    var entry = result.item;
    var snippet = entry.body ? entry.body.substring(0, 100) +
      (entry.body.length > 100 ? '...' : '') : '';
    return {
      title: entry.title,
      path: entry.path,
      snippet: snippet,
      score: 1 - (result.score || 0),
      highlights: highlights
    };
  });
}

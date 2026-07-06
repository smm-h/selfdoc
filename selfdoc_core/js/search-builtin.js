// Built-in search engine
var _searchEntries = null;
function initSearchEngine(entries) {
  _searchEntries = entries;
}
function searchEntries(query) {
  if (!_searchEntries || !query) return [];
  var tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!tokens.length) return [];
  var results = [];
  _searchEntries.forEach(function(entry) {
    var score = 0;
    var highlights = [];
    var titleLower = entry.title.toLowerCase();
    var bodyLower = entry.body.toLowerCase();
    tokens.forEach(function(token) {
      var re = new RegExp('\\b' + token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
      var titleMatches = [];
      var m;
      while ((m = re.exec(entry.title)) !== null) {
        titleMatches.push(m.index);
      }
      if (titleLower === query.toLowerCase()) {
        score += 100;
      }
      if (titleMatches.length > 0) {
        score += 50 * titleMatches.length;
        highlights.push({field: 'title', indices: titleMatches});
      }
      re.lastIndex = 0;
      var bodyMatches = [];
      while ((m = re.exec(entry.body)) !== null) {
        bodyMatches.push(m.index);
      }
      if (bodyMatches.length > 0) {
        score += 10 * bodyMatches.length;
        highlights.push({field: 'body', indices: bodyMatches});
      }
    });
    if (score > 0) {
      var snippet = '';
      var bodyHL = highlights.filter(function(h) { return h.field === 'body'; });
      if (bodyHL.length && bodyHL[0].indices.length) {
        var pos = bodyHL[0].indices[0];
        var start = Math.max(0, pos - 40);
        var end = Math.min(entry.body.length, pos + tokens[0].length + 60);
        snippet = (start > 0 ? '...' : '') +
          entry.body.substring(start, end) +
          (end < entry.body.length ? '...' : '');
      } else {
        snippet = entry.body.substring(0, 100) +
          (entry.body.length > 100 ? '...' : '');
      }
      results.push({
        title: entry.title,
        path: entry.path,
        snippet: snippet,
        score: score,
        highlights: highlights
      });
    }
  });
  results.sort(function(a, b) { return b.score - a.score; });
  return results.slice(0, 10);
}

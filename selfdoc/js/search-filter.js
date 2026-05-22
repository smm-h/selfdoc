// Search filter parser and applicator (Phase 4)
// Provides parseSearchQuery() and applyFilters() for structured search.

var _FILTER_KEYS = ['version', 'locale', 'group', 'type', 'target', 'project', 'tags'];

function parseSearchQuery(rawQuery) {
  // Returns: { text: "...", filters: [{key, values, negated}] }
  // Recognizes:
  //   key=value       -> filter (AND between different keys)
  //   key=a|b         -> OR within field
  //   -key=value      -> negated filter (NOT)
  //   Everything else -> full-text query
  var filters = [];
  var textParts = [];
  var tokens = rawQuery.split(/\s+/).filter(Boolean);

  for (var i = 0; i < tokens.length; i++) {
    var token = tokens[i];
    var negated = false;
    var filterToken = token;

    // Check for negation prefix
    if (filterToken.charAt(0) === '-' && filterToken.indexOf('=') > 0) {
      negated = true;
      filterToken = filterToken.substring(1);
    }

    var eqIdx = filterToken.indexOf('=');
    if (eqIdx > 0) {
      var key = filterToken.substring(0, eqIdx).toLowerCase();
      var rawValue = filterToken.substring(eqIdx + 1);

      if (_FILTER_KEYS.indexOf(key) !== -1 && rawValue) {
        var values = rawValue.split('|').filter(Boolean);
        if (values.length > 0) {
          filters.push({ key: key, values: values, negated: negated });
          continue;
        }
      }
    }

    // Not a recognized filter token -- treat as text
    textParts.push(token);
  }

  // Default filter: if no version= filter is present, inject version=<latest>
  var hasVersionFilter = false;
  for (var j = 0; j < filters.length; j++) {
    if (filters[j].key === 'version') {
      hasVersionFilter = true;
      break;
    }
  }
  if (!hasVersionFilter) {
    var dialog = document.getElementById('search-dialog');
    var defaultVersion = dialog ? dialog.getAttribute('data-default-version') : null;
    if (defaultVersion) {
      filters.push({ key: 'version', values: [defaultVersion], negated: false, auto: true });
    }
  }

  return { text: textParts.join(' '), filters: filters };
}

function applyFilters(entries, filters) {
  // Returns: filtered subset of entries
  // AND between different keys
  // OR within same key (pipe-separated values)
  // NOT for negated filters
  if (!filters || filters.length === 0) return entries;

  return entries.filter(function(entry) {
    for (var i = 0; i < filters.length; i++) {
      var f = filters[i];
      var key = f.key;
      var values = f.values;
      var negated = f.negated;

      var entryValue = entry[key];
      // tags is an array, other fields are strings
      var match = false;

      if (Array.isArray(entryValue)) {
        // Array field (tags): check if any filter value appears in the array
        for (var v = 0; v < values.length; v++) {
          var fv = values[v].toLowerCase();
          for (var t = 0; t < entryValue.length; t++) {
            if (entryValue[t].toLowerCase() === fv) {
              match = true;
              break;
            }
          }
          if (match) break;
        }
      } else {
        // String field: check if entry value matches any filter value
        var ev = (entryValue || '').toLowerCase();
        for (var v2 = 0; v2 < values.length; v2++) {
          if (ev === values[v2].toLowerCase()) {
            match = true;
            break;
          }
        }
      }

      // Negated: entry passes if it does NOT match
      // Normal: entry passes if it DOES match
      if (negated && match) return false;
      if (!negated && !match) return false;
    }
    return true;
  });
}

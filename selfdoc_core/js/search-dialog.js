// Search dialog UI (shared across all engines)
(function() {
  var dialog = document.getElementById('search-dialog');
  if (!dialog) return;
  var searchBase = dialog.getAttribute('data-search-base') || '/';
  var input = dialog.querySelector('.search-input');
  var resultsList = dialog.querySelector('.search-results');
  var closeBtn = dialog.querySelector('.search-close');
  var indexLoaded = false;
  var indexLoading = false;
  var activeIdx = -1;
  var _allEntries = null;
  var _activeFilters = [];

  // Platform detection for keyboard shortcut label
  var isMac = false;
  if (navigator.userAgentData && navigator.userAgentData.platform) {
    isMac = /mac/i.test(navigator.userAgentData.platform);
  } else if (navigator.platform) {
    isMac = /mac/i.test(navigator.platform);
  }
  var shortcutLabel = isMac ? 'Cmd+K' : 'Ctrl+K';

  // Update placeholder and trigger labels with correct shortcut
  input.placeholder = 'Search docs... (' + shortcutLabel + ')';
  var kbdEls = document.querySelectorAll('.search-bar-kbd');
  kbdEls.forEach(function(el) { el.textContent = shortcutLabel; });
  var triggerBtns = document.querySelectorAll('.search-trigger');
  triggerBtns.forEach(function(el) {
    el.title = 'Search (' + shortcutLabel + ')';
  });

  // Create chip container between input and results
  var chipContainer = document.createElement('div');
  chipContainer.className = 'search-chips';
  resultsList.parentNode.insertBefore(chipContainer, resultsList);

  function renderChips(filters) {
    chipContainer.innerHTML = '';
    _activeFilters = filters;
    for (var i = 0; i < filters.length; i++) {
      var f = filters[i];
      var chip = document.createElement('span');
      chip.className = 'search-chip';
      if (f.negated) chip.classList.add('search-chip-negated');

      var label = (f.negated ? '-' : '') + f.key + ': ' + f.values.join(' | ');
      chip.appendChild(document.createTextNode(label + ' '));

      var removeBtn = document.createElement('button');
      removeBtn.className = 'chip-remove';
      removeBtn.type = 'button';
      removeBtn.setAttribute('aria-label', 'Remove filter ' + f.key);
      removeBtn.textContent = '×';
      removeBtn.setAttribute('data-filter-idx', String(i));
      removeBtn.addEventListener('click', function(e) {
        var idx = parseInt(e.target.getAttribute('data-filter-idx'), 10);
        removeFilter(idx);
      });
      chip.appendChild(removeBtn);
      chipContainer.appendChild(chip);
    }
  }

  function removeFilter(idx) {
    if (idx < 0 || idx >= _activeFilters.length) return;
    var removed = _activeFilters[idx];

    // Rebuild input text: remove the filter token from query text,
    // or if it was auto-injected, just re-run without it
    if (!removed.auto) {
      // Remove the filter token from the input
      var filterToken = (removed.negated ? '-' : '') + removed.key + '=' + removed.values.join('|');
      var currentVal = input.value;
      // Remove the token (may be anywhere in the string)
      var newVal = currentVal.replace(filterToken, '').replace(/\s{2,}/g, ' ').trim();
      input.value = newVal;
    }

    // Rebuild filters without the removed one
    _activeFilters.splice(idx, 1);
    renderChips(_activeFilters);
    runFilteredSearch(input.value, _activeFilters);
  }

  function runFilteredSearch(rawQuery, overrideFilters) {
    resultsList.innerHTML = '';
    activeIdx = -1;
    if (!indexLoaded || !_allEntries) {
      if (rawQuery) {
        resultsList.innerHTML = '<li class="search-loading">Loading...</li>';
      }
      return;
    }

    var parsed;
    if (overrideFilters) {
      // When filters are explicitly provided (e.g. after chip removal),
      // only parse text from the raw query
      var textParsed = parseSearchQuery(rawQuery);
      parsed = { text: textParsed.text, filters: overrideFilters };
    } else {
      parsed = parseSearchQuery(rawQuery);
    }

    renderChips(parsed.filters);
    var filtered = applyFilters(_allEntries, parsed.filters);

    // Re-initialize engine with filtered subset
    initSearchEngine(filtered);

    var textQuery = parsed.text;
    if (!textQuery) {
      // No text query but we have filters -- show all filtered results
      if (parsed.filters.length > 0 && filtered.length > 0) {
        var toShow = filtered.slice(0, 20);
        for (var i = 0; i < toShow.length; i++) {
          var entry = toShow[i];
          var li = document.createElement('li');
          li.className = 'search-result-item';
          li.setAttribute('role', 'option');
          li.id = 'search-result-' + i;
          var a = document.createElement('a');
          a.href = searchBase + entry.path;
          var titleEl = document.createElement('div');
          titleEl.className = 'search-result-title';
          titleEl.textContent = entry.title;
          var snippet = document.createElement('div');
          snippet.className = 'search-result-snippet';
          snippet.textContent = entry.body ? entry.body.substring(0, 100) + (entry.body.length > 100 ? '...' : '') : '';
          a.appendChild(titleEl);
          a.appendChild(snippet);
          a.addEventListener('click', function() { closeSearch(); });
          li.appendChild(a);
          resultsList.appendChild(li);
        }
      }
      return;
    }

    var matches = searchEntries(textQuery);
    matches.forEach(function(result, idx) {
      var li = document.createElement('li');
      li.className = 'search-result-item';
      li.setAttribute('role', 'option');
      li.id = 'search-result-' + idx;
      var a = document.createElement('a');
      a.href = searchBase + result.path;
      var titleEl = document.createElement('div');
      titleEl.className = 'search-result-title';
      titleEl.appendChild(highlightText(result.title, result.highlights, 'title'));
      var snippet = document.createElement('div');
      snippet.className = 'search-result-snippet';
      snippet.appendChild(highlightText(result.snippet, result.highlights, 'body'));
      a.appendChild(titleEl);
      a.appendChild(snippet);
      a.addEventListener('click', function() { closeSearch(); });
      li.appendChild(a);
      resultsList.appendChild(li);
    });
    if (matches.length === 0 && textQuery) {
      var noLi = document.createElement('li');
      noLi.className = 'search-no-results';
      noLi.textContent = 'No results for "' + textQuery + '". Try different terms or browse the sidebar.';
      resultsList.appendChild(noLi);
    }
  }

  function loadIndex() {
    if (indexLoaded) return Promise.resolve();
    if (indexLoading) return indexLoading;
    indexLoading = fetch(searchBase + 'search-index.json')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        _allEntries = data;
        initSearchEngine(data);
        indexLoaded = true;
        // Re-render with current query after loading
        if (input.value) runFilteredSearch(input.value);
      });
    return indexLoading;
  }

  function openSearch(initialQuery) {
    dialog.showModal();
    input.value = initialQuery || '';
    resultsList.innerHTML = '';
    chipContainer.innerHTML = '';
    activeIdx = -1;
    _activeFilters = [];
    if (!indexLoaded) {
      resultsList.innerHTML = '<li class="search-loading">Loading...</li>';
    }
    loadIndex().then(function() {
      if (input.value) runFilteredSearch(input.value);
    });
    input.focus();
  }

  function closeSearch() {
    dialog.close();
    // Clear ?q= parameter from URL
    var url = new URL(window.location);
    if (url.searchParams.has('q')) {
      url.searchParams.delete('q');
      history.replaceState(null, '', url.pathname + url.search + url.hash);
    }
  }

  function highlightText(text, highlights, field) {
    var fieldHL = highlights.filter(function(h) { return h.field === field; });
    if (!fieldHL.length) return document.createTextNode(text);
    var allIndices = [];
    fieldHL.forEach(function(h) {
      h.indices.forEach(function(idx) { allIndices.push(idx); });
    });
    if (!allIndices.length) return document.createTextNode(text);
    allIndices.sort(function(a, b) { return a - b; });
    var frag = document.createDocumentFragment();
    var lastEnd = 0;
    var q = input.value.toLowerCase().split(/\s+/).filter(Boolean);
    // Strip filter tokens from q for highlighting
    var textQ = [];
    for (var i = 0; i < q.length; i++) {
      if (q[i].indexOf('=') === -1 && !(q[i].charAt(0) === '-' && q[i].indexOf('=') > 0)) {
        textQ.push(q[i]);
      }
    }
    allIndices.forEach(function(idx) {
      if (idx < lastEnd || idx >= text.length) return;
      // Find which token matches at this position
      var matchLen = 1;
      textQ.forEach(function(token) {
        if (text.substring(idx, idx + token.length).toLowerCase() === token) {
          matchLen = Math.max(matchLen, token.length);
        }
      });
      if (idx > lastEnd) {
        frag.appendChild(document.createTextNode(text.substring(lastEnd, idx)));
      }
      var mark = document.createElement('mark');
      mark.textContent = text.substring(idx, idx + matchLen);
      frag.appendChild(mark);
      lastEnd = idx + matchLen;
    });
    if (lastEnd < text.length) {
      frag.appendChild(document.createTextNode(text.substring(lastEnd)));
    }
    return frag;
  }

  function setActive(idx) {
    var items = resultsList.querySelectorAll('.search-result-item');
    items.forEach(function(li) { li.classList.remove('active'); });
    if (idx >= 0 && idx < items.length) {
      activeIdx = idx;
      items[idx].classList.add('active');
      items[idx].scrollIntoView({ block: 'nearest' });
      input.setAttribute('aria-activedescendant', items[idx].id);
    } else {
      input.removeAttribute('aria-activedescendant');
    }
  }

  var trigger = document.querySelector('.search-trigger, .search-bar-trigger');
  if (trigger) {
    trigger.addEventListener('click', function(e) {
      e.preventDefault();
      openSearch();
    });
  }

  if (closeBtn) {
    closeBtn.addEventListener('click', function() {
      closeSearch();
    });
  }

  document.addEventListener('keydown', function(e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      if (dialog.open) closeSearch();
      else openSearch();
    }
  });

  dialog.addEventListener('click', function(e) {
    if (e.target === dialog) closeSearch();
  });

  input.addEventListener('input', function() {
    runFilteredSearch(input.value);
  });

  input.addEventListener('keydown', function(e) {
    var items = resultsList.querySelectorAll('.search-result-item');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive(Math.min(activeIdx + 1, items.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive(Math.max(activeIdx - 1, 0));
    } else if (e.key === 'Enter' && activeIdx >= 0) {
      e.preventDefault();
      var link = items[activeIdx].querySelector('a');
      if (link) window.location.href = link.href;
    } else if (e.key === 'Escape') {
      closeSearch();
    }
  });

  // Open search with ?q= parameter if present
  var urlQ = new URLSearchParams(window.location.search).get('q');
  if (urlQ) {
    openSearch(urlQ);
  }
})();

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

  function loadIndex() {
    if (indexLoaded) return Promise.resolve();
    if (indexLoading) return indexLoading;
    indexLoading = fetch(searchBase + 'search-index.json')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        initSearchEngine(data);
        indexLoaded = true;
        // Re-render with current query after loading
        if (input.value) renderResults(input.value);
      });
    return indexLoading;
  }

  function openSearch(initialQuery) {
    dialog.showModal();
    input.value = initialQuery || '';
    resultsList.innerHTML = '';
    activeIdx = -1;
    if (!indexLoaded) {
      resultsList.innerHTML = '<li class="search-loading">Loading...</li>';
    }
    loadIndex().then(function() {
      if (input.value) renderResults(input.value);
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
    allIndices.forEach(function(idx) {
      if (idx < lastEnd || idx >= text.length) return;
      // Find which token matches at this position
      var matchLen = 1;
      q.forEach(function(token) {
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

  function renderResults(query) {
    resultsList.innerHTML = '';
    activeIdx = -1;
    if (!query) return;
    if (!indexLoaded) {
      resultsList.innerHTML = '<li class="search-loading">Loading...</li>';
      return;
    }
    var matches = searchEntries(query);
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
    if (matches.length === 0 && query) {
      var noLi = document.createElement('li');
      noLi.className = 'search-no-results';
      noLi.textContent = 'No results for "' + query + '". Try different terms or browse the sidebar.';
      resultsList.appendChild(noLi);
    }
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
    renderResults(input.value);
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

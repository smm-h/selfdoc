// Sortable tables in article content
(function() {
  var article = document.querySelector('article');
  if (!article) return;
  article.querySelectorAll('table').forEach(function(table) {
    var thead = table.querySelector('thead');
    if (!thead) return;
    var ths = thead.querySelectorAll('th');
    ths.forEach(function(th, colIdx) {
      th.addEventListener('click', function() {
        var tbody = table.querySelector('tbody');
        if (!tbody) return;
        var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
        var asc = !th.classList.contains('sort-asc');
        ths.forEach(function(h) { h.classList.remove('sort-asc', 'sort-desc'); });
        th.classList.add(asc ? 'sort-asc' : 'sort-desc');
        var allNum = rows.every(function(r) {
          var c = r.children[colIdx];
          if (!c) return false;
          var t = c.textContent.trim();
          return t !== '' && !isNaN(t);
        });
        rows.sort(function(a, b) {
          var ac = a.children[colIdx], bc = b.children[colIdx];
          if (!ac || !bc) return 0;
          var at = ac.textContent.trim(), bt = bc.textContent.trim();
          if (allNum) return asc ? at - bt : bt - at;
          return asc ? at.localeCompare(bt) : bt.localeCompare(at);
        });
        rows.forEach(function(r) { tbody.appendChild(r); });
      });
    });
  });
})();

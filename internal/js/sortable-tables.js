// Sortable tables in article content
//
// aria-sort IS the sort indicator the framework paints -- the arrow comes
// from `.tm-table th[aria-sort]::after` -- so sorting moves the attribute
// and nothing else. The server renders `aria-sort="none"` on every sortable
// header, which is the state it rendered.
(function() {
  var article = document.querySelector('article');
  if (!article) return;
  article.querySelectorAll('table.tm-table').forEach(function(table) {
    var thead = table.querySelector('thead');
    if (!thead) return;
    var ths = thead.querySelectorAll('th.sortable');
    ths.forEach(function(th, colIdx) {
      th.addEventListener('click', function() {
        var tbody = table.querySelector('tbody');
        if (!tbody) return;
        var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
        var asc = th.getAttribute('aria-sort') !== 'ascending';
        ths.forEach(function(h) { h.setAttribute('aria-sort', 'none'); });
        th.setAttribute('aria-sort', asc ? 'ascending' : 'descending');
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

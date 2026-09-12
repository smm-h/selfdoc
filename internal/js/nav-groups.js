// Nav group collapse persistence
//
// A sidebar group is the framework's JavaScript-free tree row: a native
// <details class="tm-tree-details"> whose <summary> is a .tm-tree-row.  The
// disclosure needs no script -- only the memory of what the reader closed
// does.
(function() {
  var groups = document.querySelectorAll('#tm-nav details.tm-tree-details');
  if (!groups.length) return;
  groups.forEach(function(d) {
    var slug = d.querySelector('.tm-tree-label');
    if (!slug) return;
    var key = 'selfdoc-nav-' + slug.textContent.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-');
    var saved = localStorage.getItem(key);
    if (saved === 'closed') {
      d.removeAttribute('open');
    }
    d.addEventListener('toggle', function() {
      localStorage.setItem(key, d.open ? 'open' : 'closed');
    });
  });
})();

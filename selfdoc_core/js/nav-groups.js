// Nav group collapse persistence
(function() {
  var groups = document.querySelectorAll('.nav-group details');
  if (!groups.length) return;
  groups.forEach(function(d) {
    var slug = d.querySelector('.nav-group-title');
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

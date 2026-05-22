// Scrollspy for TOC (Feature 2, Issue 44)
(function() {
  var tocLinks = document.querySelectorAll('.toc a');
  if (!tocLinks.length) return;
  var headings = [];
  tocLinks.forEach(function(link) {
    var id = link.getAttribute('href').substring(1);
    var el = document.getElementById(id);
    if (el) headings.push({ el: el, link: link });
  });
  var ticking = false;
  function update() {
    var scrollTop = window.scrollY + 100;
    var active = null;
    for (var i = 0; i < headings.length; i++) {
      if (headings[i].el.offsetTop <= scrollTop) {
        active = headings[i];
      }
    }
    tocLinks.forEach(function(a) { a.classList.remove('active'); });
    if (active) {
      active.link.classList.add('active');
      active.link.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
    ticking = false;
  }
  window.addEventListener('scroll', function() {
    if (!ticking) {
      requestAnimationFrame(update);
      ticking = true;
    }
  }, { passive: true });
  update();
})();

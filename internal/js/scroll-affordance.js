// Scroll affordance shadows on overflowing code blocks and tables.
//
// Three states, and the themes paint off all three: `has-overflow` while
// there is anything to scroll to at all, `scrolled-start` while the
// scrollport sits at its left edge, `scrolled-end` while it sits at its
// right. A shadow is painted at an edge exactly when content is hidden
// behind it, so a table that clips mid-word says so on the side it clips.
(function() {
  function setup(container, scroller) {
    if (scroller.scrollWidth <= scroller.clientWidth) return;
    container.classList.add('has-overflow');
    function check() {
      var max = scroller.scrollWidth - scroller.clientWidth;
      container.classList.toggle('scrolled-start', scroller.scrollLeft <= 2);
      container.classList.toggle('scrolled-end', scroller.scrollLeft >= max - 2);
      // When the container IS the scrollport -- a .table-wrap -- its own
      // absolutely positioned edge shadows scroll away with the content.
      // The offset is published so the theme can hold them against the
      // visible box. A .tm-code scrolls its inner <pre>, not itself, so it
      // is left alone and the theme's fallback keeps its shadows still.
      if (container === scroller) {
        container.style.setProperty('--scroll-x', scroller.scrollLeft + 'px');
      }
    }
    scroller.addEventListener('scroll', check, {passive: true});
    check();
  }
  function init() {
    document.querySelectorAll('.tm-code').forEach(function(el) {
      var pre = el.querySelector('pre');
      if (pre) setup(el, pre);
    });
    document.querySelectorAll('.table-wrap').forEach(function(el) {
      setup(el, el);
    });
  }
  init();
  if (window.ResizeObserver) {
    new ResizeObserver(function() {
      document.querySelectorAll('.has-overflow').forEach(function(el) {
        el.classList.remove('has-overflow', 'scrolled-start', 'scrolled-end');
      });
      init();
    }).observe(document.documentElement);
  }
})();

// Scroll affordance gradient on overflowing code blocks and tables
(function() {
  function setup(container, scroller) {
    if (scroller.scrollWidth <= scroller.clientWidth) return;
    container.classList.add('has-overflow');
    function check() {
      if (scroller.scrollLeft + scroller.clientWidth >= scroller.scrollWidth - 2) {
        container.classList.add('scrolled-end');
      } else {
        container.classList.remove('scrolled-end');
      }
    }
    scroller.addEventListener('scroll', check, {passive: true});
    check();
  }
  function init() {
    document.querySelectorAll('.code-block').forEach(function(el) {
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
        el.classList.remove('has-overflow', 'scrolled-end');
      });
      init();
    }).observe(document.documentElement);
  }
})();

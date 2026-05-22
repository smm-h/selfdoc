// Reading progress bar
(function() {
  var bar = document.getElementById('reading-progress');
  if (!bar) return;
  function update() {
    var scrollTop = window.scrollY || document.documentElement.scrollTop;
    var docHeight = document.documentElement.scrollHeight - window.innerHeight;
    if (docHeight <= 0) { bar.style.width = '100%'; return; }
    var progress = Math.min(scrollTop / docHeight * 100, 100);
    bar.style.width = progress + '%';
  }
  window.addEventListener('scroll', update, { passive: true });
  update();
})();

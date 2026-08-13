// Reading progress bar
//
// The scrolling element is #tm-content, not the document: the framework's
// shell is a fixed application frame and the content column is the only
// thing that moves.  Every theme states the same shell, so this is one
// element, not a choice made at runtime.
(function() {
  var bar = document.getElementById('reading-progress');
  var scroller = document.getElementById('tm-content');
  if (!bar || !scroller) return;
  function update() {
    var height = scroller.scrollHeight - scroller.clientHeight;
    if (height <= 0) { bar.style.width = '100%'; return; }
    var progress = Math.min(scroller.scrollTop / height * 100, 100);
    bar.style.width = progress + '%';
  }
  scroller.addEventListener('scroll', update, { passive: true });
  update();
})();

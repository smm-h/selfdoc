// Dismissal for the superseded-version notice.
//
// The framework paints the banner and dresses the dismiss button; removing
// the node is deliberately the consumer's decision, so this is where the
// removal lives. The dismissal is keyed per version: dismissing the notice
// on v0.1.0 says nothing about v0.2.0, so a reader who lands on a
// different old version is told again.
(function() {
  var notice = document.querySelector('.tm-notice[data-notice-key]');
  if (!notice) return;
  var key = 'selfdoc-version-notice-' + (notice.getAttribute('data-notice-key') || '');
  var stored = null;
  try { stored = localStorage.getItem(key); } catch (e) { stored = null; }
  if (stored === 'dismissed') {
    notice.hidden = true;
    return;
  }
  var button = notice.querySelector('.tm-notice-dismiss');
  if (!button) return;
  button.addEventListener('click', function() {
    notice.hidden = true;
    try { localStorage.setItem(key, 'dismissed'); } catch (e) { /* private mode */ }
  });
})();

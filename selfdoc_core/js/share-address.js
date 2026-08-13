// Share control: copy either of the page's two addresses.
// The evergreen and pinned URLs are both rendered into the button's
// data-share-url by the build; this file only copies one to the
// clipboard and confirms it.
//
// One copy path, not two. There used to be a document.execCommand
// fallback behind a hidden textarea, which is a banned native control and
// was never reached anyway: navigator.clipboard.writeText is available in
// every browser that can run this page from an https or localhost origin,
// and a page served from neither has no clipboard access by any route.
(function() {
  var buttons = document.querySelectorAll('.share-address-copy');
  if (!buttons.length) return;
  Array.prototype.forEach.call(buttons, function(button) {
    button.addEventListener('click', function() {
      var url = button.getAttribute('data-share-url');
      if (!url) return;
      var label = button.textContent;
      function confirmCopy() {
        button.textContent = 'Copied';
        setTimeout(function() { button.textContent = label; }, 1500);
      }
      navigator.clipboard.writeText(url).then(confirmCopy);
    });
  });
})();

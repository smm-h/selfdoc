// Share control: copy either of the page's two addresses.
// The evergreen and pinned URLs are both rendered into the button's
// data-share-url by the build; this file only copies one to the
// clipboard and confirms it.
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
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(confirmCopy);
        return;
      }
      var field = document.createElement('textarea');
      field.value = url;
      document.body.appendChild(field);
      field.select();
      document.execCommand('copy');
      document.body.removeChild(field);
      confirmCopy();
    });
  });
})();

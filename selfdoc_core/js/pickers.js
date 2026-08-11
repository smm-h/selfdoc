// Version and locale picker navigation.
// Every option carries the address the build computed for it
// (data-href), so this file does no path arithmetic: the old version
// assumed the site was served from an origin root and rebuilt the URL
// from location.pathname, which broke under every other mount point.
(function() {
  function wire(selector) {
    var picker = document.querySelector(selector);
    if (!picker) return;
    picker.addEventListener('change', function() {
      var option = this.options[this.selectedIndex];
      var href = option && option.getAttribute('data-href');
      if (href) window.location.href = href;
    });
  }
  wire('.version-picker');
  wire('.locale-picker');
})();

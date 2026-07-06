// Version and locale picker navigation (Phase 1.4)
(function() {
  var versionPicker = document.querySelector('.version-picker');
  var localePicker = document.querySelector('.locale-picker');
  var path = window.location.pathname;

  // URL structure: /{locale}/{version}/page/path
  // Split path into segments, ignoring leading empty string from /
  var segments = path.split('/').filter(Boolean);

  if (versionPicker) {
    versionPicker.addEventListener('change', function() {
      var newVersion = this.value;
      var locale = this.getAttribute('data-current-locale') || segments[0] || '';
      // Replace the version segment (index 1) with the new version
      var rest = segments.slice(2).join('/');
      var newPath = '/' + locale + '/' + newVersion + '/' + rest;
      window.location.href = newPath;
    });
  }

  if (localePicker) {
    localePicker.addEventListener('change', function() {
      var newLocale = this.value;
      var version = this.getAttribute('data-current-version') || segments[1] || '';
      // Replace the locale segment (index 0) with the new locale
      var rest = segments.slice(2).join('/');
      var newPath = '/' + newLocale + '/' + version + '/' + rest;
      window.location.href = newPath;
    });
  }
})();

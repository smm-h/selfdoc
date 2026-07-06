// Mobile sidebar toggle (Feature 25)
(function() {
  var toggle = document.querySelector('.hamburger');
  var sidebar = document.getElementById('sidebar');
  if (!toggle || !sidebar) return;
  function openSidebar() {
    document.body.classList.add('sidebar-open');
    toggle.setAttribute('aria-expanded', 'true');
    var focusable = sidebar.querySelectorAll('a, button, input, [tabindex]');
    if (focusable.length) {
      focusable[0].focus();
      sidebar.addEventListener('keydown', trapFocus);
    }
  }
  function closeSidebar() {
    document.body.classList.remove('sidebar-open');
    toggle.setAttribute('aria-expanded', 'false');
    sidebar.removeEventListener('keydown', trapFocus);
    toggle.focus();
  }
  function trapFocus(e) {
    if (e.key !== 'Tab') return;
    var focusable = sidebar.querySelectorAll('a, button, input, [tabindex]');
    if (!focusable.length) return;
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }
  toggle.addEventListener('click', function() {
    if (document.body.classList.contains('sidebar-open')) {
      closeSidebar();
    } else {
      openSidebar();
    }
  });
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && document.body.classList.contains('sidebar-open')) {
      closeSidebar();
    }
  });
  document.addEventListener('click', function(e) {
    if (document.body.classList.contains('sidebar-open') &&
        !sidebar.contains(e.target) && !toggle.contains(e.target)) {
      closeSidebar();
    }
  });
  sidebar.querySelectorAll('a').forEach(function(link) {
    link.addEventListener('click', function() {
      closeSidebar();
    });
  });
})();

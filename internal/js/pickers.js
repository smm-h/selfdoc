// Version and locale picker interaction.
//
// The markup is the framework's combobox shape, emitted by the build:
// button[role=combobox] + div[role=listbox] of div[role=option]. It is
// painted and readable with scripting off; this file adds the opening, the
// keyboard handling and the navigation.
//
// Every option carries the address the build computed for it (data-href),
// so this file does no path arithmetic: the version that rebuilt the URL
// from location.pathname was only ever right when the site was served from
// an origin root.
(function() {
  var open = null;

  function options(root) {
    return Array.prototype.slice.call(root.querySelectorAll('.sel-opt'));
  }

  function close(root) {
    var btn = root.querySelector('.sel-btn');
    root.classList.remove('open');
    if (btn) btn.setAttribute('aria-expanded', 'false');
    if (open === root) open = null;
  }

  function show(root) {
    if (open && open !== root) close(open);
    var btn = root.querySelector('.sel-btn');
    root.classList.add('open');
    if (btn) btn.setAttribute('aria-expanded', 'true');
    open = root;
    var selected = root.querySelector('.sel-opt[aria-selected="true"]');
    if (selected) selected.classList.add('hover');
  }

  function go(option) {
    var href = option && option.getAttribute('data-href');
    if (href) window.location.href = href;
  }

  function move(root, delta) {
    var opts = options(root);
    if (!opts.length) return;
    var current = -1;
    for (var i = 0; i < opts.length; i++) {
      if (opts[i].classList.contains('hover')) { current = i; break; }
    }
    if (current < 0) {
      for (var j = 0; j < opts.length; j++) {
        if (opts[j].getAttribute('aria-selected') === 'true') { current = j; break; }
      }
    }
    var next = (current + delta + opts.length) % opts.length;
    for (var k = 0; k < opts.length; k++) {
      opts[k].classList.toggle('hover', k === next);
    }
    opts[next].scrollIntoView({ block: 'nearest' });
  }

  function wire(root) {
    var btn = root.querySelector('.sel-btn');
    if (!btn) return;
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      if (root.classList.contains('open')) close(root);
      else show(root);
    });
    btn.addEventListener('keydown', function(e) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!root.classList.contains('open')) show(root);
        move(root, e.key === 'ArrowDown' ? 1 : -1);
      } else if (e.key === 'Enter') {
        if (root.classList.contains('open')) {
          e.preventDefault();
          go(root.querySelector('.sel-opt.hover'));
        }
      } else if (e.key === 'Escape') {
        close(root);
      }
    });
    options(root).forEach(function(option) {
      option.addEventListener('click', function(e) {
        e.stopPropagation();
        go(option);
      });
      option.addEventListener('mousemove', function() {
        options(root).forEach(function(o) {
          o.classList.toggle('hover', o === option);
        });
      });
    });
  }

  var pickers = document.querySelectorAll(
    '.sel.version-picker, .sel.locale-picker'
  );
  for (var p = 0; p < pickers.length; p++) wire(pickers[p]);

  document.addEventListener('click', function() { if (open) close(open); });
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && open) close(open);
  });
})();

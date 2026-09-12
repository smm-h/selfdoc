// Re-enable smooth scroll after initial load (Issue 32)
requestAnimationFrame(function() {
  requestAnimationFrame(function() {
    document.documentElement.style.scrollBehavior = '';
  });
});

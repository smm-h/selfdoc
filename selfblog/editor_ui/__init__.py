"""The editor shell's static assets.

A package rather than a bare directory so the wheel's ``*.py`` include takes
it along, and so ``importlib.resources`` can address it in an installed
environment exactly as it does in a checkout.  The HTML, JS and CSS beside
this file are served verbatim by ``selfblog.editor_server``.
"""

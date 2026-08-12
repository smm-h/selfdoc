"""Directive shims selfblog hands to a home-project build.

selfdoc resolves a directive it does not know by loading a script that
declares ``resolve(attrs, config, body)``.  These are those scripts: one per
site-level directive, each a single call into
:mod:`selfblog.sitedirectives`, which holds the actual rendering.  They live
in the package rather than in the home project's repository so the home
project declares *what* it wants rendered and never *how*.
"""

from __future__ import annotations

import os

#: Absolute path of the directory holding the shim scripts.
SHIM_DIR = os.path.dirname(os.path.abspath(__file__))

#: Directive name -> the script that resolves it, as
#: ``selfdoc.json``'s ``directives`` map spells it.
SHIM_SCRIPTS = {
    "projects-cards": os.path.join(SHIM_DIR, "projects_cards.py"),
    "blog-highlights": os.path.join(SHIM_DIR, "blog_highlights.py"),
}

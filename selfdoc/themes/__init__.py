"""Theme registry for selfdoc.

Themes are CSS files stored alongside this module. Use get_theme(name) to load
a theme's CSS content by name.
"""

import os

_THEMES_DIR = os.path.dirname(__file__)


def get_theme(name):
    """Load and return the CSS content for the named theme.

    Args:
        name: Theme name (corresponds to a .css file in the themes directory).

    Returns:
        The CSS content as a string.

    Raises:
        ValueError: If the theme does not exist.
    """
    css_path = os.path.join(_THEMES_DIR, f"{name}.css")
    if not os.path.isfile(css_path):
        available = [
            f[:-4] for f in os.listdir(_THEMES_DIR) if f.endswith(".css")
        ]
        raise ValueError(
            f"unknown theme {name!r}; "
            f"available themes: {', '.join(sorted(available)) or 'none'}"
        )
    with open(css_path, "r", encoding="utf-8") as f:
        return f.read()

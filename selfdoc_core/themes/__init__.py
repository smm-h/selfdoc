"""Theme registry for selfdoc.

Themes are CSS files stored alongside this module. Use get_theme(name) to load
a theme's CSS content by name. Use get_theme_meta(name) to load a theme's
metadata (fonts, accent color, Pygments styles) from its companion JSON file.
"""

import json
import os

_THEMES_DIR = os.path.dirname(__file__)

# Default metadata returned when a theme has no companion .json file.
# These match the values historically hardcoded across build.py and html.py.
_DEFAULT_THEME_META = {
    "fonts_url": "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap",
    "fonts_preconnect": ["https://fonts.googleapis.com", "https://fonts.gstatic.com"],
    "accent_color": "#0969da",
    "pygments_light": "default",
    "pygments_dark": "monokai",
}


def list_themes():
    """Return every theme name this build ships, sorted.

    A theme *is* its CSS file, so the directory listing is the registry --
    there is no second list to keep in step with it.  Every place that
    validates or enumerates a theme reads this.
    """
    return sorted(
        f[:-4] for f in os.listdir(_THEMES_DIR) if f.endswith(".css")
    )


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
        available = list_themes()
        raise ValueError(
            f"unknown theme {name!r}; "
            f"available themes: {', '.join(available) or 'none'}"
        )
    with open(css_path, "r", encoding="utf-8") as f:
        return f.read()


def get_theme_meta(name):
    """Load and return the metadata dict for the named theme.

    Looks for a ``{name}.json`` file alongside the ``{name}.css`` theme file.
    If found, loads and returns its contents merged over the defaults.
    If not found, returns the default metadata dict (backward compatible).

    Returns:
        A dict with keys: fonts_url, fonts_preconnect, accent_color,
        pygments_light, pygments_dark.
    """
    json_path = os.path.join(_THEMES_DIR, f"{name}.json")
    if os.path.isfile(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        # Merge over defaults so missing keys get filled in
        result = dict(_DEFAULT_THEME_META)
        result.update(meta)
        return result
    return dict(_DEFAULT_THEME_META)

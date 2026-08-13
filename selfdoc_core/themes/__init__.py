"""Theme registry for selfdoc.

Themes are CSS files stored alongside this module. Use get_theme(name) to load
a theme's CSS content by name. Use get_theme_meta(name) to load a theme's
metadata (fonts, accent color, Pygments styles) from its companion JSON file.

Framework themes
----------------

A theme's companion JSON may declare a ``framework`` block, and then the
theme is not a whole stylesheet: it is an *overlay* on top of a framework
whose sheets ship in an installed package.  ``tinymoon`` is the one such
theme -- selfdoc consumes the framework rather than imitating it, so the
palette, the reset and the faces are the framework's, and the file in this
directory carries only what is selfdoc's.  The overlay still restates a
good deal of component styling, because the emitters still produce
selfdoc's own class surface rather than the framework's markup shapes;
that restatement goes when the emitters migrate.

Three consequences the rest of the build reads through this module:

- :func:`get_theme` returns the *composed* stylesheet -- the framework's
  sheets, in the order its markup contract requires, then the overlay.  The
  framework bytes are shipped as-is; nothing here rewrites them.
- :func:`theme_assets` names the non-CSS files that have to travel with the
  stylesheet, and :func:`theme_css_rel` says where the stylesheet is written
  relative to a site root.  The framework's ``@font-face`` rules address
  ``../fonts/``, so the stylesheet goes in ``css/`` with ``fonts/`` beside
  it -- the layout inside the installed package, preserved.
- :func:`theme_modules` is the ES modules a page under the theme imports:
  the *closure* of the entry points the framework block declares, computed
  from the package's own sources.  They travel in ``js/`` beside the
  stylesheet's directory.  A declared list would be a second copy of a fact
  the sources already state, and the failure when it fell behind would be a
  page importing a module the site does not carry.
"""

import json
import os
import re

_THEMES_DIR = os.path.dirname(__file__)

#: Where a plain theme's stylesheet is written, relative to a site root.
DEFAULT_CSS_REL = "style.css"

#: Where a framework theme's stylesheet is written.  The directory is not
#: decoration: the framework's font URLs are ``../fonts/``, so the sheet has
#: to sit one level in with ``fonts/`` as its sibling.
FRAMEWORK_CSS_REL = "css/style.css"

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


def theme_framework(name):
    """The ``framework`` block a theme declares, or ``None``.

    The block names an installed package and the sheets to take from it::

        {"framework": {"package": "tinymoon",
                       "sheets": ["tokens", "base", ...],
                       "assets": ["fonts"]}}

    A theme with no such block is a whole stylesheet of its own and every
    framework-aware branch below is skipped for it.
    """
    meta = get_theme_meta(name)
    block = meta.get("framework")
    if not block:
        return None
    if not block.get("package") or not block.get("sheets"):
        raise ValueError(
            f"theme {name!r} declares a framework block with no "
            f"'package' or no 'sheets'"
        )
    return block


def _framework_assets_dir(package):
    """The directory the named framework package ships its assets in.

    The package is a hard dependency of this engine, so a missing one is a
    broken install rather than a condition to route around.
    """
    if package == "tinymoon":
        import tinymoon

        return str(tinymoon.assets_path())
    raise ValueError(
        f"unknown theme framework package {package!r}; selfdoc knows how "
        f"to locate the assets of: tinymoon"
    )


def framework_sheets_css(name):
    """The framework sheets a theme composes over, concatenated in order.

    Empty string for a theme that declares no framework.  The bytes are the
    package's own: they are read and joined, never rewritten, so the hash of
    the result pins the framework version that produced it.
    """
    block = theme_framework(name)
    if not block:
        return ""
    assets = _framework_assets_dir(block["package"])
    parts = []
    for sheet in block["sheets"]:
        path = os.path.join(assets, "css", f"{sheet}.css")
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"theme {name!r} names the framework sheet {sheet!r}, which "
                f"{block['package']} does not ship at {path}"
            )
        with open(path, "r", encoding="utf-8") as f:
            parts.append(f"/* --- {block['package']}/{sheet}.css --- */\n"
                         + f.read())
    return "\n\n".join(parts)


#: Where a framework theme's ES modules are written, from the payload root.
MODULES_DIR = "js"

# Every static-import form the framework's modules use.  A specifier is
# always relative and always names a file: the framework has no bare
# specifiers, no import maps and no extensionless imports, so this covers
# the whole surface -- and a form it does not cover fails loudly below
# rather than shipping a module whose dependency is missing.
_JS_IMPORT_RE = re.compile(
    r"""(?:from|import)\s*\(?\s*["'](\./[\w.\-/]+\.js)["']"""
)


def theme_modules(name):
    """Every framework module a page under this theme loads, sorted.

    The theme's ``framework`` block names *entry points* -- the modules the
    page's own script imports by name.  Their transitive imports are
    computed here from the package's own sources rather than declared,
    because a declared list is a second copy of a fact the sources already
    state, and the failure when it falls behind is a page that imports a
    module the site does not carry.

    The framework ships far more than a documentation page uses (its whole
    ``js/`` tree is an order of magnitude larger than this closure), so the
    closure is also what keeps the payload to what is really loaded.

    Empty for a theme that declares no framework, or one whose framework
    block names no modules.
    """
    block = theme_framework(name)
    if not block:
        return []
    entries = block.get("modules") or []
    if not entries:
        return []
    js_dir = os.path.join(_framework_assets_dir(block["package"]), MODULES_DIR)
    seen = set()
    queue = list(entries)
    while queue:
        module = queue.pop()
        if module in seen:
            continue
        path = os.path.join(js_dir, module)
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"theme {name!r} reaches the framework module {module!r}, "
                f"which {block['package']} does not ship at {path}"
            )
        seen.add(module)
        with open(path, "r", encoding="utf-8") as handle:
            source = handle.read()
        for specifier in _JS_IMPORT_RE.findall(source):
            queue.append(specifier[2:])
    return sorted(seen)


def theme_assets(name):
    """``(absolute source, site-relative destination)`` for a theme's assets.

    The files that have to travel with the stylesheet and are not the
    stylesheet: one directory per kind the ``framework`` block names -- the
    ``@font-face`` rules are the only thing in the sheets that addresses
    anything outside them -- plus the ES modules a page imports, which are
    the closure of the block's declared entry points rather than the
    framework's whole module tree.  Empty for a theme that declares no
    framework.  Destinations keep the layout the package uses, because the
    sheets and the modules address each other by relative URL.
    """
    block = theme_framework(name)
    if not block:
        return []
    assets = _framework_assets_dir(block["package"])
    pairs = []
    for module in theme_modules(name):
        pairs.append((
            os.path.join(assets, MODULES_DIR, module),
            f"{MODULES_DIR}/{module}",
        ))
    for kind in block.get("assets", []):
        src_dir = os.path.join(assets, kind)
        if not os.path.isdir(src_dir):
            raise FileNotFoundError(
                f"theme {name!r} names the framework asset directory "
                f"{kind!r}, which {block['package']} does not ship at "
                f"{src_dir}"
            )
        for entry in sorted(os.listdir(src_dir)):
            src = os.path.join(src_dir, entry)
            if os.path.isfile(src):
                pairs.append((src, f"{kind}/{entry}"))
    return pairs


def theme_css_rel(name):
    """Where the named theme's stylesheet is written, from a site root."""
    return FRAMEWORK_CSS_REL if theme_framework(name) else DEFAULT_CSS_REL


def theme_overlay(name):
    """The theme's own CSS file, without any framework sheets under it."""
    css_path = os.path.join(_THEMES_DIR, f"{name}.css")
    if not os.path.isfile(css_path):
        available = list_themes()
        raise ValueError(
            f"unknown theme {name!r}; "
            f"available themes: {', '.join(available) or 'none'}"
        )
    with open(css_path, "r", encoding="utf-8") as f:
        return f.read()


def get_theme(name):
    """Load and return the CSS content for the named theme.

    For a framework theme this is the composition: the framework's sheets
    followed by selfdoc's overlay.  The whole composition sits *below* the
    critical-CSS marker, because the framework's ``@font-face`` rules are
    written relative to the stylesheet's own location and inlining them into
    a page at arbitrary depth would aim them at nothing.

    Args:
        name: Theme name (corresponds to a .css file in the themes directory).

    Returns:
        The CSS content as a string.

    Raises:
        ValueError: If the theme does not exist.
    """
    overlay = theme_overlay(name)
    framework = framework_sheets_css(name)
    if not framework:
        return overlay
    return "/* --- NON-CRITICAL --- */\n" + framework + "\n\n" + overlay


def get_theme_meta(name):
    """Load and return the metadata dict for the named theme.

    Looks for a ``{name}.json`` file alongside the ``{name}.css`` theme file.
    If found, loads and returns its contents merged over the defaults.
    If not found, returns the default metadata dict (backward compatible).

    Returns:
        A dict with keys: fonts_url, fonts_preconnect, accent_color,
        pygments_light, pygments_dark, name, css_rel.  ``name`` and
        ``css_rel`` are computed rather than declared: every page renderer
        already carries the metadata, so carrying the theme's identity and
        the address of its stylesheet in the same dict saves threading two
        more parameters through every wrapper.
    """
    json_path = os.path.join(_THEMES_DIR, f"{name}.json")
    result = dict(_DEFAULT_THEME_META)
    if os.path.isfile(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        # Merge over defaults so missing keys get filled in
        result.update(meta)
    result["name"] = name
    result["css_rel"] = (
        FRAMEWORK_CSS_REL if result.get("framework") else DEFAULT_CSS_REL
    )
    return result

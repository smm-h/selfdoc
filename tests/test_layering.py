"""Layering tests for the selfdoc_core / selfdoc / selfblog split.

selfdoc_core is the shared engine and must import neither sibling
package.  In particular, the build pipeline must not import the posts
module (which belongs to selfblog) -- posts flow through the post
provider registered via selfdoc_core.register_post_provider().
"""

import ast
import os

import pytest

import selfdoc_core

_CORE_DIR = os.path.dirname(selfdoc_core.__file__)


def _imported_modules(py_path):
    """Return every module name imported anywhere in *py_path*."""
    with open(py_path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=py_path)

    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _core_py_files():
    """Yield every .py file under the selfdoc_core package."""
    for root, dirs, files in os.walk(_CORE_DIR):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fname in files:
            if fname.endswith(".py"):
                yield os.path.join(root, fname)


# -- Import layering -------------------------------------------------------


def test_build_has_zero_posts_imports():
    """selfdoc_core.build must not import the posts module at all.

    Post discovery goes through the registered post provider instead.
    """
    build_path = os.path.join(_CORE_DIR, "build.py")
    for mod in _imported_modules(build_path):
        assert "posts" not in mod.split("."), (
            f"selfdoc_core/build.py imports {mod!r}; it must use the "
            f"registered post provider instead of importing posts"
        )


def test_core_imports_neither_sibling():
    """No module in selfdoc_core may import selfdoc or selfblog."""
    for py_path in _core_py_files():
        for mod in _imported_modules(py_path):
            top = mod.split(".")[0]
            assert top not in ("selfdoc", "selfblog"), (
                f"{os.path.relpath(py_path, _CORE_DIR)} imports {mod!r}; "
                f"selfdoc_core must not import sibling packages"
            )


def test_posts_module_lives_only_in_selfblog():
    """The posts module moved to selfblog; the old locations must not
    exist (a core->blog shim would invert the dependency)."""
    import importlib.util

    assert importlib.util.find_spec("selfblog.posts") is not None
    assert importlib.util.find_spec("selfdoc_core.posts") is None
    assert importlib.util.find_spec("selfdoc.posts") is None


# -- JS assets live in exactly one package ---------------------------------


def test_no_js_assets_outside_core():
    """selfdoc ships no .js of its own; the loader reads selfdoc_core's.

    A copy under ``selfdoc/js/`` was packaged and never loaded, and it had
    drifted: its ``pickers.js`` was still the retired path-arithmetic
    version picker that rebuilt ``/{locale}/{version}/`` URLs, while the
    loaded one computes links from each page's own address.
    """
    import selfdoc

    pkg_dir = os.path.dirname(selfdoc.__file__)
    strays = []
    for root, dirs, files in os.walk(pkg_dir):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "dist", "node_modules")]
        strays.extend(
            os.path.relpath(os.path.join(root, name), pkg_dir)
            for name in files if name.endswith(".js")
        )
    # bin/cli.js is the npm wrapper, not a docs-site asset.
    strays = [rel for rel in strays if not rel.startswith("bin" + os.sep)]
    assert strays == [], (
        f"selfdoc carries JS assets {strays}; they belong to selfdoc_core, "
        f"whose loader is the only thing that reads them"
    )


def test_selfdoc_package_does_not_package_js():
    """The selfdoc wheel and sdist declare no JS include pattern."""
    import selfdoc

    manifest = os.path.join(os.path.dirname(selfdoc.__file__), "pyproject.toml")
    with open(manifest, encoding="utf-8") as f:
        text = f.read()
    assert "js/*.js" not in text, (
        "selfdoc/pyproject.toml still packages js/*.js; the assets live in "
        "selfdoc_core"
    )


# -- Theme assets live in exactly one package ------------------------------


def test_no_theme_assets_outside_core():
    """selfdoc ships no theme CSS or JSON of its own; core's are the ones read.

    ``selfdoc/themes/__init__.py`` is a re-export shim that points
    ``__file__`` at ``selfdoc_core/themes``, so every reader resolves there.
    The copies that sat beside the shim were packaged and drifted 58 lines
    behind core's -- and the contrast lint read the drifted copy.
    """
    import selfdoc

    themes_dir = os.path.join(os.path.dirname(selfdoc.__file__), "themes")
    strays = sorted(
        name for name in os.listdir(themes_dir)
        if name.endswith((".css", ".json"))
    ) if os.path.isdir(themes_dir) else []
    assert strays == [], (
        f"selfdoc/themes carries theme assets {strays}; they belong to "
        f"selfdoc_core, which every reader resolves to through the shim"
    )


def test_selfdoc_package_does_not_package_themes():
    """The selfdoc wheel and sdist declare no theme asset include pattern."""
    import selfdoc

    manifest = os.path.join(os.path.dirname(selfdoc.__file__), "pyproject.toml")
    with open(manifest, encoding="utf-8") as f:
        text = f.read()
    assert "themes/*.css" not in text and "themes/*.json" not in text, (
        "selfdoc/pyproject.toml still packages theme assets; they live in "
        "selfdoc_core"
    )


def test_contrast_lint_reads_the_core_theme_css():
    """The contrast lint resolves its CSS through the theme registry.

    It used to build the path from ``selfdoc/check.py``'s own directory,
    which reached the packaged mirror rather than the stylesheet the build
    emits.
    """
    import selfdoc_core.themes as core_themes
    from selfdoc.check import theme_css_path

    core_dir = os.path.dirname(core_themes.__file__)
    assert theme_css_path("minimal") == os.path.join(core_dir, "minimal.css")


# -- Post provider registration --------------------------------------------


def test_register_same_provider_is_noop(monkeypatch):
    """Re-registering the identical callable must not raise."""
    provider = lambda posts_dir, manifest_path=None: []  # noqa: E731
    monkeypatch.setattr(selfdoc_core, "_post_provider", None)
    selfdoc_core.register_post_provider(provider)
    selfdoc_core.register_post_provider(provider)
    assert selfdoc_core.get_post_provider() is provider


def test_register_different_provider_raises(monkeypatch):
    """Registering a second, different provider is an error."""
    monkeypatch.setattr(selfdoc_core, "_post_provider", None)
    selfdoc_core.register_post_provider(lambda d, manifest_path=None: [])
    with pytest.raises(ValueError, match="already registered"):
        selfdoc_core.register_post_provider(
            lambda d, manifest_path=None: [],
        )


def test_require_without_provider_names_selfblog(monkeypatch):
    """The no-provider hard error must direct the user to selfblog."""
    monkeypatch.setattr(selfdoc_core, "_post_provider", None)
    with pytest.raises(RuntimeError, match="selfblog"):
        selfdoc_core.require_post_provider()


def test_selfblog_import_registers_discover_posts():
    """Importing selfblog registers its discover_posts as the provider."""
    import selfblog

    assert selfdoc_core.get_post_provider() is selfblog.discover_posts


# -- Post-check hook registration --------------------------------------------


def test_register_different_check_hook_raises(monkeypatch):
    """Registering a second, different post-check hook is an error."""
    monkeypatch.setattr(selfdoc_core, "_post_check_hook", None)
    selfdoc_core.register_post_check_hook(lambda config, dir_path: [])
    with pytest.raises(ValueError, match="already registered"):
        selfdoc_core.register_post_check_hook(
            lambda config, dir_path: [],
        )


def test_require_check_hook_without_hook_names_selfblog(monkeypatch):
    """The no-hook hard error must direct the user to selfblog."""
    monkeypatch.setattr(selfdoc_core, "_post_check_hook", None)
    with pytest.raises(RuntimeError, match="selfblog"):
        selfdoc_core.require_post_check_hook()


def test_selfblog_import_registers_check_posts():
    """Importing selfblog registers check_posts as the post-check hook."""
    import selfblog.check

    assert (
        selfdoc_core.get_post_check_hook()
        is selfblog.check.check_posts
    )


# -- Build pipeline uses the provider ---------------------------------------


def _project_with_post(tmp_path):
    """Create a minimal posts-configured project with one post."""
    import json

    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "author": {"name": "Test Author", "url": "https://author.example"},
        "search_engine": "pagefind",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0"}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "docs": "docs/",
        "output": "docs/_build/",
    }
    with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
        json.dump(config, f)

    os.makedirs(os.path.join(tmp_path, "src"), exist_ok=True)
    with open(os.path.join(tmp_path, "src", "__init__.py"), "w") as f:
        f.write('"""Example package."""\n')

    os.makedirs(os.path.join(tmp_path, "docs"), exist_ok=True)
    with open(os.path.join(tmp_path, "docs", "index.md"), "w") as f:
        f.write("# Test Project\n\nWelcome.\n")

    posts_dir = os.path.join(tmp_path, ".selfdoc", "posts")
    os.makedirs(posts_dir, exist_ok=True)
    with open(os.path.join(posts_dir, "hello.md"), "w") as f:
        f.write(
            "---\ntitle: Hello\ndate: 2024-01-15\nslug: hello\n"
            "directives: false\n"
            "tags: []\ndraft: false\n---\nBody.\n"
        )
    return tmp_path


def test_build_with_posts_but_no_provider_hard_errors(tmp_path, monkeypatch):
    """A posts-carrying build without a registered provider must fail
    with a hard error naming selfblog."""
    from selfdoc_core.build import build

    project = _project_with_post(tmp_path)
    monkeypatch.setattr(selfdoc_core, "_post_provider", None)
    with pytest.raises(RuntimeError, match="selfblog"):
        build(str(project))


def test_posts_only_build_without_provider_hard_errors(tmp_path, monkeypatch):
    """target='posts' without a registered provider must hard-error."""
    from selfdoc_core.build import build

    project = _project_with_post(tmp_path)
    monkeypatch.setattr(selfdoc_core, "_post_provider", None)
    with pytest.raises(RuntimeError, match="selfblog"):
        build(str(project), target="posts")


def test_build_with_posts_and_provider_succeeds(tmp_path):
    """With selfblog's provider registered (via conftest), a
    posts-carrying build produces the post page."""
    from selfdoc_core.build import build

    project = _project_with_post(tmp_path)
    written = build(str(project), target="posts")
    assert any("hello" in path for path in written)

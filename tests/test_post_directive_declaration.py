"""A post declares, in its frontmatter, whether it may contain directives.

``directives`` is a required boolean on every post.  There is no default:
a post that does not declare is refused at discovery, because "does this
markdown carry executable markers?" is a question the author answers, not
one the reader guesses.  A post declaring ``false`` that carries a marker
is refused too, naming the marker and the line it sits on.  A post
declaring ``true`` resolves its directives like any other page.

Documentation pages carry no such key: the whole docs tree is directive
territory by construction.
"""

from __future__ import annotations

import os

import pytest

from selfblog.check import check_posts
from selfblog.posts import discover_posts, parse_post


def _post_source(frontmatter_lines, body=""):
    return "---\n" + "\n".join(frontmatter_lines) + "\n---\n" + body


def _write_post(posts_dir, filename, frontmatter_lines, body=""):
    path = os.path.join(posts_dir, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_post_source(frontmatter_lines, body))
    return path


_BASE_FM = ["title: Hello World", "date: 2025-01-15"]


# -- The declaration is required ----------------------------------------------


def test_missing_declaration_is_a_hard_error():
    """No default: a post that does not declare is refused at parse."""
    with pytest.raises(RuntimeError) as excinfo:
        parse_post(_post_source(_BASE_FM, "Body text.\n"), "p.md")
    message = str(excinfo.value)
    assert "directives" in message
    assert "p.md" in message


def test_non_boolean_declaration_is_a_hard_error():
    """The key is a boolean; 'maybe' declares nothing."""
    with pytest.raises(RuntimeError) as excinfo:
        parse_post(
            _post_source([*_BASE_FM, "directives: maybe"], "Body.\n"), "p.md",
        )
    assert "directives" in str(excinfo.value)


def test_discovery_refuses_a_post_with_no_declaration(tmp_path):
    """Discovery carries the same refusal as the parser."""
    posts_dir = tmp_path / "posts"
    _write_post(str(posts_dir), "p.md", _BASE_FM, "Body.\n")
    with pytest.raises(RuntimeError) as excinfo:
        discover_posts(str(posts_dir))
    assert "directives" in str(excinfo.value)


def test_declaring_false_without_markers_parses(tmp_path):
    """The ordinary case: prose, declared free of directives."""
    post = parse_post(
        _post_source([*_BASE_FM, "directives: false"], "Just prose.\n"),
        "p.md",
    )
    assert post["directives"] is False


def test_declaring_true_parses(tmp_path):
    """A post that opts in carries the declaration on its dict."""
    post = parse_post(
        _post_source(
            [*_BASE_FM, "directives: true"],
            'Intro.\n\n:-: ref path="mylib" target="alpha"\n',
        ),
        "p.md",
    )
    assert post["directives"] is True


# -- Declared false, marker present -------------------------------------------


def test_declared_false_with_a_marker_names_marker_and_line():
    """The refusal is specific: which marker, and where in the post file."""
    body = "Intro paragraph.\n\n:-: ref path=\"mylib\" target=\"alpha\"\n"
    with pytest.raises(RuntimeError) as excinfo:
        parse_post(
            _post_source([*_BASE_FM, "directives: false"], body), "p.md",
        )
    message = str(excinfo.value)
    assert ":-:" in message
    # Frontmatter is 5 lines (---, title, date, directives, ---), so the
    # marker sits on line 8 of the post file, not line 3 of its body.
    assert "line 8" in message


def test_declared_false_with_a_block_marker_is_refused():
    """Every marker type counts, not just the self-closing one."""
    body = ':<: table-commands\n:@: path="cli.py"\n:>:\n'
    with pytest.raises(RuntimeError) as excinfo:
        parse_post(
            _post_source([*_BASE_FM, "directives: false"], body), "p.md",
        )
    assert ":<:" in str(excinfo.value)


def test_a_marker_inside_a_fence_is_not_a_directive():
    """A fenced example of the syntax is documentation, not a directive."""
    body = "Here is the syntax:\n\n```\n:-: ref path=\"x\"\n```\n"
    post = parse_post(
        _post_source([*_BASE_FM, "directives: false"], body), "p.md",
    )
    assert post["directives"] is False


def test_a_marker_in_a_code_span_is_not_a_directive():
    """`:-: ref` written inline is prose about the syntax."""
    body = "Write `:-: ref path=\"x\"` to embed a symbol.\n"
    post = parse_post(
        _post_source([*_BASE_FM, "directives: false"], body), "p.md",
    )
    assert post["directives"] is False


# -- The check surface reports both as post lints ------------------------------


def test_check_posts_reports_a_missing_declaration_as_post006(tmp_path):
    posts_dir = tmp_path / "blog"
    _write_post(str(posts_dir), "p.md", _BASE_FM, "Body.\n")
    result = check_posts({"posts": {"dir": "blog"}}, str(tmp_path))
    assert len(result) == 1
    assert result[0].code == "POST006"
    assert result[0].severity == "error"


def test_check_posts_reports_a_declared_false_marker_as_post007(tmp_path):
    posts_dir = tmp_path / "blog"
    _write_post(
        str(posts_dir),
        "p.md",
        [*_BASE_FM, "directives: false"],
        ':-: ref path="mylib" target="alpha"\n',
    )
    result = check_posts({"posts": {"dir": "blog"}}, str(tmp_path))
    assert len(result) == 1
    assert result[0].code == "POST007"
    assert result[0].severity == "error"
    assert ":-:" in result[0].message


def test_check_posts_passes_a_declared_true_post(tmp_path):
    posts_dir = tmp_path / "blog"
    _write_post(
        str(posts_dir),
        "p.md",
        [*_BASE_FM, "directives: true"],
        "Body with no markers at all.\n",
    )
    assert check_posts({"posts": {"dir": "blog"}}, str(tmp_path)) == []


# -- A declared-true post builds ----------------------------------------------


def test_a_declared_true_post_builds_with_its_directive_resolved(tmp_path):
    """Declaring true is not a bypass -- the directive still resolves."""
    import json

    from conftest import default_config

    from selfdoc.build import build

    config = default_config(docs="docs/", output="docs/_build/")
    with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
        json.dump(config, f)

    src_dir = os.path.join(tmp_path, "src")
    os.makedirs(src_dir, exist_ok=True)
    with open(os.path.join(src_dir, "__init__.py"), "w") as f:
        f.write('"""Example package."""\n\n\ndef alpha():\n    """Alpha does a thing."""\n')

    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    with open(os.path.join(docs_dir, "index.md"), "w") as f:
        f.write("# Test Project\n\nWelcome.\n")

    _write_post(
        os.path.join(tmp_path, ".selfdoc", "posts"),
        "hello.md",
        ["title: Hello World", "date: 2024-01-15", "slug: hello-world",
         "draft: false", "directives: true"],
        'Intro.\n\n:-: ref path="src" target="alpha"\n',
    )

    build(str(tmp_path))

    out = os.path.join(tmp_path, "docs", "_build", "blog", "hello-world", "index.html")
    assert os.path.isfile(out)
    with open(out, encoding="utf-8") as f:
        html = f.read()
    assert "Alpha does a thing." in html
    assert ":-:" not in html


# -- The scaffold emits the key ------------------------------------------------


def test_post_new_scaffold_emits_the_declaration(tmp_path, monkeypatch):
    """'selfblog post new' writes a post that discovery accepts."""
    import json
    import subprocess
    import sys

    (tmp_path / "selfdoc.json").write_text(json.dumps({
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "versions": [{"version": "0.1.0"}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "posts": {"dir": "posts/"},
    }))
    proc = subprocess.run(
        [sys.executable, "-m", "selfblog", "post", "new",
         "--title", "Hello World"],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr

    written = list((tmp_path / "posts").glob("*.md"))
    assert len(written) == 1
    assert "directives: false" in written[0].read_text()

    # The scaffolded post is discoverable as written -- no manual edit needed.
    posts = discover_posts(str(tmp_path / "posts"))
    assert len(posts) == 1
    assert posts[0]["directives"] is False


def test_release_post_scaffold_emits_the_declaration(tmp_path):
    """'selfblog post generate --from-release' does too."""
    import json
    import subprocess
    import sys

    (tmp_path / "selfdoc.json").write_text(json.dumps({
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "versions": [{"version": "0.1.0"}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "posts": {"dir": "posts/"},
    }))
    proc = subprocess.run(
        [sys.executable, "-m", "selfblog", "post", "generate",
         "--from-release", "--version", "0.1.0", "--prev-version", "0.0.9",
         "--bump-type", "minor", "--description", "A release.",
         "--context", "", "--changelog-file", "", "--body-file", "",
         "--project-name", "Example", "--release-url", ""],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr

    written = list((tmp_path / "posts").glob("*.md"))
    assert len(written) == 1
    assert "directives: false" in written[0].read_text()
    assert len(discover_posts(str(tmp_path / "posts"))) == 1

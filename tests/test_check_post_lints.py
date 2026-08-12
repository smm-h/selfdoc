"""Posts are linted by the check, at their own path and their own lines.

A post is a page on the site, so every rule that holds a documentation
page to a standard holds a post to it too.  Neither path used to reach
them: ``check`` never injected posts into the docs tree, and the build's
lint pass ran after the injected files were removed, so a post could carry
any defect at all and both surfaces reported nothing.

The check now resolves posts through the same conversion the build uses
(``post_docs_payloads`` -- the one place a post becomes a docs page) and
merges the result into the slice the lint rules see.  The reported path is
the post's own file, and the reported line is that file's line: frontmatter
line counts come from the source, not from the rebuilt frontmatter the
conversion emits.
"""

from __future__ import annotations

import json
import os

import pytest

from selfdoc.check import check_docs

from conftest import default_config


def _project(tmp_path, posts, config_overrides=None):
    """A minimal project with *posts* in the default posts directory."""
    config = default_config(docs="docs/", output="docs/_build/")
    if config_overrides:
        config.update(config_overrides)
    with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
        json.dump(config, f)

    src_dir = os.path.join(tmp_path, "src")
    os.makedirs(src_dir, exist_ok=True)
    with open(os.path.join(src_dir, "__init__.py"), "w") as f:
        f.write('"""Example package."""\n')

    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    with open(os.path.join(docs_dir, "index.md"), "w") as f:
        f.write(
            "---\ntitle: Home\ndescription: A home page whose description is "
            "long enough to keep the description rules quiet in this fixture.\n"
            "---\n# Test Project\n\nWelcome.\n"
        )

    posts_dir = os.path.join(tmp_path, ".selfdoc", "posts")
    os.makedirs(posts_dir, exist_ok=True)
    for filename, content in posts:
        with open(os.path.join(posts_dir, filename), "w") as f:
            f.write(content)

    return str(tmp_path)


_FM = (
    "---\n"
    "title: Hello World\n"
    "date: 2024-01-15\n"
    "slug: hello-world\n"
    "draft: false\n"
    "directives: false\n"
    "description: A post description written at a comfortable length, so "
    "that the description-length rules stay out of the assertions these "
    "tests actually make.\n"
    "---\n"
)


def _lints_of(result, code):
    return [lint for lint in result.lints if lint.code == code]


def test_a_defect_in_a_post_is_reported_at_the_posts_own_path(tmp_path):
    """The empty alt text is in the post file, so the post file is named."""
    post = _FM + "Intro paragraph.\n\n![](/img/x.png)\n"
    project = _project(tmp_path, [("hello.md", post)])

    result = check_docs(project)

    seo003 = _lints_of(result, "SEO003")
    assert len(seo003) == 1
    assert seo003[0].file == os.path.join(".selfdoc", "posts", "hello.md")


def test_the_reported_line_is_the_post_files_own_line(tmp_path):
    """Frontmatter is counted from the source, not from a reconstruction.

    The rebuilt frontmatter the docs conversion emits has a different line
    count from the file on disk (keys are injected, dropped and reordered),
    so a line number computed from it would point at the wrong line of the
    file a reader opens.
    """
    post = _FM + "Intro paragraph.\n\n![](/img/x.png)\n"
    project = _project(tmp_path, [("hello.md", post)])

    result = check_docs(project)

    seo003 = _lints_of(result, "SEO003")
    assert len(seo003) == 1
    # The source's frontmatter is 8 lines, then "Intro paragraph.", then a
    # blank line: the image sits on line 11 of hello.md.
    lines = post.split("\n")
    expected = next(
        i + 1 for i, line in enumerate(lines) if line.startswith("![](")
    )
    assert expected == 11
    assert seo003[0].line == expected


def test_a_clean_post_produces_no_post_lints(tmp_path):
    """The slice adds no diagnostics of its own to a well-formed post."""
    post = _FM + (
        "# Hello World\n\nA paragraph of ordinary prose with nothing wrong "
        "with it at all, long enough that the paragraph-length rule is "
        "satisfied: it runs past thirty words without running past eighty, "
        "which is the band every page on the site is held to regardless of "
        "who or what wrote it.\n"
    )
    project = _project(tmp_path, [("hello.md", post)])

    result = check_docs(project)

    post_path = os.path.join(".selfdoc", "posts", "hello.md")
    assert [lint for lint in result.lints if lint.file == post_path] == []


def test_a_post_missing_a_description_is_an_error(tmp_path):
    """Posts are held to the page rules, SEO006 included."""
    post = (
        "---\ntitle: Hello World\ndate: 2024-01-15\nslug: hello-world\n"
        "draft: false\ndirectives: false\n---\n"
        "# Hello World\n\nBody.\n"
    )
    project = _project(tmp_path, [("hello.md", post)])

    result = check_docs(project)

    seo006 = _lints_of(result, "SEO006")
    assert any(
        lint.file == os.path.join(".selfdoc", "posts", "hello.md")
        for lint in seo006
    )


def test_a_draft_is_not_linted(tmp_path):
    """The build does not emit a draft, so the check does not judge one."""
    draft = _FM.replace("draft: false", "draft: true").replace(
        "slug: hello-world", "slug: draft-post",
    ) + "Intro paragraph.\n\n![](/img/x.png)\n"
    project = _project(tmp_path, [("draft.md", draft)])

    result = check_docs(project)

    assert _lints_of(result, "SEO003") == []


def test_the_generated_listing_page_is_not_linted(tmp_path):
    """The listing has no source file, so it has nothing a reader can fix."""
    post = _FM + "# Hello World\n\nBody prose.\n"
    project = _project(tmp_path, [("hello.md", post)])

    result = check_docs(project)

    assert [lint for lint in result.lints if "blog" == lint.file] == []
    assert [lint for lint in result.lints if lint.file == "blog.md"] == []


def test_a_project_with_no_posts_is_unaffected(tmp_path):
    """No posts directory, no slice, no change to the reported lints."""
    project = _project(tmp_path, [])
    result = check_docs(project)
    assert all(".selfdoc" not in lint.file for lint in result.lints)


def test_selfblog_unified_check_reports_the_posts_defect(tmp_path):
    """The selfblog surface reaches posts through the same slice.

    ``selfblog check`` on a unified project runs the docs check over every
    constituent project, so the post lints arrive with the project's slug
    prefixed onto the post's own path.
    """
    from selfblog.check import check_unified

    packages = tmp_path / "monorepo" / "packages"
    core = packages / "core"
    core.mkdir(parents=True)
    _project(core, [("hello.md", _FM + "Intro.\n\n![](/img/x.png)\n")])

    docs_site = packages / "docs-site"
    docs_site.mkdir(parents=True)
    site_config = default_config(docs="docs/", output="docs/_build/")
    site_config["unified"] = {"projects": [{"path": "../core"}]}
    (docs_site / "selfdoc.json").write_text(json.dumps(site_config))
    (docs_site / "src").mkdir()
    (docs_site / "src" / "__init__.py").write_text('"""Docs site."""\n')
    (docs_site / "docs").mkdir()
    (docs_site / "docs" / "index.md").write_text("# Docs site\n\nHello.\n")

    result = check_unified(str(docs_site), dry_run=True)

    seo003 = [lint for lint in result.lints if lint.code == "SEO003"]
    assert len(seo003) == 1
    assert seo003[0].file == "[core] " + os.path.join(
        ".selfdoc", "posts", "hello.md",
    )
    assert seo003[0].line == 11

"""Directive attribute enforcement in `selfdoc check` and `selfdoc gen`.

Unknown or missing-required attributes are hard errors (exit 1), distinct
from resolution failures (warning-level FAILED results).
"""

import json
import os
import re

import pytest

from selfdoc.catalog import DirectiveAttrError
from selfdoc.check import check_docs
from selfdoc.gen import generate_root_files


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _project(tmp_path, page_body, root_files=None):
    config = {
        "source": [{"path": "mylib/", "language": "python"}],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
        "author": {"name": "Test Author", "url": "https://author.example"},
        "search_engine": "pagefind",
        "version": "1.0.0",
    }
    if root_files is not None:
        config["root_files"] = root_files
    _write(os.path.join(tmp_path, "selfdoc.json"), json.dumps(config))
    _write(os.path.join(tmp_path, "mylib", "__init__.py"), '"""My library."""\n')
    _write(
        os.path.join(tmp_path, "docs", "index.md"),
        "---\n"
        "title: API\n"
        "description: API reference page describing the public surface of the"
        " library in careful and complete detail\n"
        "---\n"
        "\n"
        "# API\n"
        "\n" + page_body + "\n",
    )
    return tmp_path


class TestCheckEnforcement:
    def test_unknown_attr_is_hard_error(self, tmp_path):
        proj = _project(tmp_path, ':-: ref path="mylib" bogus="1"')
        with pytest.raises(DirectiveAttrError) as exc:
            check_docs(str(proj))
        msg = str(exc.value)
        assert re.search(r"index\.md:\d+", msg), msg
        assert "ref" in msg
        assert "bogus" in msg
        # Allowed attributes are surfaced for actionability.
        assert "path" in msg and "lang" in msg

    def test_missing_required_attr_is_hard_error(self, tmp_path):
        proj = _project(tmp_path, ":-: ref")
        with pytest.raises(DirectiveAttrError) as exc:
            check_docs(str(proj))
        msg = str(exc.value)
        assert "missing required" in msg
        assert "path" in msg

    def test_valid_lang_attr_passes(self, tmp_path):
        proj = _project(tmp_path, ':-: ref path="mylib" lang="python"')
        result = check_docs(str(proj))
        assert any(dr.status == "OK" for dr in result.directive_results)

    def test_unknown_attr_on_callout_is_hard_error(self, tmp_path):
        body = ":<: callout-note title=\"x\"\n:=:\n::: hi\n:>:"
        proj = _project(tmp_path, body)
        with pytest.raises(DirectiveAttrError):
            check_docs(str(proj))


class TestGenEnforcement:
    def _root_template(self, tmp_path, body):
        _write(
            os.path.join(tmp_path, "docs", "_TEST.md"),
            "---\ntitle: T\n---\n\n# T\n\n" + body + "\n",
        )

    def test_gen_refuses_unknown_attr(self, tmp_path):
        proj = _project(tmp_path, ':-: ref path="mylib"', root_files=["docs/_TEST.md"])
        self._root_template(proj, ':-: ref path="mylib" bogus="1"')
        config = json.load(open(os.path.join(proj, "selfdoc.json")))
        with pytest.raises(DirectiveAttrError) as exc:
            generate_root_files(config, base_dir=str(proj))
        msg = str(exc.value)
        assert "docs/_TEST.md" in msg
        assert "bogus" in msg

    def test_gen_refuses_missing_required_attr(self, tmp_path):
        proj = _project(tmp_path, ':-: ref path="mylib"', root_files=["docs/_TEST.md"])
        self._root_template(proj, ":-: ref")
        config = json.load(open(os.path.join(proj, "selfdoc.json")))
        with pytest.raises(DirectiveAttrError) as exc:
            generate_root_files(config, base_dir=str(proj))
        assert "missing required" in str(exc.value)

    def test_gen_accepts_valid_directive(self, tmp_path):
        proj = _project(tmp_path, ':-: ref path="mylib"', root_files=["docs/_TEST.md"])
        self._root_template(proj, ':-: ref path="mylib" lang="python"')
        config = json.load(open(os.path.join(proj, "selfdoc.json")))
        result = generate_root_files(config, base_dir=str(proj))
        assert result  # generated without raising

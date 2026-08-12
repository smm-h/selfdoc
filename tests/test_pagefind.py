"""The search_engine declaration, the indexer subprocess, and SEARCH001."""

import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from conftest import default_config


def _project(tmp_path, **overrides):
    """Write a minimal project whose config carries *overrides*."""
    config = default_config(**overrides)
    (tmp_path / "selfdoc.json").write_text(json.dumps(config))
    src_dir = tmp_path / "src"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "__init__.py").write_text('"""pkg."""\n')
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "index.md").write_text("# Test\n")
    return tmp_path


class TestSearchEngineDeclaration:
    """The engine is declared in the config, never inferred."""

    def test_pagefind_is_the_valid_set(self):
        from selfdoc.config import VALID_SEARCH_ENGINES
        assert VALID_SEARCH_ENGINES == ("pagefind",)

    def test_pagefind_accepted(self, tmp_path):
        from selfdoc.config import load_config

        _project(tmp_path, search_engine="pagefind")
        assert load_config(str(tmp_path))["search_engine"] == "pagefind"

    def test_missing_declaration_is_an_error(self, tmp_path):
        """Absent is refused, and the message names the key and the value."""
        from selfdoc.config import load_config, ConfigError

        config = default_config()
        del config["search_engine"]
        (tmp_path / "selfdoc.json").write_text(json.dumps(config))

        with pytest.raises(ConfigError) as exc:
            load_config(str(tmp_path))
        assert "search_engine" in str(exc.value)
        assert "pagefind" in str(exc.value)

    def test_null_declaration_is_an_error(self, tmp_path):
        from selfdoc.config import load_config, ConfigError

        _project(tmp_path, search_engine=None)
        with pytest.raises(ConfigError, match="search_engine"):
            load_config(str(tmp_path))

    def test_deleted_engines_are_rejected(self, tmp_path):
        from selfdoc.config import load_config, ConfigError

        for dead in ("builtin", "fuse", "minisearch"):
            _project(tmp_path, search_engine=dead)
            with pytest.raises(ConfigError):
                load_config(str(tmp_path))

    def test_unknown_engine_rejected(self, tmp_path):
        from selfdoc.config import load_config, ConfigError

        _project(tmp_path, search_engine="nonexistent")
        with pytest.raises(ConfigError):
            load_config(str(tmp_path))


class TestPagefindBinaryDetection:
    """Pagefind availability detection and error handling."""

    def test_missing_pagefind_raises_error(self):
        from selfdoc.build import _run_pagefind

        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="not installed"):
                _run_pagefind("/fake/output")

    def test_pagefind_subprocess_constructed_correctly(self):
        from selfdoc.build import _run_pagefind
        import sys

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            _run_pagefind("/my/output/dir")

        cmd = mock_run.call_args_list[0][0][0]
        assert cmd == [sys.executable, "-m", "pagefind", "--site", "/my/output/dir"]

    def test_pagefind_failure_reports_stderr(self):
        from selfdoc.build import _run_pagefind

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Something went wrong"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="Something went wrong"):
                _run_pagefind("/fake/output")

    def test_pagefind_timeout_raises_error(self):
        from selfdoc.build import _run_pagefind

        with patch("subprocess.run",
                   side_effect=subprocess.TimeoutExpired("pagefind", 120)):
            with pytest.raises(RuntimeError, match="timed out"):
                _run_pagefind("/fake/output")

    def test_pagefind_falls_back_to_binary(self):
        """If the Python module is absent, the standalone binary is tried."""
        from selfdoc.build import _run_pagefind

        mock_result = MagicMock()
        mock_result.returncode = 0
        call_count = 0

        def side_effect(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise FileNotFoundError
            return mock_result

        with patch("subprocess.run", side_effect=side_effect) as mock_run:
            _run_pagefind("/my/output")

        assert call_count == 2
        assert mock_run.call_args_list[1][0][0] == [
            "pagefind", "--site", "/my/output",
        ]


class TestPagefindCheck:
    """SEARCH001 is unconditional: every build needs the indexer."""

    def test_check_reports_missing_pagefind(self, tmp_path):
        from selfdoc.check import check_docs

        _project(tmp_path)
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = check_docs(str(tmp_path))

        search_lints = [ln for ln in result.lints if ln.code == "SEARCH001"]
        assert len(search_lints) == 1
        assert "not installed" in search_lints[0].message

    def test_check_silent_when_pagefind_available(self, tmp_path):
        from selfdoc.check import check_docs

        _project(tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("selfdoc.check.subprocess.run", return_value=mock_result):
            result = check_docs(str(tmp_path))

        assert [ln for ln in result.lints if ln.code == "SEARCH001"] == []

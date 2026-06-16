"""Tests for Pagefind search engine option (Phase 8.1)."""

import json
import os
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from conftest import default_config


class TestPagefindConfigValidation:
    """Test that 'pagefind' is accepted as a valid search_engine value."""

    def test_pagefind_in_valid_search_engines(self):
        """The VALID_SEARCH_ENGINES constant includes 'pagefind'."""
        from selfdoc.config import VALID_SEARCH_ENGINES
        assert "pagefind" in VALID_SEARCH_ENGINES

    def test_pagefind_accepted_in_config(self, tmp_path):
        """Loading a config with search_engine='pagefind' succeeds."""
        from selfdoc.config import load_config

        config = default_config(search_engine="pagefind")
        config_path = tmp_path / "selfdoc.json"
        config_path.write_text(json.dumps(config))

        # Create minimal project structure
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "__init__.py").write_text('"""pkg."""\n')
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "index.md").write_text("# Test\n")

        loaded = load_config(str(tmp_path))
        assert loaded["search_engine"] == "pagefind"

    def test_invalid_search_engine_rejected(self, tmp_path):
        """Loading a config with an invalid search_engine raises an error."""
        from selfdoc.config import load_config, ConfigError

        config = default_config(search_engine="nonexistent")
        config_path = tmp_path / "selfdoc.json"
        config_path.write_text(json.dumps(config))

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "__init__.py").write_text('"""pkg."""\n')
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "index.md").write_text("# Test\n")

        with pytest.raises(ConfigError):
            load_config(str(tmp_path))


class TestPagefindBinaryDetection:
    """Test pagefind availability detection and error handling."""

    def test_missing_pagefind_raises_error(self):
        """When pagefind is not available, _run_pagefind raises RuntimeError."""
        from selfdoc.build import _run_pagefind

        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="not installed"):
                _run_pagefind("/fake/output")

    def test_pagefind_subprocess_constructed_correctly(self):
        """The pagefind subprocess call uses --site with the output dir."""
        from selfdoc.build import _run_pagefind
        import sys

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            _run_pagefind("/my/output/dir")

        # Should have been called with the Python module form first
        call_args = mock_run.call_args_list[0]
        cmd = call_args[0][0]
        assert cmd == [sys.executable, "-m", "pagefind", "--site", "/my/output/dir"]

    def test_pagefind_failure_reports_stderr(self):
        """When pagefind exits non-zero, the error includes stderr."""
        from selfdoc.build import _run_pagefind

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Something went wrong"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="Something went wrong"):
                _run_pagefind("/fake/output")

    def test_pagefind_timeout_raises_error(self):
        """When pagefind times out, a clear error is raised."""
        from selfdoc.build import _run_pagefind

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pagefind", 120)):
            with pytest.raises(RuntimeError, match="timed out"):
                _run_pagefind("/fake/output")

    def test_pagefind_falls_back_to_binary(self):
        """If Python module fails with FileNotFoundError, tries standalone binary."""
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
        # Second call should be the standalone binary
        second_call = mock_run.call_args_list[1]
        cmd = second_call[0][0]
        assert cmd == ["pagefind", "--site", "/my/output"]


class TestPagefindCheck:
    """Test that selfdoc check reports missing pagefind."""

    def test_check_warns_when_pagefind_missing(self, tmp_path):
        """selfdoc check emits SEARCH001 when pagefind is configured but missing."""
        from selfdoc.check import check_docs

        config = default_config(search_engine="pagefind")
        config_path = tmp_path / "selfdoc.json"
        config_path.write_text(json.dumps(config))

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "__init__.py").write_text('"""pkg."""\n')
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "index.md").write_text("# Test\n")

        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = check_docs(str(tmp_path))

        search_lints = [l for l in result.lints if l.code == "SEARCH001"]
        assert len(search_lints) == 1
        assert "not installed" in search_lints[0].message

    def test_check_no_warning_when_pagefind_available(self, tmp_path):
        """selfdoc check does NOT emit SEARCH001 when pagefind is available."""
        from selfdoc.check import check_docs

        config = default_config(search_engine="pagefind")
        config_path = tmp_path / "selfdoc.json"
        config_path.write_text(json.dumps(config))

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "__init__.py").write_text('"""pkg."""\n')
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "index.md").write_text("# Test\n")

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("selfdoc.check.subprocess.run", return_value=mock_result):
            result = check_docs(str(tmp_path))

        search_lints = [l for l in result.lints if l.code == "SEARCH001"]
        assert len(search_lints) == 0

    def test_check_no_warning_for_builtin_engine(self, tmp_path):
        """selfdoc check does NOT emit SEARCH001 for builtin search engine."""
        from selfdoc.check import check_docs

        config = default_config()  # no search_engine = defaults to builtin
        config_path = tmp_path / "selfdoc.json"
        config_path.write_text(json.dumps(config))

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "__init__.py").write_text('"""pkg."""\n')
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "index.md").write_text("# Test\n")

        result = check_docs(str(tmp_path))

        search_lints = [l for l in result.lints if l.code == "SEARCH001"]
        assert len(search_lints) == 0

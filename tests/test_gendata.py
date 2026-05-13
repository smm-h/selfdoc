"""Tests for selfdoc.gendata -- sandboxed script execution for data generation."""

import json
import os
import subprocess
from unittest import mock

import pytest

from selfdoc.gendata import (
    GenDataError,
    _build_bwrap_command,
    _check_bwrap,
    _validate_output,
    _validate_script,
    generate_data,
)


class TestNoGenDataConfig:
    """When gen_data is absent or empty, generate_data returns []."""

    def test_no_gen_data_key(self):
        result = generate_data({})
        assert result == []

    def test_empty_gen_data(self):
        result = generate_data({"gen_data": {}})
        assert result == []

    def test_empty_scripts_list(self):
        result = generate_data({"gen_data": {"scripts": []}})
        assert result == []


class TestMissingBwrap:
    """When bwrap is not installed, a clear error is raised."""

    def test_missing_bwrap_error(self):
        config = {
            "gen_data": {
                "scripts": [
                    {
                        "command": "python3 scripts/test.py",
                        "output": "test.json",
                        "mounts": ["src/"],
                    }
                ]
            }
        }
        with mock.patch("selfdoc.gendata.shutil.which", return_value=None):
            with pytest.raises(GenDataError, match="gen-data requires bubblewrap"):
                generate_data(config)

    def test_error_includes_install_instructions(self):
        with mock.patch("selfdoc.gendata.shutil.which", return_value=None):
            with pytest.raises(GenDataError) as exc_info:
                _check_bwrap()
            msg = str(exc_info.value)
            assert "sudo dnf install bubblewrap" in msg
            assert "sudo apt install bubblewrap" in msg


class TestScriptValidation:
    """Script declarations must have command, output, and mounts."""

    def test_missing_command(self):
        with pytest.raises(GenDataError, match="command"):
            _validate_script({"output": "out.json", "mounts": []})

    def test_missing_output(self):
        with pytest.raises(GenDataError, match="output"):
            _validate_script({"command": "echo hi", "mounts": []})

    def test_missing_mounts(self):
        with pytest.raises(GenDataError, match="mounts"):
            _validate_script({"command": "echo hi", "output": "out.json"})

    def test_missing_multiple_fields(self):
        with pytest.raises(GenDataError, match="command.*output.*mounts"):
            _validate_script({})

    def test_mounts_not_a_list(self):
        with pytest.raises(GenDataError, match="mounts.*must be a list"):
            _validate_script({
                "command": "echo hi",
                "output": "out.json",
                "mounts": "src/",
            })

    def test_valid_script(self):
        # Should not raise
        _validate_script({
            "command": "python3 test.py",
            "output": "result.json",
            "mounts": ["src/"],
        })


class TestBwrapCommandConstruction:
    """Verify the bwrap command is built correctly."""

    def test_basic_command_structure(self):
        script = {
            "command": "python3 scripts/extract.py",
            "output": "targets.json",
            "mounts": ["selfdoc/"],
        }
        cmd = _build_bwrap_command(script, "/project", "/project/.selfdoc/data")

        assert cmd[0] == "bwrap"
        assert "--die-with-parent" in cmd
        assert "--unshare-all" in cmd
        assert "--clearenv" in cmd

    def test_read_only_mounts(self):
        script = {
            "command": "python3 test.py",
            "output": "out.json",
            "mounts": ["src/", "lib/"],
        }
        cmd = _build_bwrap_command(script, "/project", "/project/.selfdoc/data")

        # Each mount should appear as --ro-bind <abs> <abs>
        abs_src = os.path.abspath("/project/src/")
        abs_lib = os.path.abspath("/project/lib/")
        for i, arg in enumerate(cmd):
            if arg == "--ro-bind" and i + 1 < len(cmd) and cmd[i + 1] == abs_src:
                assert cmd[i + 2] == abs_src
                break
        else:
            pytest.fail(f"Expected --ro-bind for {abs_src}")

    def test_output_dir_writable(self):
        script = {
            "command": "python3 test.py",
            "output": "out.json",
            "mounts": [],
        }
        output_dir = "/project/.selfdoc/data"
        cmd = _build_bwrap_command(script, "/project", output_dir)

        abs_output = os.path.abspath(output_dir)
        # Find --bind (not --ro-bind) for output dir
        for i, arg in enumerate(cmd):
            if arg == "--bind" and i + 1 < len(cmd) and cmd[i + 1] == abs_output:
                assert cmd[i + 2] == abs_output
                break
        else:
            pytest.fail(f"Expected --bind for {abs_output}")

    def test_system_mounts(self):
        script = {
            "command": "python3 test.py",
            "output": "out.json",
            "mounts": [],
        }
        cmd = _build_bwrap_command(script, "/project", "/project/.selfdoc/data")

        # System paths that exist should be ro-bound
        for sys_path in ("/usr", "/bin"):
            if os.path.exists(sys_path):
                assert sys_path in cmd, f"Expected {sys_path} in bwrap command"

    def test_proc_and_dev(self):
        script = {
            "command": "python3 test.py",
            "output": "out.json",
            "mounts": [],
        }
        cmd = _build_bwrap_command(script, "/project", "/project/.selfdoc/data")

        assert "--proc" in cmd
        assert "/proc" in cmd
        assert "--dev" in cmd
        assert "/dev" in cmd

    def test_chdir_to_base(self):
        script = {
            "command": "python3 test.py",
            "output": "out.json",
            "mounts": [],
        }
        cmd = _build_bwrap_command(script, "/project", "/project/.selfdoc/data")

        chdir_idx = cmd.index("--chdir")
        assert cmd[chdir_idx + 1] == os.path.abspath("/project")

    def test_command_after_separator(self):
        script = {
            "command": "python3 scripts/extract.py",
            "output": "out.json",
            "mounts": [],
        }
        cmd = _build_bwrap_command(script, "/project", "/project/.selfdoc/data")

        sep_idx = cmd.index("--")
        assert cmd[sep_idx + 1] == "python3"
        assert cmd[sep_idx + 2] == "scripts/extract.py"


class TestOutputValidation:
    """Output files must be valid JSON or CSV."""

    def test_valid_json(self, tmp_path):
        filepath = os.path.join(tmp_path, "data.json")
        with open(filepath, "w") as f:
            json.dump({"key": "value"}, f)
        # Should not raise
        _validate_output(filepath)

    def test_invalid_json(self, tmp_path):
        filepath = os.path.join(tmp_path, "data.json")
        with open(filepath, "w") as f:
            f.write("{invalid json")
        with pytest.raises(GenDataError, match="not valid JSON"):
            _validate_output(filepath)

    def test_valid_csv(self, tmp_path):
        filepath = os.path.join(tmp_path, "data.csv")
        with open(filepath, "w") as f:
            f.write("name,value\na,1\nb,2\n")
        # Should not raise
        _validate_output(filepath)

    def test_unreadable_file(self, tmp_path):
        filepath = os.path.join(tmp_path, "missing.json")
        with pytest.raises(GenDataError, match="cannot read output file"):
            _validate_output(filepath)

    def test_unknown_extension_no_validation(self, tmp_path):
        filepath = os.path.join(tmp_path, "data.txt")
        with open(filepath, "w") as f:
            f.write("just some text")
        # Unknown extensions should not raise (no format check)
        _validate_output(filepath)


class TestGenerateDataIntegration:
    """Test the full generate_data flow with mocked subprocess."""

    def test_successful_run(self, tmp_path):
        config = {
            "gen_data": {
                "scripts": [
                    {
                        "command": "python3 scripts/extract.py",
                        "output": "targets.json",
                        "mounts": ["selfdoc/"],
                    }
                ]
            }
        }
        output_dir = os.path.join(tmp_path, ".selfdoc", "data")
        os.makedirs(output_dir, exist_ok=True)

        # Pre-create the expected output file
        output_file = os.path.join(output_dir, "targets.json")
        with open(output_file, "w") as f:
            json.dump({"targets": []}, f)

        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with mock.patch("selfdoc.gendata.shutil.which", return_value="/usr/bin/bwrap"):
            with mock.patch("selfdoc.gendata.subprocess.run", return_value=mock_result):
                result = generate_data(config, base_dir=str(tmp_path))

        assert len(result) == 1
        assert result[0] == output_file

    def test_script_failure(self, tmp_path):
        config = {
            "gen_data": {
                "scripts": [
                    {
                        "command": "python3 scripts/fail.py",
                        "output": "out.json",
                        "mounts": [],
                    }
                ]
            }
        }

        mock_result = mock.MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "some error"

        with mock.patch("selfdoc.gendata.shutil.which", return_value="/usr/bin/bwrap"):
            with mock.patch("selfdoc.gendata.subprocess.run", return_value=mock_result):
                with pytest.raises(GenDataError, match="failed with exit code 1"):
                    generate_data(config, base_dir=str(tmp_path))

    def test_timeout(self, tmp_path):
        config = {
            "gen_data": {
                "scripts": [
                    {
                        "command": "python3 scripts/slow.py",
                        "output": "out.json",
                        "mounts": [],
                    }
                ]
            }
        }

        with mock.patch("selfdoc.gendata.shutil.which", return_value="/usr/bin/bwrap"):
            with mock.patch(
                "selfdoc.gendata.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="bwrap ...", timeout=60),
            ):
                with pytest.raises(GenDataError, match="timed out after 60 seconds"):
                    generate_data(config, base_dir=str(tmp_path))

    def test_missing_output_file(self, tmp_path):
        config = {
            "gen_data": {
                "scripts": [
                    {
                        "command": "python3 scripts/noop.py",
                        "output": "missing.json",
                        "mounts": [],
                    }
                ]
            }
        }

        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with mock.patch("selfdoc.gendata.shutil.which", return_value="/usr/bin/bwrap"):
            with mock.patch("selfdoc.gendata.subprocess.run", return_value=mock_result):
                with pytest.raises(GenDataError, match="did not produce expected output"):
                    generate_data(config, base_dir=str(tmp_path))

    def test_creates_output_directory(self, tmp_path):
        config = {
            "gen_data": {
                "scripts": [
                    {
                        "command": "python3 scripts/extract.py",
                        "output": "data.json",
                        "mounts": [],
                    }
                ]
            }
        }

        output_dir = os.path.join(tmp_path, ".selfdoc", "data")
        output_file = os.path.join(output_dir, "data.json")

        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        def fake_run(*args, **kwargs):
            # Simulate the script creating the output file
            os.makedirs(output_dir, exist_ok=True)
            with open(output_file, "w") as f:
                json.dump([], f)
            return mock_result

        with mock.patch("selfdoc.gendata.shutil.which", return_value="/usr/bin/bwrap"):
            with mock.patch("selfdoc.gendata.subprocess.run", side_effect=fake_run):
                result = generate_data(config, base_dir=str(tmp_path))

        assert os.path.isdir(output_dir)
        assert len(result) == 1

    def test_multiple_scripts(self, tmp_path):
        config = {
            "gen_data": {
                "scripts": [
                    {
                        "command": "python3 scripts/a.py",
                        "output": "a.json",
                        "mounts": [],
                    },
                    {
                        "command": "python3 scripts/b.py",
                        "output": "b.json",
                        "mounts": [],
                    },
                ]
            }
        }
        output_dir = os.path.join(tmp_path, ".selfdoc", "data")
        os.makedirs(output_dir, exist_ok=True)

        call_count = [0]

        def fake_run(*args, **kwargs):
            call_count[0] += 1
            filename = "a.json" if call_count[0] == 1 else "b.json"
            with open(os.path.join(output_dir, filename), "w") as f:
                json.dump({}, f)
            result = mock.MagicMock()
            result.returncode = 0
            result.stderr = ""
            return result

        with mock.patch("selfdoc.gendata.shutil.which", return_value="/usr/bin/bwrap"):
            with mock.patch("selfdoc.gendata.subprocess.run", side_effect=fake_run):
                result = generate_data(config, base_dir=str(tmp_path))

        assert len(result) == 2

    def test_subprocess_called_with_timeout(self, tmp_path):
        config = {
            "gen_data": {
                "scripts": [
                    {
                        "command": "python3 scripts/test.py",
                        "output": "out.json",
                        "mounts": [],
                    }
                ]
            }
        }
        output_dir = os.path.join(tmp_path, ".selfdoc", "data")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "out.json")
        with open(output_file, "w") as f:
            json.dump({}, f)

        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with mock.patch("selfdoc.gendata.shutil.which", return_value="/usr/bin/bwrap"):
            with mock.patch(
                "selfdoc.gendata.subprocess.run", return_value=mock_result
            ) as mock_run:
                generate_data(config, base_dir=str(tmp_path))

        # Verify timeout was passed
        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == 60

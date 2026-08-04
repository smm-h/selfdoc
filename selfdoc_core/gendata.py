"""Generate data files by running sandboxed scripts via bubblewrap (bwrap)."""

import csv
import io
import json
import os
import shutil
import subprocess

from selfdoc_core import effects


class GenDataError(Exception):
    """Raised when gen-data encounters an error."""


def _validate_script(script):
    """Validate that a script declaration has all required fields.

    Raises GenDataError if command, output, or mounts is missing or invalid.
    """
    missing = []
    for field in ("command", "output", "mounts"):
        if field not in script:
            missing.append(field)
    if missing:
        raise GenDataError(
            f"script declaration missing required field(s): {', '.join(missing)}"
        )
    if not isinstance(script["mounts"], list):
        raise GenDataError("'mounts' must be a list of paths")


def _check_bwrap():
    """Check that bwrap is available on the system.

    Raises GenDataError with installation instructions if not found.
    """
    if shutil.which("bwrap") is None:
        raise GenDataError(
            "gen-data requires bubblewrap (bwrap). Install it: "
            "sudo dnf install bubblewrap (Fedora) or "
            "sudo apt install bubblewrap (Debian/Ubuntu)"
        )


def _build_bwrap_command(script, base_dir, output_dir):
    """Build the bwrap command list for a script declaration.

    Returns a list of strings suitable for subprocess.run.
    """
    abs_base = os.path.abspath(base_dir)
    abs_output = os.path.abspath(output_dir)

    cmd = [
        "bwrap",
        "--die-with-parent",
        "--unshare-all",
        "--clearenv",
    ]

    # Read-only mounts for script dependencies
    for mount in script["mounts"]:
        abs_mount = os.path.abspath(os.path.join(abs_base, mount))
        cmd.extend(["--ro-bind", abs_mount, abs_mount])

    # Read-write bind for output directory
    cmd.extend(["--bind", abs_output, abs_output])

    # System binaries needed to run scripts
    for sys_path in ("/usr", "/lib", "/lib64", "/bin", "/sbin"):
        if os.path.exists(sys_path):
            cmd.extend(["--ro-bind", sys_path, sys_path])

    # Basic filesystem
    cmd.extend(["--proc", "/proc", "--dev", "/dev"])

    # Working directory
    cmd.extend(["--chdir", abs_base])

    # The actual command
    cmd.append("--")
    cmd.extend(script["command"].split())

    return cmd


def _validate_output(filepath):
    """Validate that an output file is valid JSON or CSV based on extension.

    Raises GenDataError if the file cannot be parsed.
    """
    ext = os.path.splitext(filepath)[1].lower()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError as e:
        raise GenDataError(f"cannot read output file {filepath}: {e}") from e

    if ext == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            raise GenDataError(
                f"output file {filepath} is not valid JSON: {e}"
            ) from e
    elif ext == ".csv":
        try:
            csv.reader(io.StringIO(content))
            # Just verify it parses without error by consuming the reader
            list(csv.reader(io.StringIO(content)))
        except csv.Error as e:
            raise GenDataError(
                f"output file {filepath} is not valid CSV: {e}"
            ) from e


def generate_data(config, base_dir="."):
    """Run sandboxed scripts to generate data files.

    Reads gen_data.scripts from config, runs each script inside a bwrap
    sandbox, and validates the output. Returns a list of output file paths.

    Raises GenDataError on validation failures, missing bwrap, or script errors.
    """
    scripts = config.get("gen_data", {}).get("scripts", [])
    if not scripts:
        return []

    output_dir = os.path.join(base_dir, ".selfdoc", "data")
    effects.makedirs(output_dir, exist_ok=True)

    _check_bwrap()

    generated = []

    for script in scripts:
        _validate_script(script)

        bwrap_cmd = _build_bwrap_command(script, base_dir, output_dir)

        try:
            result = effects.run(
                bwrap_cmd,
                capture_output=True,
                text=True,
                timeout=60,
                resource=f"gendata:{script['output']}",
            )
        except subprocess.TimeoutExpired as e:
            raise GenDataError(
                f"script timed out after 60 seconds: {script['command']}"
            ) from e

        if result.returncode != 0:
            raise GenDataError(
                f"script failed with exit code {result.returncode}: "
                f"{script['command']}\nstderr: {result.stderr}"
            )

        output_path = os.path.join(output_dir, script["output"])
        if not os.path.isfile(output_path):
            raise GenDataError(
                f"script did not produce expected output file: {output_path}"
            )

        _validate_output(output_path)
        generated.append(output_path)

    return generated

#!/usr/bin/env python3
"""Regenerate every ``.strictcli/schema.json`` this repository tracks.

Three schema files are tracked, and until now only two of them could be
regenerated:

- ``selfdoc/.strictcli/schema.json`` -- the selfdoc app's own dump;
- ``selfblog/.strictcli/schema.json`` -- the selfblog app's own dump;
- ``.strictcli/schema.json`` at the repo root -- read by ``selfdoc gen``,
  because the docs site lives at the root (``selfdoc.json``, ``docs/``)
  while the package lives in ``selfdoc/``.

``--dump-schema`` writes to the current directory and reads the project id
out of the current directory's ``pyproject.toml``, and the workspace root
has no ``[project]`` table -- so the root copy cannot be produced by running
the dump there, and it went stale the moment the CLI changed. That is what
this script exists to stop: it runs each app's dump in the app's own
directory and then copies the selfdoc dump to the root, where ``gen`` reads
it.

Run it from anywhere in the checkout, or let the selfdoc releasable's
``pre-checks.sh`` run it before ``selfdoc gen``.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys


#: (package directory, console script) for each app that dumps a schema.
APPS = [("selfdoc", "selfdoc"), ("selfblog", "selfblog")]

#: The app whose dump the root docs site reads.
ROOT_SCHEMA_SOURCE = "selfdoc"

SCHEMA_RELPATH = os.path.join(".strictcli", "schema.json")


def _repo_root():
    return subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def dump_schemas(root, *, check_only=False):
    """Dump every app's schema; return the list of paths that changed."""
    changed = []
    for pkg_dir, script in APPS:
        target = os.path.join(root, pkg_dir, SCHEMA_RELPATH)
        before = _read(target)
        subprocess.run(
            ["uv", "run", "--project", ".", script, "--dump-schema"],
            cwd=os.path.join(root, pkg_dir), check=True,
            stdout=subprocess.DEVNULL,
        )
        after = _read(target)
        if before != after:
            changed.append(os.path.relpath(target, root))

    # The root copy is the selfdoc app's dump under a second name, because
    # that is where `selfdoc gen` looks for it.
    source = os.path.join(root, ROOT_SCHEMA_SOURCE, SCHEMA_RELPATH)
    root_target = os.path.join(root, SCHEMA_RELPATH)
    if _read(root_target) != _read(source):
        changed.append(SCHEMA_RELPATH)
        if not check_only:
            os.makedirs(os.path.dirname(root_target), exist_ok=True)
            shutil.copyfile(source, root_target)

    return changed


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="report drift and exit 1 without writing the root copy",
    )
    args = parser.parse_args(argv)

    root = _repo_root()
    changed = dump_schemas(root, check_only=args.check)

    if not changed:
        print("schemas: already current")
        return 0
    for path in changed:
        print(f"schemas: updated {path}")
    versions = {
        path: json.loads(_read(os.path.join(root, path)) or "{}").get(
            "schema_version"
        )
        for path in changed
    }
    for path, version in versions.items():
        print(f"schemas: {path} is schema_version {version}")
    return 1 if args.check else 0


if __name__ == "__main__":
    sys.exit(main())

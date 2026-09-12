#!/usr/bin/env python3
"""Record the Python selfdoc.gen output for the Go port's byte-equality tests.

The Go port of ``selfdoc/gen.py`` must emit the same bytes as the Python it
replaces.  This script is the recorder: for each fixture project under
``fixture/``, it copies the project into a scratch directory outside the
repository, runs the Python ``generate_docs`` and ``generate_root_files``
against that copy, and writes every file they produced under
``expected/<fixture>/``.  The Go test builds the same copy from the same
fixture, runs the Go implementation, and compares byte for byte.

Run it with an interpreter that can import ``selfdoc`` -- from the repository
root, that is the pinned tool's interpreter:

    /home/m/.local/share/uv/tools/selfdoc/bin/python internal/gen/testdata/record.py

The recorded outputs are committed.  Re-record only when the Python's own
output legitimately changes; a diff otherwise is the port being wrong.
"""

import os
import shutil
import sys
import tempfile

FIXTURES = ("python", "go", "rootfiles")

# Files each fixture's run is expected to produce, relative to the project
# root.  Naming them rather than sweeping the tree keeps the recording
# deliberate: a file that appears without being named here is a change to
# review, not a new expectation to bless.
RECORDED_PREFIXES = ("docs/", ".selfdoc/hashes/")
RECORDED_ROOT_FILES = ("TEST.md",)


def load_config(project_dir):
    import json

    with open(os.path.join(project_dir, "selfdoc.json"), encoding="utf-8") as f:
        return json.load(f)


def record(fixture, testdata_dir):
    fixture_dir = os.path.join(testdata_dir, "fixture", fixture)
    expected_dir = os.path.join(testdata_dir, "expected", fixture)

    from selfdoc.gen import generate_docs, generate_root_files

    with tempfile.TemporaryDirectory(prefix="selfdoc-gen-record-") as scratch:
        project = os.path.join(scratch, "project")
        shutil.copytree(fixture_dir, project)

        config = load_config(project)
        if config.get("source"):
            generate_docs(config, base_dir=project)
        generate_root_files(config, base_dir=project)

        if os.path.isdir(expected_dir):
            shutil.rmtree(expected_dir)
        os.makedirs(expected_dir, exist_ok=True)

        recorded = []
        for prefix in RECORDED_PREFIXES:
            source_dir = os.path.join(project, prefix)
            if not os.path.isdir(source_dir):
                continue
            for entry in sorted(os.listdir(source_dir)):
                full = os.path.join(source_dir, entry)
                if not os.path.isfile(full):
                    continue
                if entry.startswith("_"):
                    # A root-file template is an input of the run, not an
                    # output of it.
                    continue
                rel = prefix + entry
                target = os.path.join(expected_dir, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copyfile(full, target)
                os.chmod(target, 0o644)
                recorded.append(rel)
        for name in RECORDED_ROOT_FILES:
            full = os.path.join(project, name)
            if not os.path.isfile(full):
                continue
            shutil.copyfile(full, os.path.join(expected_dir, name))
            os.chmod(os.path.join(expected_dir, name), 0o644)
            recorded.append(name)

    print(f"{fixture}: {len(recorded)} file(s)")
    for rel in recorded:
        print(f"  {rel}")


def main():
    testdata_dir = os.path.dirname(os.path.abspath(__file__))
    for fixture in FIXTURES:
        record(fixture, testdata_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())

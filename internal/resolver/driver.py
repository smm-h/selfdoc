"""Run one custom directive script and print the Markdown it returns.

selfdoc's ``directives`` config key maps a directive name to a script that
resolves it.  The contract is the one it has always had: the script defines
``resolve(attrs, config, body)`` and returns Markdown.  That contract is
Python's, so the script is still loaded and called by Python -- this driver is
handed to python3 on its command line, the script's path as its one argument,
and one JSON object on standard input:

    {"attrs": {...}, "config": {...}, "body": [...], "base_dir": "..."}

Markdown goes to standard output.  Every failure -- a script that will not
load, one with no callable ``resolve``, one that raises -- writes the reason to
standard error and exits non-zero, and the Go side turns that into the hard
error naming the directive and the script.  Nothing is ever printed to standard
output on a failure, so a caller can never mistake a diagnostic for content.
"""

import importlib.util
import json
import sys

#: The module name the script is loaded under.  Each run is a fresh
#: interpreter, so one fixed name cannot collide with anything.
MODULE_NAME = "selfdoc_custom"


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: <driver> <script_path>")
        return 2
    script_path = argv[1]

    try:
        payload = json.load(sys.stdin)
    except ValueError as exc:
        sys.stderr.write(f"the directive payload is not JSON: {exc}")
        return 2

    spec = importlib.util.spec_from_file_location(MODULE_NAME, script_path)
    if spec is None or spec.loader is None:
        sys.stderr.write(
            f"custom directive script '{script_path}' cannot be imported"
        )
        return 1
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 -- the script decides what it raises
        sys.stderr.write(str(exc))
        return 1

    resolve = getattr(module, "resolve", None)
    if not callable(resolve):
        sys.stderr.write(
            f"custom directive script '{script_path}' has no callable 'resolve'"
        )
        return 1

    try:
        result = resolve(payload["attrs"], payload["config"], payload["body"])
    except Exception as exc:  # noqa: BLE001 -- the script decides what it raises
        sys.stderr.write(str(exc))
        return 1

    sys.stdout.write(result if isinstance(result, str) else str(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

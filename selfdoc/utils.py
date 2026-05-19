"""Shared utility functions for selfdoc."""

import ast
import os
import re
import tempfile


def extract_module_docstring(filepath):
    """Extract the first line of a Python module's docstring.

    Uses ``ast.parse`` and ``ast.get_docstring`` to read the module-level
    docstring.  Returns the first sentence (up to the first period followed
    by whitespace/end, or the first newline), truncated to 155 characters.
    Returns ``None`` if the file is not Python, cannot be parsed, or has
    no module docstring.
    """
    if not filepath.endswith(".py"):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return None
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return None
    docstring = ast.get_docstring(tree)
    if not docstring:
        return None
    # Take the first line
    first_line = docstring.split("\n", 1)[0].strip()
    if not first_line:
        return None
    # Take up to the first sentence-ending period (period followed by
    # whitespace or end-of-string)
    match = re.search(r"\.\s", first_line)
    if match:
        first_line = first_line[: match.start() + 1]
    elif first_line.endswith("."):
        pass  # already ends with period
    # Truncate to 155 chars
    if len(first_line) > 155:
        first_line = first_line[:152] + "..."
    return first_line


def atomic_write(filepath, content, permissions=None):
    """Write *content* to *filepath* atomically.

    Writes to a temporary file in the same directory, then replaces the
    target.  Optionally sets file permissions after writing.
    """
    dir_name = os.path.dirname(filepath)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        if permissions is not None:
            os.chmod(tmp_path, permissions)
        os.replace(tmp_path, filepath)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

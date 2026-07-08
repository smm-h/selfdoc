"""Version detection for selfdoc."""

import os


def _detect_version():
    """Detect package version, preferring pyproject.toml over installed metadata.

    Order: pyproject.toml inside the package directory (accurate during
    editable installs) -> importlib.metadata (works for regular installs)
    -> "unknown".
    """
    # Try reading version from the pyproject.toml that lives inside the
    # package directory (flat monorepo layout).
    try:
        pyproject_path = os.path.join(os.path.dirname(__file__), "pyproject.toml")
        if os.path.isfile(pyproject_path):
            import tomllib
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
            return data["project"]["version"]
    except Exception:
        pass

    # Fall back to installed dist-info metadata
    try:
        from importlib.metadata import version as _get_version
        return _get_version("selfdoc")
    except Exception:
        pass

    return "unknown"


__version__ = _detect_version()

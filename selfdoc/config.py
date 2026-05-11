"""Config loader for selfdoc.json."""

import json
import os

VALID_LANGUAGES = ("python", "go", "typescript", "javascript")
VALID_DEPLOY_PROVIDERS = ("cloudflare-pages", "github-pages")


class ConfigError(Exception):
    """Raised when selfdoc.json is present but invalid."""


def _validate_deploy(deploy):
    """Validate the deploy section if present.

    Raises ConfigError if provider is unrecognized or required fields are missing.
    """
    if not isinstance(deploy, dict):
        raise ConfigError("'deploy' must be an object")

    provider = deploy.get("provider")
    if provider is None:
        raise ConfigError("'deploy.provider' is required when deploy section is present")

    if provider not in VALID_DEPLOY_PROVIDERS:
        raise ConfigError(
            f"invalid deploy provider {provider!r}; "
            f"must be one of: {', '.join(VALID_DEPLOY_PROVIDERS)}"
        )

    if provider == "cloudflare-pages" and not deploy.get("project"):
        raise ConfigError("'deploy.project' is required for cloudflare-pages provider")


def load_config(dir_path="."):
    """Load and validate selfdoc.json from *dir_path*.

    Returns the validated config dict, or None if selfdoc.json does not exist.
    Raises ConfigError on malformed or invalid configuration.
    """
    config_path = os.path.join(dir_path, "selfdoc.json")

    if not os.path.isfile(config_path):
        return None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"selfdoc.json is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("selfdoc.json must be a JSON object")

    # --- required fields ---
    if "language" not in raw:
        raise ConfigError("missing required field 'language'")

    language = raw["language"]
    if language not in VALID_LANGUAGES:
        raise ConfigError(
            f"invalid language {language!r}; "
            f"must be one of: {', '.join(VALID_LANGUAGES)}"
        )

    if "source" not in raw:
        raise ConfigError("missing required field 'source'")

    source = raw["source"]
    if not isinstance(source, list) or not source:
        raise ConfigError("'source' must be a non-empty list of paths")

    # --- optional fields with defaults ---
    docs = raw.get("docs", "docs/")
    output = raw.get("output", "docs/_build/")
    theme = raw.get("theme", "minimal")
    deploy = raw.get("deploy", None)
    directives = raw.get("directives", {})

    if not isinstance(theme, str) or not theme:
        raise ConfigError("'theme' must be a non-empty string")

    if deploy is not None:
        _validate_deploy(deploy)

    if not isinstance(directives, dict):
        raise ConfigError("'directives' must be an object")

    repo = raw.get("repo", None)
    if repo is not None and not isinstance(repo, str):
        raise ConfigError("'repo' must be a string (GitHub repo URL)")

    return {
        "language": language,
        "source": source,
        "docs": docs,
        "output": output,
        "theme": theme,
        "deploy": deploy,
        "directives": directives,
        "repo": repo,
    }

"""Config loader for selfdoc.json."""

import json
import os
import re

VALID_LANGUAGES = ("python", "go", "typescript", "javascript")
VALID_DEPLOY_PROVIDERS = ("cloudflare-pages", "github-pages")
VALID_SEARCH_ENGINES = ("builtin", "fuse", "minisearch")


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

    if "base_url" not in raw:
        raise ConfigError("'base_url' is required")
    base_url = raw["base_url"]
    if not isinstance(base_url, str) or not base_url:
        raise ConfigError("'base_url' must be a non-empty string (e.g. 'https://example.com')")
    # Strip trailing slash for consistent URL joining
    base_url = base_url.rstrip("/")

    lang = raw.get("lang", None)
    if lang is not None:
        if not isinstance(lang, str) or not lang:
            raise ConfigError("'lang' must be a non-empty string (BCP 47 language tag)")
        if not re.match(r"^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$", lang):
            raise ConfigError(
                f"invalid lang {lang!r}; must be a valid BCP 47 language tag "
                f"(e.g. 'en', 'en-US', 'pt-BR')"
            )

    description = raw.get("description", None)
    if description is not None:
        if not isinstance(description, str) or not description:
            raise ConfigError("'description' must be a non-empty string")

    author = raw.get("author", None)
    if author is not None:
        if not isinstance(author, dict):
            raise ConfigError("'author' must be an object")
        if "name" not in author or not isinstance(author["name"], str) or not author["name"]:
            raise ConfigError("'author.name' is required and must be a non-empty string")
        if "type" in author and author["type"] not in ("Person", "Organization"):
            raise ConfigError(
                "'author.type' must be 'Person' or 'Organization'"
            )
        if "twitter" in author:
            if not isinstance(author["twitter"], str) or not author["twitter"]:
                raise ConfigError("'author.twitter' must be a non-empty string")
            if not author["twitter"].startswith("@"):
                raise ConfigError("'author.twitter' must start with '@'")

    top_twitter = raw.get("twitter", None)
    if top_twitter is not None:
        if not isinstance(top_twitter, str) or not top_twitter:
            raise ConfigError("'twitter' must be a non-empty string")
        if not top_twitter.startswith("@"):
            raise ConfigError("'twitter' must start with '@'")

    # Resolve twitter: author.twitter takes precedence over top-level twitter
    twitter = None
    if author and author.get("twitter"):
        twitter = author["twitter"]
    elif top_twitter:
        twitter = top_twitter

    valid_search_values = ("icon", "bar", "hidden")
    search = raw.get("search", None)
    if search is not None:
        if not isinstance(search, str) or search not in valid_search_values:
            raise ConfigError(
                f"invalid search value {search!r}; "
                f"must be one of: {', '.join(valid_search_values)}"
            )

    search_engine = raw.get("search_engine", None)
    if search_engine is not None:
        if not isinstance(search_engine, str) or search_engine not in VALID_SEARCH_ENGINES:
            raise ConfigError(
                f"invalid search_engine value {search_engine!r}; "
                f"must be one of: {', '.join(VALID_SEARCH_ENGINES)}"
            )

    feedback = raw.get("feedback", None)
    if feedback is not None:
        if not isinstance(feedback, dict):
            raise ConfigError("'feedback' must be an object")
        webhook = feedback.get("webhook")
        ga = feedback.get("ga")
        if webhook is None and ga is None:
            raise ConfigError(
                "'feedback' must contain at least one of 'webhook' or 'ga'"
            )
        if webhook is not None and (not isinstance(webhook, str) or not webhook):
            raise ConfigError("'feedback.webhook' must be a non-empty string")
        if ga is not None and (not isinstance(ga, str) or not ga):
            raise ConfigError("'feedback.ga' must be a non-empty string")

    branch = raw.get("branch", None)
    if branch is not None:
        if not isinstance(branch, str) or not branch:
            raise ConfigError("'branch' must be a non-empty string")

    lint_ignore = raw.get("lint_ignore", [])
    if not isinstance(lint_ignore, list):
        raise ConfigError("'lint_ignore' must be a list of strings")
    for item in lint_ignore:
        if not isinstance(item, str) or not re.match(r"^SEO\d+$", item):
            raise ConfigError(
                f"invalid lint_ignore entry {item!r}; "
                f"must match pattern SEO followed by digits (e.g. 'SEO007')"
            )

    min_coverage = raw.get("min_coverage", None)
    if min_coverage is not None:
        if not isinstance(min_coverage, int) or isinstance(min_coverage, bool):
            raise ConfigError("'min_coverage' must be an integer between 0 and 100")
        if min_coverage < 0 or min_coverage > 100:
            raise ConfigError("'min_coverage' must be an integer between 0 and 100")

    branding = raw.get("branding", None)
    if branding is not None:
        if not isinstance(branding, dict):
            raise ConfigError("'branding' must be an object")
        for key in ("tagline", "cta_text", "cta_link", "logo",
                     "secondary_cta_text", "secondary_cta_link"):
            if key in branding and (not isinstance(branding[key], str) or not branding[key]):
                raise ConfigError(f"'branding.{key}' must be a non-empty string")
        features = branding.get("features", None)
        if features is not None:
            if not isinstance(features, list):
                raise ConfigError("'branding.features' must be a list")
            for i, feat in enumerate(features):
                if not isinstance(feat, dict):
                    raise ConfigError(f"'branding.features[{i}]' must be an object")
                if "title" not in feat or not isinstance(feat["title"], str) or not feat["title"]:
                    raise ConfigError(
                        f"'branding.features[{i}].title' is required "
                        f"and must be a non-empty string"
                    )
                if ("description" not in feat
                        or not isinstance(feat["description"], str)
                        or not feat["description"]):
                    raise ConfigError(
                        f"'branding.features[{i}].description' is required "
                        f"and must be a non-empty string"
                    )

    auto_detect = raw.get("auto_detect", None)
    if auto_detect is not None:
        if not isinstance(auto_detect, dict):
            raise ConfigError("'auto_detect' must be an object")
        valid_keys = {"steps", "api_entries"}
        for key, val in auto_detect.items():
            if key not in valid_keys:
                raise ConfigError(
                    f"invalid auto_detect key {key!r}; "
                    f"must be one of: {', '.join(sorted(valid_keys))}"
                )
            if not isinstance(val, bool) or isinstance(val, int) and not isinstance(val, bool):
                raise ConfigError(
                    f"'auto_detect.{key}' must be a boolean"
                )

    return {
        "language": language,
        "source": source,
        "docs": docs,
        "output": output,
        "theme": theme,
        "deploy": deploy,
        "directives": directives,
        "repo": repo,
        "base_url": base_url,
        "lang": lang,
        "author": author,
        "description": description,
        "twitter": twitter,
        "search": search,
        "search_engine": search_engine,
        "feedback": feedback,
        "branch": branch,
        "lint_ignore": lint_ignore,
        "min_coverage": min_coverage,
        "branding": branding,
        "auto_detect": auto_detect,
    }

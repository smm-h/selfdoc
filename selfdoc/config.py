"""Config loader for selfdoc.json."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

class FieldType(Enum):
    """Supported field types for config validation."""

    STR = "str"
    BOOL = "bool"
    INT = "int"
    DICT = "dict"
    LIST = "list"


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """Specification for a single configuration field."""

    name: str
    type: FieldType
    required: bool = False
    default: Any = None
    default_factory: Callable[[], Any] | None = None
    choices: tuple[Any, ...] | None = None
    pattern: str | None = None
    description: str = ""
    non_empty: bool = True
    min_val: int | None = None
    max_val: int | None = None
    min_length: int | None = None
    children: tuple[FieldSpec, ...] | None = None
    item_spec: FieldSpec | None = None
    strict_keys: bool = False
    transform: Callable[[Any], Any] | None = None
    internal: bool = False

VALID_DEPLOY_PROVIDERS = ("cloudflare-pages", "github-pages")
VALID_SEARCH_ENGINES = ("builtin", "fuse", "minisearch")

_S = FieldType.STR
_B = FieldType.BOOL
_I = FieldType.INT
_D = FieldType.DICT
_L = FieldType.LIST

CONFIG_SCHEMA: tuple[FieldSpec, ...] = (
    # --- required fields ---
    FieldSpec(
        name="source",
        type=_L,
        required=True,
        min_length=1,
        item_spec=FieldSpec(
            name="<item>",
            type=_D,
            strict_keys=True,
            children=(
                FieldSpec(
                    name="path",
                    type=_S,
                    required=True,
                    description="Source directory or file path.",
                ),
                FieldSpec(
                    name="language",
                    type=_S,
                    required=True,
                    description="Programming language for this source entry.",
                ),
            ),
            description="Source entry with path and language.",
        ),
        description="List of source entries to extract documentation from.",
    ),
    FieldSpec(
        name="base_url",
        type=_S,
        required=True,
        transform=lambda s: s.rstrip("/"),
        description="Base URL of the generated site, used for canonical links and SEO.",
    ),
    # --- optional string fields ---
    FieldSpec(
        name="version",
        type=_S,
        required=False,
        default=None,
        pattern=r"^\d+\.\d+\.\d+",
        description="Project version. When present, used by deploy instead of reading from pyproject.toml/package.json.",
    ),
    FieldSpec(
        name="docs",
        type=_S,
        default="docs/",
        description="Directory containing Markdown documentation templates.",
    ),
    FieldSpec(
        name="output",
        type=_S,
        default="docs/_build/",
        description="Output directory for generated HTML files.",
    ),
    FieldSpec(
        name="theme",
        type=_S,
        default="minimal",
        description="Visual theme for the generated site.",
    ),
    FieldSpec(
        name="repo",
        type=_S,
        default=None,
        non_empty=True,
        description="GitHub repository URL shown in the site header.",
    ),
    FieldSpec(
        name="lang",
        type=_S,
        default=None,
        pattern=r"^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$",
        description="BCP 47 language tag for the site content (e.g. 'en', 'pt-BR').",
    ),
    FieldSpec(
        name="description",
        type=_S,
        default=None,
        description="Short description of the project, used in meta tags and SEO.",
    ),
    FieldSpec(
        name="branch",
        type=_S,
        default=None,
        description="Git branch used for source links in the generated site.",
    ),
    FieldSpec(
        name="search",
        type=_S,
        default=None,
        choices=("icon", "bar", "hidden"),
        description="Search UI mode: icon button, full bar, or hidden.",
    ),
    FieldSpec(
        name="search_engine",
        type=_S,
        default=None,
        choices=("builtin", "fuse", "minisearch"),
        description="Client-side search engine implementation to use.",
    ),
    FieldSpec(
        name="code_icons",
        type=_S,
        default="colorful",
        choices=("colorful", "monochrome", "none"),
        description="Style of language icons shown on code blocks.",
    ),
    # --- optional boolean fields ---
    FieldSpec(
        name="line_numbers",
        type=_B,
        default=False,
        description="Show line numbers in code blocks.",
    ),
    FieldSpec(
        name="run_button",
        type=_B,
        default=False,
        description="Show a run button on code blocks for supported languages.",
    ),
    FieldSpec(
        name="page_nav",
        type=_B,
        default=True,
        description="Show previous/next navigation links between pages.",
    ),
    FieldSpec(
        name="page_progress",
        type=_B,
        default=True,
        description="Show a reading progress bar at the top of each page.",
    ),
    FieldSpec(
        name="glossary",
        type=_B,
        default=True,
        description="Auto-generate a glossary page from dfn terms.",
    ),
    # --- optional int field ---
    FieldSpec(
        name="feed_max_entries",
        type=_I,
        default=None,
        min_val=1,
        description="Maximum number of entries in the Atom feed, sorted by most recent.",
    ),
    # --- optional list fields ---
    FieldSpec(
        name="lint_ignore",
        type=_L,
        default_factory=list,
        non_empty=False,
        item_spec=FieldSpec(
            name="<item>",
            type=_S,
            pattern=r"^[A-Z]+\d+$",
            description="Lint rule ID to ignore (e.g. SEO007, STALE001, VER002).",
        ),
        description="List of lint rule IDs to suppress (e.g. 'SEO007', 'STALE001').",
    ),
    FieldSpec(
        name="root_files",
        type=_L,
        default_factory=list,
        non_empty=False,
        item_spec=FieldSpec(
            name="<item>",
            type=_S,
            description="Underscore-prefixed template path in docs/.",
        ),
        description="List of underscore-prefixed template paths in docs/ for root file generation.",
    ),
    FieldSpec(
        name="redirects",
        type=_L,
        required=False,
        default_factory=list,
        non_empty=False,
        item_spec=FieldSpec(
            name="<item>",
            type=_D,
            strict_keys=True,
            children=(
                FieldSpec(
                    name="from",
                    type=_S,
                    required=True,
                    description="Old page slug to redirect from.",
                ),
                FieldSpec(
                    name="to",
                    type=_S,
                    required=True,
                    description="New page slug to redirect to.",
                ),
            ),
            description="Redirect entry mapping old slug to new slug.",
        ),
        description="Page-level redirects expanded across all locale/version combos.",
    ),
    # --- optional dict fields ---
    FieldSpec(
        name="deploy",
        type=_D,
        default=None,
        strict_keys=False,
        children=(
            FieldSpec(
                name="provider",
                type=_S,
                required=True,
                choices=("cloudflare-pages", "github-pages"),
                description="Hosting provider for deployment.",
            ),
            FieldSpec(
                name="project",
                type=_S,
                required=False,
                description="Project name on the hosting provider (required for cloudflare-pages).",
            ),
        ),
        description="Deployment configuration for publishing the generated site.",
    ),
    FieldSpec(
        name="directives",
        type=_D,
        default_factory=dict,
        strict_keys=False,
        description="Custom directive mappings from directive name to source file path.",
    ),
    FieldSpec(
        name="author",
        type=_D,
        default=None,
        strict_keys=False,
        children=(
            FieldSpec(
                name="name",
                type=_S,
                required=True,
                description="Author display name.",
            ),
            FieldSpec(
                name="type",
                type=_S,
                required=False,
                choices=("Person", "Organization"),
                description="Schema.org author type.",
            ),
            FieldSpec(
                name="twitter",
                type=_S,
                required=False,
                pattern=r"^@",
                description="Author Twitter handle (must start with @).",
            ),
        ),
        description="Author information for meta tags and structured data.",
    ),
    FieldSpec(
        name="twitter",
        type=_S,
        default=None,
        pattern=r"^@",
        internal=True,
        description="Top-level Twitter handle, merged into author in post-validation.",
    ),
    FieldSpec(
        name="feedback",
        type=_D,
        default=None,
        strict_keys=False,
        children=(
            FieldSpec(
                name="webhook",
                type=_S,
                required=False,
                description="Webhook URL for collecting user feedback.",
            ),
            FieldSpec(
                name="ga",
                type=_S,
                required=False,
                description="Google Analytics measurement ID.",
            ),
        ),
        description="Feedback collection configuration (at least one of webhook or ga required).",
    ),
    FieldSpec(
        name="branding",
        type=_D,
        default=None,
        strict_keys=False,
        children=(
            FieldSpec(
                name="tagline",
                type=_S,
                required=False,
                description="Short tagline displayed on the landing page.",
            ),
            FieldSpec(
                name="cta_text",
                type=_S,
                required=False,
                description="Primary call-to-action button text.",
            ),
            FieldSpec(
                name="cta_link",
                type=_S,
                required=False,
                description="Primary call-to-action button URL.",
            ),
            FieldSpec(
                name="logo",
                type=_S,
                required=False,
                description="Path to a logo image file.",
            ),
            FieldSpec(
                name="secondary_cta_text",
                type=_S,
                required=False,
                description="Secondary call-to-action button text.",
            ),
            FieldSpec(
                name="secondary_cta_link",
                type=_S,
                required=False,
                description="Secondary call-to-action button URL.",
            ),
            FieldSpec(
                name="features",
                type=_L,
                required=False,
                non_empty=False,
                item_spec=FieldSpec(
                    name="<item>",
                    type=_D,
                    children=(
                        FieldSpec(
                            name="title",
                            type=_S,
                            required=True,
                            description="Feature card title.",
                        ),
                        FieldSpec(
                            name="description",
                            type=_S,
                            required=True,
                            description="Feature card description.",
                        ),
                    ),
                    description="Feature card object.",
                ),
                description="List of feature cards shown on the landing page.",
            ),
        ),
        description="Landing page branding and call-to-action configuration.",
    ),
    FieldSpec(
        name="auto_detect",
        type=_D,
        default=None,
        strict_keys=True,
        children=(
            FieldSpec(
                name="steps",
                type=_B,
                required=False,
                description="Auto-detect step guide blocks in documentation.",
            ),
            FieldSpec(
                name="api_entries",
                type=_B,
                required=False,
                description="Auto-detect API entry cards in documentation.",
            ),
        ),
        description="Automatic content detection settings for step guides and API entries.",
    ),
    FieldSpec(
        name="gen",
        type=_D,
        default=None,
        strict_keys=True,
        children=(
            FieldSpec(
                name="exclude",
                type=_L,
                required=False,
                non_empty=False,
                item_spec=FieldSpec(
                    name="<item>",
                    type=_S,
                    description="Glob pattern to exclude from generation.",
                ),
                description="List of glob patterns to exclude from doc generation.",
            ),
        ),
        description="Configuration for the gen command.",
    ),
    FieldSpec(
        name="gen_data",
        type=_D,
        default=None,
        strict_keys=True,
        children=(
            FieldSpec(
                name="scripts",
                type=_L,
                required=False,
                non_empty=False,
                item_spec=FieldSpec(
                    name="<item>",
                    type=_D,
                    children=(
                        FieldSpec(
                            name="command",
                            type=_S,
                            required=True,
                            description="Shell command to execute for data generation.",
                        ),
                        FieldSpec(
                            name="output",
                            type=_S,
                            required=True,
                            description="Output file path relative to docs/ for generated data.",
                        ),
                        FieldSpec(
                            name="mounts",
                            type=_L,
                            required=True,
                            non_empty=False,
                            item_spec=FieldSpec(
                                name="<item>",
                                type=_S,
                                description="File path to mount into the script environment.",
                            ),
                            description="List of files to mount into the script environment.",
                        ),
                    ),
                    description="Data generation script configuration.",
                ),
                description="List of data generation scripts to run before build.",
            ),
        ),
        description="Configuration for the gen-data command.",
    ),
    FieldSpec(
        name="schema_types",
        type=_D,
        default=None,
        strict_keys=False,
        description="Mapping from page type to schema.org @type (e.g. guide -> TechArticle).",
    ),
    # --- multi-version / multi-locale / unified fields ---
    FieldSpec(
        name="versions",
        type=_L,
        default=None,
        non_empty=False,
        item_spec=FieldSpec(
            name="<item>",
            type=_D,
            strict_keys=True,
            children=(
                FieldSpec(
                    name="version",
                    type=_S,
                    required=True,
                    description="Version string (e.g. '1.0', 'latest').",
                ),
                FieldSpec(
                    name="indexed",
                    type=_B,
                    required=True,
                    description="Whether this version is included in search indexes.",
                ),
                FieldSpec(
                    name="projects",
                    type=_D,
                    required=False,
                    strict_keys=False,
                    description="Per-project version overrides (project name -> version string).",
                ),
            ),
            description="Version entry.",
        ),
        description="List of documentation versions to build.",
    ),
    FieldSpec(
        name="locales",
        type=_L,
        default=None,
        non_empty=False,
        item_spec=FieldSpec(
            name="<item>",
            type=_D,
            strict_keys=False,
            children=(
                FieldSpec(
                    name="code",
                    type=_S,
                    required=True,
                    pattern=r"^[a-z]{2,3}(-[A-Z][a-z]{3})?(-[A-Z]{2})?$",
                    description="BCP 47 locale code (e.g. 'en', 'pt-BR', 'zh-Hans-CN').",
                ),
                FieldSpec(
                    name="label",
                    type=_S,
                    required=True,
                    description="Human-readable locale label (e.g. 'English').",
                ),
                FieldSpec(
                    name="default",
                    type=_B,
                    required=False,
                    description="Whether this locale is the default.",
                ),
                FieldSpec(
                    name="rtl",
                    type=_B,
                    required=False,
                    description="Whether this locale uses right-to-left text direction.",
                ),
            ),
            description="Locale entry.",
        ),
        description="List of locales for multi-language documentation.",
    ),
    FieldSpec(
        name="unified",
        type=_D,
        default=None,
        strict_keys=True,
        children=(
            FieldSpec(
                name="projects",
                type=_L,
                required=True,
                min_length=1,
                item_spec=FieldSpec(
                    name="<item>",
                    type=_D,
                    strict_keys=True,
                    children=(
                        FieldSpec(
                            name="path",
                            type=_S,
                            required=True,
                            description="Path to the project directory.",
                        ),
                        FieldSpec(
                            name="slug",
                            type=_S,
                            required=False,
                            description="URL slug for the project (defaults to path basename).",
                        ),
                        FieldSpec(
                            name="nav_title",
                            type=_S,
                            required=False,
                            description="Display title in the navigation.",
                        ),
                    ),
                    description="Unified project entry.",
                ),
                description="List of projects to unify into a single documentation site.",
            ),
            FieldSpec(
                name="exclude",
                type=_L,
                required=False,
                non_empty=False,
                item_spec=FieldSpec(
                    name="<item>",
                    type=_S,
                    description="Glob pattern to exclude from unified build.",
                ),
                description="Glob patterns to exclude from the unified build.",
            ),
        ),
        description="Configuration for unified multi-project documentation.",
    ),
    FieldSpec(
        name="posts",
        type=_D,
        description="Blog post configuration.",
        children=(
            FieldSpec(name="dir", type=_S, default=".selfdoc/posts/",
                      description="Directory containing post markdown files."),
            FieldSpec(name="listing_path", type=_S, default="posts",
                      description="URL path segment for the post listing page."),
        ),
    ),
    FieldSpec(
        name="topology",
        type=_D,
        description="Deployment topology for multi-project unified sites.",
    ),
    FieldSpec(
        name="assembly",
        type=_D,
        description="Assembly configuration for unified site deployment.",
        children=(
            FieldSpec(name="repo", type=_S,
                      description="GitHub repository for the assembly (e.g., owner/repo)."),
        ),
    ),
)


class ConfigError(Exception):
    """Raised when selfdoc.json is present but invalid."""


# Sentinel for "no value provided" (distinct from None, which is a valid default)
_MISSING = object()


def _validate_field(spec: FieldSpec, value, path: str) -> Any:
    """Validate a single config value against its FieldSpec.

    Returns the validated (and possibly transformed) value.
    Raises ConfigError on validation failure.
    """
    # Handle missing values
    if value is _MISSING or value is None:
        is_absent = value is _MISSING
        if is_absent and spec.required:
            raise ConfigError(f"missing required field '{path}'")
        if is_absent:
            if spec.default_factory is not None:
                return spec.default_factory()
            return spec.default
        # value is None (explicitly set in JSON) -- for DICT/LIST types that
        # are not required, treat explicit null the same as absent
        if not spec.required:
            if spec.type in (FieldType.DICT, FieldType.LIST):
                if spec.default_factory is not None:
                    return spec.default_factory()
                return spec.default
            return spec.default if spec.default is not None else None
        raise ConfigError(f"missing required field '{path}'")

    # Type checking and validation by FieldType
    if spec.type == FieldType.STR:
        if not isinstance(value, str):
            if spec.choices:
                raise ConfigError(
                    f"invalid {path} value {value!r}; "
                    f"must be one of: {', '.join(spec.choices)}"
                )
            raise ConfigError(f"'{path}' must be a string")
        if spec.non_empty and not value:
            raise ConfigError(f"'{path}' must be a non-empty string")
        if spec.choices and value not in spec.choices:
            raise ConfigError(
                f"invalid {path} value {value!r}; "
                f"must be one of: {', '.join(spec.choices)}"
            )
        if spec.pattern and not re.match(spec.pattern, value):
            raise ConfigError(
                f"invalid {path} {value!r}; must match pattern {spec.pattern}"
            )
        if spec.transform:
            value = spec.transform(value)
        return value

    if spec.type == FieldType.BOOL:
        if not isinstance(value, bool):
            raise ConfigError(f"'{path}' must be a boolean")
        return value

    if spec.type == FieldType.INT:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ConfigError(
                f"'{path}' must be an integer"
                + (f" between {spec.min_val} and {spec.max_val}"
                   if spec.min_val is not None and spec.max_val is not None
                   else "")
            )
        if spec.min_val is not None and value < spec.min_val:
            raise ConfigError(
                f"'{path}' must be an integer between {spec.min_val} and {spec.max_val}"
            )
        if spec.max_val is not None and value > spec.max_val:
            raise ConfigError(
                f"'{path}' must be an integer between {spec.min_val} and {spec.max_val}"
            )
        return value

    if spec.type == FieldType.LIST:
        if not isinstance(value, list):
            if spec.min_length and spec.min_length > 0:
                raise ConfigError(f"'{path}' must be a non-empty list")
            raise ConfigError(f"'{path}' must be a list")
        if spec.min_length is not None and len(value) < spec.min_length:
            raise ConfigError(f"'{path}' must be a non-empty list")
        if spec.non_empty and not value and spec.min_length and spec.min_length > 0:
            raise ConfigError(f"'{path}' must be a non-empty list")
        if spec.item_spec:
            for i, item in enumerate(value):
                value[i] = _validate_field(spec.item_spec, item, f"{path}[{i}]")
        return value

    if spec.type == FieldType.DICT:
        if not isinstance(value, dict):
            raise ConfigError(f"'{path}' must be an object")

        # No children = open dict (e.g. directives), just check it's a dict
        if not spec.children:
            return value

        # Check for unknown keys in strict mode
        if spec.strict_keys:
            known_keys = {child.name for child in spec.children}
            for key in value:
                if key not in known_keys:
                    raise ConfigError(
                        f"invalid {spec.name} key {key!r}; "
                        f"must be one of: {', '.join(sorted(known_keys))}"
                    )

        # Validate children that are present or required
        for child in spec.children:
            child_path = f"{path}.{child.name}"
            if child.name in value:
                value[child.name] = _validate_field(
                    child, value[child.name], child_path,
                )
            elif child.required:
                raise ConfigError(f"'{child_path}' is required")
            # If not required and not present, leave the dict as-is
            # (don't inject defaults for sub-dict fields)

        return value

    # Unreachable for valid FieldType values
    raise ConfigError(f"unknown field type {spec.type!r} for '{path}'")


def _post_validate(config: dict) -> dict:
    """Apply cross-field validation rules after individual field validation.

    Handles twitter merge, feedback at-least-one, and deploy.project conditional.
    Returns the modified config dict.
    """
    # Twitter merge: author.twitter takes precedence over top-level twitter
    twitter = None
    author = config.get("author")
    if author and author.get("twitter"):
        twitter = author["twitter"]
    elif config.get("twitter"):
        twitter = config["twitter"]
    config["twitter"] = twitter

    # Feedback at-least-one: if feedback is present, at least one of
    # webhook or ga must be set
    feedback = config.get("feedback")
    if feedback is not None:
        webhook = feedback.get("webhook")
        ga = feedback.get("ga")
        if webhook is None and ga is None:
            raise ConfigError(
                "'feedback' must contain at least one of 'webhook' or 'ga'"
            )

    # Deploy.project conditional: cloudflare-pages requires project
    deploy = config.get("deploy")
    if deploy is not None:
        if deploy.get("provider") == "cloudflare-pages" and not deploy.get("project"):
            raise ConfigError(
                "'deploy.project' is required for cloudflare-pages provider"
            )

    # Locales validation: unique codes, at most one default
    locales = config.get("locales")
    if locales is not None:
        codes = [loc["code"] for loc in locales]
        seen_codes: set[str] = set()
        for code in codes:
            if code in seen_codes:
                raise ConfigError(
                    f"duplicate locale code {code!r} in 'locales'"
                )
            seen_codes.add(code)
        defaults = [loc for loc in locales if loc.get("default") is True]
        if len(defaults) > 1:
            raise ConfigError(
                "at most one locale may have 'default: true', "
                f"found {len(defaults)}"
            )

    # Versions validation: unique version strings
    versions = config.get("versions")
    if versions is not None:
        seen_versions: set[str] = set()
        for entry in versions:
            v = entry["version"]
            if v in seen_versions:
                raise ConfigError(
                    f"duplicate version string {v!r} in 'versions'"
                )
            seen_versions.add(v)

    # Unified validation: unique project slugs (explicit or derived from path)
    unified = config.get("unified")
    if unified is not None:
        seen_slugs: set[str] = set()
        for proj in unified["projects"]:
            slug = proj.get("slug") or os.path.basename(proj["path"].rstrip("/"))
            if slug in seen_slugs:
                raise ConfigError(
                    f"duplicate project slug {slug!r} in 'unified.projects'"
                )
            seen_slugs.add(slug)

    return config


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

    # Migration error: top-level "language" is no longer supported
    if "language" in raw:
        raise ConfigError(
            "Top-level 'language' field is no longer supported. "
            'Move language into each source entry: '
            '"source": [{"path": "src/", "language": "python"}]'
        )

    # Check for unknown root-level keys
    known_keys = {spec.name for spec in CONFIG_SCHEMA}
    for key in raw:
        if key not in known_keys:
            raise ConfigError(f"unknown config key {key!r}")

    # Migration error: source items must be dicts, not strings
    raw_source = raw.get("source")
    if isinstance(raw_source, list):
        for i, item in enumerate(raw_source):
            if isinstance(item, str):
                raise ConfigError(
                    f"source[{i}] is a plain string ({item!r}). "
                    "Source entries must be objects with 'path' and 'language': "
                    '{"path": "src/", "language": "python"}'
                )

    # Validate each field against its schema spec
    result = {}
    for spec in CONFIG_SCHEMA:
        raw_value = raw.get(spec.name, _MISSING)
        validated = _validate_field(spec, raw_value, spec.name)
        result[spec.name] = validated

    return _post_validate(result)

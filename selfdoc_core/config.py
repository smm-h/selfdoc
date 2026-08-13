"""Config loader for selfdoc.json."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from selfdoc_core.lints import LintSuppressionError, validate_lint_codes

class FieldType(Enum):
    """Supported field types for config validation."""

    STR = "str"
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
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
    # For STR: a literal substring the value must contain.  Says what a
    # regex would say, but the rejection message names the missing text
    # instead of printing a pattern the reader has to decode.
    must_contain: str | None = None
    description: str = ""
    non_empty: bool = True
    min_val: int | None = None
    max_val: int | None = None
    min_length: int | None = None
    children: tuple[FieldSpec, ...] | None = None
    # For LIST: the spec every element is validated against.  For a
    # childless DICT (open key set), the spec every VALUE is validated
    # against -- the dict analogue of the list case.
    item_spec: FieldSpec | None = None
    strict_keys: bool = False
    # For a childless DICT: the regex every KEY must match.  A closed
    # ``children`` tuple cannot express an open-but-well-formed key set
    # (e.g. fence language names), so the keys are constrained by shape.
    key_pattern: str | None = None
    transform: Callable[[Any], Any] | None = None
    internal: bool = False

VALID_DEPLOY_PROVIDERS = ("cloudflare-pages", "github-pages")
# The engine that answers a site's search UI.  One member today, and the
# tuple is still the enumeration a config is checked against: the key is the
# extension point, so a second engine is a member added here rather than a
# new mechanism.
VALID_SEARCH_ENGINES = ("pagefind",)

_S = FieldType.STR
_B = FieldType.BOOL
_I = FieldType.INT
_F = FieldType.FLOAT
_D = FieldType.DICT
_L = FieldType.LIST

CONFIG_SCHEMA: tuple[FieldSpec, ...] = (
    # --- required fields ---
    # 'source' is optional: a codeless project (a portfolio or personal site
    # that is nothing but markdown pages) has no code to extract from and
    # declares no source entries.  Absent normalizes to [] rather than None so
    # every consumer can iterate it unconditionally.  Directives that need
    # source code raise instead of rendering a placeholder note -- see
    # selfdoc_core.resolver.Resolver and selfdoc_core.content.
    FieldSpec(
        name="source",
        type=_L,
        required=False,
        non_empty=False,
        default_factory=list,
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
    # Absent keeps the convention every standalone repo relies on: the
    # project root's CHANGELOG.md becomes the changelog page.  That
    # convention reads "the root changelog is this project's changelog",
    # which is false in a workspace whose root file rolls up several
    # independently versioned projects -- and nothing in the build can tell
    # which of them a given site documents.  So the answer is declared, not
    # guessed: name the file, and a name that does not exist is an error
    # rather than a silently missing page.
    FieldSpec(
        name="changelog",
        type=_S,
        required=False,
        default=None,
        description="Path to the changelog document published as the site's changelog page, relative to the project root. Absent means the project root's CHANGELOG.md is used if it exists; declare it when that file is not this site's changelog.",
    ),
    FieldSpec(
        name="theme",
        type=_S,
        default="minimal",
        description=(
            "Visual theme for the generated site. One of the themes selfdoc "
            "ships -- 'minimal', 'clean' or 'tinymoon'. A build's --theme "
            "flag overrides this for that build only, without writing "
            "anything back here."
        ),
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
        name="name",
        type=_S,
        default=None,
        description=(
            "Explicit project name. Used as the single source of truth for "
            "the manifest name and the auto-generated API reference index "
            "description. When absent, the name is derived heuristically "
            "(single-source basename or project directory basename)."
        ),
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
        required=True,
        choices=VALID_SEARCH_ENGINES,
        description=(
            "Search engine that answers this site's search UI. Required and "
            "never inferred: every site builds a search UI, so the engine "
            "behind it is declared, not defaulted."
        ),
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
    # --- optional float field ---
    FieldSpec(
        name="coverage_threshold",
        type=_F,
        default=1.0,
        min_val=0.0,
        max_val=1.0,
        description=(
            "Minimum fraction of public symbols that must be documented "
            "for selfdoc check to pass (0.0-1.0). Default 1.0 requires "
            "100% coverage."
        ),
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
            description="Warning-severity lint rule ID to ignore (e.g. SEO007, SEO008, XREF001).",
        ),
        description="List of warning-severity lint rule IDs to suppress (e.g. 'SEO007', 'SEO008'). Error-severity codes cannot be suppressed and are refused at load.",
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
        name="examples",
        type=_D,
        default=None,
        # Keys are fenced-block language names, an open set (any language may
        # appear after a fence), so they are constrained by shape rather than
        # by a closed children tuple: a malformed key is rejected, an
        # unanticipated-but-well-formed language is not.
        key_pattern=r"^[a-z][a-z0-9+#._-]*$",
        item_spec=FieldSpec(
            name="<language>",
            type=_S,
            must_contain="{file}",
            description=(
                "Validator command template; '{file}' is replaced with the"
                " path of the assembled snippet."
            ),
        ),
        description=(
            "Validator command templates keyed by code-block language, used by"
            " 'selfdoc check' to execute fenced blocks marked 'validate'."
            " Each template must contain the '{file}' placeholder. Absent"
            " means example validation is off."
        ),
    ),
    # The one identity a site's structured data names.  Required, because
    # every page carries structured data and an author is one of the facts it
    # states: an absent block used to mint an Organization named after the
    # project directory, which stated a legal entity nobody had declared.
    # There is no schema.org type to choose -- a site has one author and the
    # emitters render it as a Person.
    FieldSpec(
        name="author",
        type=_D,
        required=True,
        strict_keys=True,
        children=(
            FieldSpec(
                name="name",
                type=_S,
                required=True,
                description="The author's display name, as every page's structured data states it.",
            ),
            FieldSpec(
                name="url",
                type=_S,
                required=True,
                description="The author's canonical URL -- the address that identifies them.",
            ),
            FieldSpec(
                name="same_as",
                type=_L,
                required=False,
                non_empty=False,
                item_spec=FieldSpec(
                    name="<item>",
                    type=_S,
                    description="An external URL naming the same author (a profile, a directory entry).",
                ),
                description=(
                    "External identity URLs, emitted as the Person's sameAs."
                ),
            ),
        ),
        description=(
            "The site's author: one Person, named in every page's structured"
            " data. Required -- there is no inferred author."
        ),
    ),
    FieldSpec(
        name="twitter",
        type=_S,
        default=None,
        pattern=r"^@",
        description=(
            "Twitter/X handle (starts with @) for the twitter:site meta tag."
        ),
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
        name="unversioned",
        type=_B,
        default=None,
        description=(
            "Declares that this project has no public version -- a personal "
            "site or portfolio that publishes no artifact. It replaces the "
            "'versions' array (declaring both is an error) and is refused "
            "for a project that declares 'source', because code is the "
            "thing that gets released and therefore carries a version. An "
            "unversioned project's pages show no version badge, offer no "
            "version search filter and no version picker."
        ),
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
            FieldSpec(name="repo", type=_S,
                      description="GitHub repository for archiving resolved post content (e.g., owner/posts)."),
        ),
    ),
    FieldSpec(
        name="topology",
        type=_D,
        description="Deployment topology for multi-project unified sites.",
        children=(
            FieldSpec(name="slug", type=_S, required=False,
                      description="This project's URL path segment."),
            FieldSpec(name="docs_base", type=_S, required=False,
                      transform=lambda s: s.rstrip("/"),
                      description="Base URL for docs (e.g., 'https://docs.smmh.dev')."),
            FieldSpec(name="posts_base", type=_S, required=False,
                      transform=lambda s: s.rstrip("/"),
                      description="Canonical base URL under which blog posts and the unified blog index are served. This is a path on the docs site, not a separate host (e.g., 'https://docs.smmh.dev/blog')."),
            FieldSpec(name="legacy_blog_host", type=_S, required=False,
                      description="Hostname of a retired blog subdomain (e.g., 'blog.smmh.dev'). When set, every request arriving on that host is 301'd by the generated assembly worker onto '<docs_base>/blog' -- the canonical blog URL the worker derives from topology.docs_base, not from posts_base. Omit when no such subdomain exists."),
            FieldSpec(name="projects", type=_D, required=False, strict_keys=False,
                      description="Maps other project slugs to their base URLs for cross-linking."),
        ),
    ),
    FieldSpec(
        name="assembly",
        type=_D,
        description="Assembly configuration for unified site deployment.",
        children=(
            FieldSpec(name="repo", type=_S,
                      description="GitHub repository for the assembly (e.g., owner/repo)."),
            FieldSpec(name="pages_project", type=_S,
                      description="Cloudflare Pages project the assembled site deploys to. Used by both 'assembly init' (project creation) and the generated deploy workflow, so the two can never diverge. No default."),
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
        if spec.must_contain and spec.must_contain not in value:
            raise ConfigError(
                f"invalid {path} {value!r}; must contain {spec.must_contain!r}"
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

    if spec.type == FieldType.FLOAT:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ConfigError(
                f"'{path}' must be a number"
                + (f" between {spec.min_val} and {spec.max_val}"
                   if spec.min_val is not None and spec.max_val is not None
                   else "")
            )
        value = float(value)
        if spec.min_val is not None and value < spec.min_val:
            raise ConfigError(
                f"'{path}' must be a number between {spec.min_val} and {spec.max_val}"
            )
        if spec.max_val is not None and value > spec.max_val:
            raise ConfigError(
                f"'{path}' must be a number between {spec.min_val} and {spec.max_val}"
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

        # No children = open key set (e.g. directives, examples).  Keys may
        # still be shape-constrained and values may still carry their own
        # spec; without either this is just a dict check.
        if not spec.children:
            if spec.key_pattern:
                for key in value:
                    if not isinstance(key, str) or not re.match(spec.key_pattern, key):
                        raise ConfigError(
                            f"invalid {spec.name} key {key!r}; "
                            f"must match pattern {spec.key_pattern}"
                        )
            if spec.item_spec:
                for key in list(value):
                    value[key] = _validate_field(
                        spec.item_spec, value[key], f"{path}.{key}",
                    )
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

    Handles feedback at-least-one and the deploy.project conditional.
    Returns the modified config dict.
    """
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

    # A project with no public version says so, and the declaration is what
    # every version-shaped emitter reads: one anonymous version, whose empty
    # string means no badge, no search filter, no picker and no version
    # segment in any address.  Nothing is sniffed and no number is invented.
    if config.get("unversioned") is True:
        if config.get("versions") is not None:
            raise ConfigError(
                "'unversioned': true and 'versions' contradict each other. "
                "A project either has public versions or declares it has "
                "none -- remove one of the two."
            )
        if config.get("source"):
            raise ConfigError(
                "'unversioned': true is refused for a project that declares "
                "'source'. Code is what gets released, so it carries a "
                'version: declare it, e.g. "versions": [{"version": '
                '"0.1.0"}].'
            )
        config["versions"] = [{"version": ""}]

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

    # lint_ignore validation: every suppressed code must be a real one, and
    # must be suppressible at all.  A mistyped code suppresses nothing and an
    # error-severity code may not be silenced, so both are refused at load
    # rather than sitting in the config looking effective.
    lint_ignore = config.get("lint_ignore")
    if lint_ignore:
        try:
            validate_lint_codes(lint_ignore, source="'lint_ignore'")
        except LintSuppressionError as exc:
            raise ConfigError(str(exc)) from exc

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

    return validate_config(raw)


def validate_config(raw):
    """Validate a raw config document and return the resolved config.

    This is what :func:`load_config` runs on the parsed contents of
    selfdoc.json; it is separate so a config assembled in memory goes
    through exactly the same rules as one read from disk.
    """
    if not isinstance(raw, dict):
        raise ConfigError("selfdoc.json must be a JSON object")

    # Migration error: top-level "language" is no longer supported
    if "language" in raw:
        raise ConfigError(
            "Top-level 'language' field is no longer supported. "
            'Move language into each source entry: '
            '"source": [{"path": "src/", "language": "python"}]'
        )

    # Migration error: topology.assembly duplicated assembly.repo
    raw_topology = raw.get("topology")
    if isinstance(raw_topology, dict) and "assembly" in raw_topology:
        raise ConfigError(
            "'topology.assembly' is no longer supported. The assembly repo "
            'has one home: "assembly": {"repo": "owner/repo"}'
        )

    # Check for unknown root-level keys
    known_keys = {spec.name for spec in CONFIG_SCHEMA}
    for key in raw:
        if key not in known_keys:
            raise ConfigError(f"unknown config key {key!r}")

    # The engine is declared, never inferred.  Every selfdoc site builds a
    # search UI -- 'search: "hidden"' still answers Cmd/Ctrl+K -- so the
    # engine behind it has to be named in the config.  The valid set has one
    # member, which is still an explicit declaration: the key is the
    # extension point, and its absence must not silently pick anything.  The
    # generic "missing required field" message would not name the value, so
    # the requirement says it here instead.
    if raw.get("search_engine") is None:
        raise ConfigError(
            "missing required field 'search_engine'. Every site builds a "
            'search UI, so declare the engine that answers it: '
            '"search_engine": "pagefind" (the only valid value).'
        )

    # The author is declared, never inferred.  Every page this build writes
    # carries structured data that states who wrote it; with no block to read,
    # the emitters used to mint an Organization named after the project
    # directory, so a site published a legal entity nobody had declared.  The
    # generic "missing required field" message would not say what to write,
    # so the requirement says it here instead.
    if raw.get("author") is None:
        raise ConfigError(
            "missing required field 'author'. Every page carries structured "
            "data naming who wrote it, and there is no inferred author: "
            '"author": {"name": "Your Name", "url": "https://you.example"} '
            "-- optionally with "
            '"same_as": ["https://github.com/you"] for external profiles.'
        )

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

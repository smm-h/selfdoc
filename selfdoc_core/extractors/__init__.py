"""Language extractor registry and auto-detection."""

from dataclasses import dataclass

from selfdoc_core.extractors.base import StubExtractor
from selfdoc_core.extractors.dart import DartExtractor
from selfdoc_core.extractors.go import GoExtractor
from selfdoc_core.extractors.kotlin import KotlinExtractor
from selfdoc_core.extractors.protocol import LanguageExtractor
from selfdoc_core.extractors.python import PythonExtractor
from selfdoc_core.extractors.sql import SqlExtractor
from selfdoc_core.extractors.svelte import SvelteExtractor
from selfdoc_core.extractors.swift import SwiftExtractor
from selfdoc_core.extractors.typescript import TypeScriptExtractor
from selfdoc_core.extractors.zig import ZigExtractor

EXTRACTORS: dict[str, LanguageExtractor] = {
    "python": PythonExtractor(),
    "go": GoExtractor(),
    "typescript": TypeScriptExtractor(),
    "zig": ZigExtractor(),
    "swift": SwiftExtractor(),
    "kotlin": KotlinExtractor(),
    "dart": DartExtractor(),
    "svelte": SvelteExtractor(),
    "sql": SqlExtractor(),
}


@dataclass(frozen=True, slots=True)
class SourceEntry:
    """A resolved source path with its language and extractor."""

    path: str
    language: str
    extractor: LanguageExtractor


# Ordered list for detection priority.
# Svelte must come BEFORE TypeScript -- a Svelte project also has TypeScript files.
_DETECTION_ORDER: list[LanguageExtractor] = [
    EXTRACTORS["python"],
    EXTRACTORS["go"],
    EXTRACTORS["svelte"],
    EXTRACTORS["typescript"],
    EXTRACTORS["zig"],
    EXTRACTORS["swift"],
    EXTRACTORS["kotlin"],
    EXTRACTORS["dart"],
]


def detect_language(dir_path: str) -> str | None:
    """Auto-detect the project language from marker files in dir_path.

    Tries Python first, then Go, then TypeScript (matching cli.py priority).
    Returns the extractor name or None if no language is detected.
    """
    for extractor in _DETECTION_ORDER:
        if extractor.detect(dir_path):
            return extractor.name
    return None


def detect_languages(dir_path: str) -> list[dict[str, str]]:
    """Detect ALL languages present in a directory.

    Unlike detect_language which returns only the first match,
    this returns all detected languages with their source paths.

    Returns a list of {"path": ..., "language": ...} dicts.
    """
    results: list[dict[str, str]] = []
    for extractor in _DETECTION_ORDER:
        if extractor.detect(dir_path):
            results.append({"path": dir_path, "language": extractor.name})
    return results


def resolve_source_entries(config: dict) -> list[SourceEntry]:
    """Resolve config source entries into SourceEntry objects.

    Each source entry dict has 'path' and 'language' keys.
    The language is looked up in the extractor registry.
    """
    entries = []
    for item in config["source"]:
        language = item["language"]
        extractor = EXTRACTORS.get(language)
        if extractor is None:
            extractor = StubExtractor(language)
        entries.append(
            SourceEntry(path=item["path"], language=language, extractor=extractor)
        )
    return entries


def source_paths(config: dict) -> list[str]:
    """Extract just the source path strings from config."""
    return [item["path"] for item in config["source"]]

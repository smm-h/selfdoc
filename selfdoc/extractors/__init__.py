"""Language extractor registry and auto-detection."""

from selfdoc.extractors.go import GoExtractor
from selfdoc.extractors.protocol import LanguageExtractor
from selfdoc.extractors.python import PythonExtractor
from selfdoc.extractors.typescript import TypeScriptExtractor

EXTRACTORS: dict[str, LanguageExtractor] = {
    "python": PythonExtractor(),
    "go": GoExtractor(),
    "typescript": TypeScriptExtractor(),
    "javascript": TypeScriptExtractor(),  # alias
}

# Ordered list for detection priority (Python, Go, TypeScript).
# Avoids duplicate detection for the javascript alias.
_DETECTION_ORDER: list[LanguageExtractor] = [
    EXTRACTORS["python"],
    EXTRACTORS["go"],
    EXTRACTORS["typescript"],
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

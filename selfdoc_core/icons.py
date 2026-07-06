"""Language icons for code blocks.

Provides small inline SVG icons for common programming languages.
Each icon uses viewBox="0 0 16 16" and is kept under 500 bytes.
Two variants: colorful (brand colors) and monochrome (currentColor).
"""

# Mapping: canonical language name -> (colorful_svg, monochrome_svg)
# Each SVG uses viewBox="0 0 16 16" for consistent sizing.
_ICONS = {
    "python": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<path d="M8 1C5.2 1 5.5 2.2 5.5 2.2V3.5H8v.5H3.5S1 3.7 1 6.5'
        'S3.2 9 3.2 9H4.5V7.7S4.4 5.5 6.7 5.5h2.5S11 5.5 11 3.8V2.3'
        'S11.3 1 8 1zM6.3 2a.6.6 0 110 1.2.6.6 0 010-1.2z" fill="#3776AB"/>'
        '<path d="M8 15c2.8 0 2.5-1.2 2.5-1.2V12.5H8V12h4.5s2.5.3 2.5-2.5'
        'S12.8 7 12.8 7H11.5v1.3s.1 2.2-2.2 2.2H6.8S5 10.5 5 12.2v1.5'
        'S4.7 15 8 15zm1.7-1a.6.6 0 110-1.2.6.6 0 010 1.2z" fill="#FFD43B"/>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<path d="M8 1C5.2 1 5.5 2.2 5.5 2.2V3.5H8v.5H3.5S1 3.7 1 6.5'
        'S3.2 9 3.2 9H4.5V7.7S4.4 5.5 6.7 5.5h2.5S11 5.5 11 3.8V2.3'
        'S11.3 1 8 1zM6.3 2a.6.6 0 110 1.2.6.6 0 010-1.2z" fill="currentColor"/>'
        '<path d="M8 15c2.8 0 2.5-1.2 2.5-1.2V12.5H8V12h4.5s2.5.3 2.5-2.5'
        'S12.8 7 12.8 7H11.5v1.3s.1 2.2-2.2 2.2H6.8S5 10.5 5 12.2v1.5'
        'S4.7 15 8 15zm1.7-1a.6.6 0 110-1.2.6.6 0 010 1.2z" fill="currentColor" opacity="0.5"/>'
        '</svg>',
    ),
    "javascript": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#F7DF1E"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="9" font-weight="700" fill="#000">JS</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="9" font-weight="700" fill="currentColor">JS</text>'
        '</svg>',
    ),
    "typescript": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#3178C6"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="9" font-weight="700" fill="#fff">TS</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="9" font-weight="700" fill="currentColor">TS</text>'
        '</svg>',
    ),
    "go": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#00ADD8"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="9" font-weight="700" fill="#fff">Go</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="9" font-weight="700" fill="currentColor">Go</text>'
        '</svg>',
    ),
    "rust": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#B7410E"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="9" font-weight="700" fill="#fff">Rs</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="9" font-weight="700" fill="currentColor">Rs</text>'
        '</svg>',
    ),
    "java": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#E76F00"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="9" font-weight="700" fill="#fff">Ja</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="9" font-weight="700" fill="currentColor">Ja</text>'
        '</svg>',
    ),
    "bash": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#4EAA25"/>'
        '<text x="8" y="12" text-anchor="middle" font-family="monospace"'
        ' font-size="8" font-weight="700" fill="#fff">$_</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12" text-anchor="middle" font-family="monospace"'
        ' font-size="8" font-weight="700" fill="currentColor">$_</text>'
        '</svg>',
    ),
    "html": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#E34F26"/>'
        '<text x="8" y="12" text-anchor="middle" font-family="monospace"'
        ' font-size="7" font-weight="700" fill="#fff">&lt;/&gt;</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12" text-anchor="middle" font-family="monospace"'
        ' font-size="7" font-weight="700" fill="currentColor">&lt;/&gt;</text>'
        '</svg>',
    ),
    "css": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#1572B6"/>'
        '<text x="8" y="12" text-anchor="middle" font-family="monospace"'
        ' font-size="7" font-weight="700" fill="#fff">{;}</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12" text-anchor="middle" font-family="monospace"'
        ' font-size="7" font-weight="700" fill="currentColor">{;}</text>'
        '</svg>',
    ),
    "sql": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#336791"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="8" font-weight="700" fill="#fff">SQL</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="8" font-weight="700" fill="currentColor">SQL</text>'
        '</svg>',
    ),
    "json": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#555"/>'
        '<text x="8" y="12" text-anchor="middle" font-family="monospace"'
        ' font-size="8" font-weight="700" fill="#fff">{}</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12" text-anchor="middle" font-family="monospace"'
        ' font-size="8" font-weight="700" fill="currentColor">{}</text>'
        '</svg>',
    ),
    "yaml": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#CB171E"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="8" font-weight="700" fill="#fff">YM</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="8" font-weight="700" fill="currentColor">YM</text>'
        '</svg>',
    ),
    "toml": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#9C4121"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="8" font-weight="700" fill="#fff">TM</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="8" font-weight="700" fill="currentColor">TM</text>'
        '</svg>',
    ),
    "markdown": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#333"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="9" font-weight="700" fill="#fff">M</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="9" font-weight="700" fill="currentColor">M</text>'
        '</svg>',
    ),
    "c": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#A8B9CC"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="10" font-weight="700" fill="#fff">C</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="10" font-weight="700" fill="currentColor">C</text>'
        '</svg>',
    ),
    "cpp": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#00599C"/>'
        '<text x="8" y="12" text-anchor="middle" font-family="monospace"'
        ' font-size="7" font-weight="700" fill="#fff">C++</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12" text-anchor="middle" font-family="monospace"'
        ' font-size="7" font-weight="700" fill="currentColor">C++</text>'
        '</svg>',
    ),
    "ruby": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#CC342D"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="8" font-weight="700" fill="#fff">Rb</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="8" font-weight="700" fill="currentColor">Rb</text>'
        '</svg>',
    ),
    "php": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#777BB4"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="8" font-weight="700" fill="#fff">PHP</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="8" font-weight="700" fill="currentColor">PHP</text>'
        '</svg>',
    ),
    "swift": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#F05138"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="8" font-weight="700" fill="#fff">Sw</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="8" font-weight="700" fill="currentColor">Sw</text>'
        '</svg>',
    ),
    "kotlin": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#7F52FF"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="8" font-weight="700" fill="#fff">Kt</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12.5" text-anchor="middle" font-family="monospace"'
        ' font-size="8" font-weight="700" fill="currentColor">Kt</text>'
        '</svg>',
    ),
    "docker": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="#2496ED"/>'
        '<text x="8" y="12" text-anchor="middle" font-family="monospace"'
        ' font-size="6.5" font-weight="700" fill="#fff">Dk</text>'
        '</svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
        '<rect width="16" height="16" rx="2" fill="currentColor" opacity="0.15"/>'
        '<text x="8" y="12" text-anchor="middle" font-family="monospace"'
        ' font-size="6.5" font-weight="700" fill="currentColor">Dk</text>'
        '</svg>',
    ),
}

# Language aliases mapping to canonical names
_ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "sh": "bash",
    "shell": "bash",
    "zsh": "bash",
    "yml": "yaml",
    "c++": "cpp",
    "cxx": "cpp",
    "md": "markdown",
    "dockerfile": "docker",
    "py": "python",
    "rb": "ruby",
    "rs": "rust",
    "kt": "kotlin",
}

VALID_CODE_ICON_MODES = ("colorful", "monochrome", "none")


def get_icon(language, mode="colorful"):
    """Return an inline SVG icon for *language*, or None if unavailable.

    Args:
        language: Language name (case-insensitive). Aliases are resolved
            (e.g. "js" -> "javascript", "sh" -> "bash").
        mode: One of "colorful", "monochrome", or "none".
            "none" always returns None.

    Returns:
        SVG string or None.
    """
    if mode == "none":
        return None

    key = language.lower()
    key = _ALIASES.get(key, key)
    entry = _ICONS.get(key)
    if entry is None:
        return None

    if mode == "monochrome":
        return entry[1]
    return entry[0]

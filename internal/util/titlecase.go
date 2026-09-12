package util

import (
	"strings"
	"unicode"
)

// TitleCase reproduces Python's str.title().
//
// Every cased character that follows an uncased one is title-cased and every
// other cased character is lower-cased, with "cased" meaning the Unicode Cased
// property -- not "alphabetic". An apostrophe is uncased, so "don't" becomes
// "Don'T", and a digit is uncased too, so "a1b" becomes "A1B". Both are the
// documented behavior of the Python method this replaces, not accidents.
//
// The full (multi-character) case mappings Python applies are reproduced from
// the tables below, so a word-initial sharp s becomes "Ss" and a word-initial
// ff ligature becomes "Ff" as they do in Python, rather than staying put the
// way the single-rune unicode.ToTitle would leave them.
func TitleCase(s string) string {
	var b strings.Builder
	b.Grow(len(s))
	previousIsCased := false
	for _, r := range s {
		if previousIsCased {
			if expansion, ok := lowerExpansions[r]; ok {
				b.WriteString(expansion)
			} else {
				b.WriteRune(unicode.ToLower(r))
			}
		} else if expansion, ok := titleExpansions[r]; ok {
			b.WriteString(expansion)
		} else {
			b.WriteRune(unicode.ToTitle(r))
		}
		previousIsCased = isCased(r)
	}
	return b.String()
}

// isCased reports whether r carries the Unicode Cased property, which is what
// Python's str.title() branches on: the uppercase, lowercase and titlecase
// letters plus the Other_Uppercase and Other_Lowercase code points (the
// modifier letters, the Roman numerals, the circled letters).
func isCased(r rune) bool {
	return unicode.IsUpper(r) || unicode.IsLower(r) || unicode.IsTitle(r) ||
		unicode.Is(unicode.Other_Uppercase, r) || unicode.Is(unicode.Other_Lowercase, r)
}

// titleExpansions holds every code point whose Unicode full title-case mapping
// is longer than one character. Generated from the Unicode SpecialCasing data
// Python's str.title() consults; the count is small and stable enough to carry
// as a literal rather than derive at runtime.
var titleExpansions = map[rune]string{
	0x00DF: "Ss",
	0x0149: "ʼN",
	0x01F0: "J̌",
	0x0390: "Ϊ́",
	0x03B0: "Ϋ́",
	0x0587: "Եւ",
	0x1E96: "H̱",
	0x1E97: "T̈",
	0x1E98: "W̊",
	0x1E99: "Y̊",
	0x1E9A: "Aʾ",
	0x1F50: "Υ̓",
	0x1F52: "Υ̓̀",
	0x1F54: "Υ̓́",
	0x1F56: "Υ̓͂",
	0x1FB2: "Ὰͅ",
	0x1FB4: "Άͅ",
	0x1FB6: "Α͂",
	0x1FB7: "ᾼ͂",
	0x1FC2: "Ὴͅ",
	0x1FC4: "Ήͅ",
	0x1FC6: "Η͂",
	0x1FC7: "ῌ͂",
	0x1FD2: "Ϊ̀",
	0x1FD3: "Ϊ́",
	0x1FD6: "Ι͂",
	0x1FD7: "Ϊ͂",
	0x1FE2: "Ϋ̀",
	0x1FE3: "Ϋ́",
	0x1FE4: "Ρ̓",
	0x1FE6: "Υ͂",
	0x1FE7: "Ϋ͂",
	0x1FF2: "Ὼͅ",
	0x1FF4: "Ώͅ",
	0x1FF6: "Ω͂",
	0x1FF7: "ῼ͂",
	0xFB00: "Ff",
	0xFB01: "Fi",
	0xFB02: "Fl",
	0xFB03: "Ffi",
	0xFB04: "Ffl",
	0xFB05: "St",
	0xFB06: "St",
	0xFB13: "Մն",
	0xFB14: "Մե",
	0xFB15: "Մի",
	0xFB16: "Վն",
	0xFB17: "Մխ",
}

// lowerExpansions holds every code point whose Unicode full lowercase mapping
// is longer than one character. There is exactly one: the Latin capital I with
// dot above, which lowercases to "i" plus a combining dot.
var lowerExpansions = map[rune]string{
	0x0130: "i̇",
}

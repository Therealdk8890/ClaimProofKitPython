# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: Apache-2.0

"""Shared text primitives that must byte-match Swift's semantics.

Every helper here exists because a naive Python equivalent demonstrably
diverges from the Swift reference (verified by differential probes):

- ``swift_lower``: Python ``str.lower()`` applies the Unicode Final_Sigma
  contextual rule (``"ΑΣ".lower() == "ας"``); Swift ``lowercased()`` maps
  Σ→σ unconditionally. Fingerprints hash lowercased text, so this must match.
- ``split_words`` / ``split_letter_runs``: Swift splits on grapheme clusters
  using ``Character.isLetter``/``.isNumber`` (Alphabetic incl. Nl; a cluster
  like e+◌́ is one letter). Python evaluates per code point, so input is
  NFC-normalized first (composing most marks) and Nl is treated as a letter.
  Swift ``Set<String>`` term comparison uses canonical equivalence, which the
  NFC normalization also reproduces.
- ``swift_trim_whitespace``: Python ``str.strip()`` strips the information
  separators U+001C–U+001F (``isspace() == True``); Swift's
  ``CharacterSet.whitespacesAndNewlines`` does not.
"""

from __future__ import annotations

import unicodedata
from typing import List


def swift_lower(text: str) -> str:
    """``String.lowercased()`` parity: unconditional mappings, no Final_Sigma."""
    return text.replace("Σ", "σ").lower()


def _is_letter(ch: str) -> bool:
    # Swift Character.isLetter is the Unicode Alphabetic property, which
    # includes Letter_Number (Nl) characters like Ⅻ.
    return ch.isalpha() or unicodedata.category(ch) == "Nl"


def _is_word_char(ch: str) -> bool:
    return _is_letter(ch) or ch.isnumeric()


def split_words(text: str) -> List[str]:
    """Runs of letter/number characters — Swift's
    ``split(whereSeparator: { !$0.isLetter && !$0.isNumber })`` semantics.
    NFC-normalizes first so combining sequences behave like Swift's grapheme
    clusters and the resulting tokens compare canonically."""
    return _runs(unicodedata.normalize("NFC", text), _is_word_char)


def split_letter_runs(text: str) -> List[str]:
    """Runs of letters only (Swift's ``!$0.isLetter`` separator)."""
    return _runs(unicodedata.normalize("NFC", text), _is_letter)


def _runs(text: str, predicate) -> List[str]:
    words: List[str] = []
    current: List[str] = []
    for ch in text:
        if predicate(ch):
            current.append(ch)
        elif current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))
    return words


# CharacterSet.whitespacesAndNewlines: Zs + Zl + Zp categories plus the
# control-range \t \n \v \f \r and U+0085. NOT U+001C-U+001F.
_TRIM_EXTRA = {"\t", "\n", "\x0b", "\x0c", "\r", "\x85"}


def _is_swift_whitespace(ch: str) -> bool:
    return ch in _TRIM_EXTRA or unicodedata.category(ch) in ("Zs", "Zl", "Zp")


def swift_trim_whitespace(text: str) -> str:
    """``trimmingCharacters(in: .whitespacesAndNewlines)`` parity."""
    start = 0
    end = len(text)
    while start < end and _is_swift_whitespace(text[start]):
        start += 1
    while end > start and _is_swift_whitespace(text[end - 1]):
        end -= 1
    return text[start:end]


def canonical_compare_key(text: str) -> str:
    """Approximation of Swift ``String`` ordering/equality: canonical (NFC)
    normalization before code-point comparison."""
    return unicodedata.normalize("NFC", text)

# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: BUSL-1.1

"""Claim extraction — mirrors the Swift `ClaimExtractor.swift`.

Claim ids and ranges use UTF-16 code-unit offsets (Swift extracts with
NSRegularExpression over NSString), so ids like ``claim-46-0`` are identical
across both implementations even for documents containing astral-plane
characters.
"""

from __future__ import annotations

import re
from typing import List

from ._text import split_words, swift_lower, swift_trim_whitespace
from .models import Claim, ClaimType

# ICU's non-multiline `$` (NSRegularExpression) matches at end of string AND
# before a final line terminator; Python's non-MULTILINE `$` matches at end
# and before a final "\n". Combined with the `[^.!?\n]+` class and the
# Swift-parity trimming below, the extracted claim text and fingerprint are
# identical for every terminator (\n, \r\n, U+0085, U+2028, U+2029) —
# verified differentially against the Swift CLI.
_SENTENCE = re.compile(r"[^.!?\n]+(?:[.!?]+|$)")

# ICU regex `\s` does NOT include the information separators U+001C-U+001F;
# Python's Unicode `\s` does, so the whitespace class is spelled out to match
# ICU's set exactly.
_ICU_WS = "\\t-\\r \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000"
_CLAUSE_SEPARATOR = re.compile(f"[{_ICU_WS}]+(?:and|but)[{_ICU_WS}]+", re.IGNORECASE)

_NON_CLAIMS = ("please note", "this document is not legal advice")


def _utf16_offset(document: str, char_index: int) -> int:
    """Number of UTF-16 code units before ``char_index`` (Swift NSRange origin)."""
    prefix = document[:char_index]
    return sum(2 if ord(ch) > 0xFFFF else 1 for ch in prefix)


def _utf16_length(text: str) -> int:
    return sum(2 if ord(ch) > 0xFFFF else 1 for ch in text)


def _is_material_claim(text: str) -> bool:
    if not text or text.endswith("?"):
        return False
    if len(split_words(text)) < 4:
        return False
    lower = swift_lower(text)
    return not any(marker in lower for marker in _NON_CLAIMS)


def _atomic_clauses(sentence: str) -> List[str]:
    # Swift replaces separator matches with a U+001F sentinel and then splits
    # on it, so a pre-existing U+001F in the sentence also acts as a clause
    # boundary. Reproduce that exactly rather than using re.split.
    sentinel = _CLAUSE_SEPARATOR.sub("\x1f", sentence)
    parts = [swift_trim_whitespace(part) for part in sentinel.split("\x1f")]
    parts = [p for p in parts if p]
    # Swift's split(separator: " ") drops empty subsequences, so runs of spaces
    # must not inflate the word count here.
    if len(parts) > 1 and all(len([w for w in p.split(" ") if w]) >= 3 for p in parts):
        return parts
    return [sentence]


def _classify(claim: str) -> ClaimType:
    lower = swift_lower(claim)
    if " recommends " in lower or lower.startswith("recommend "):
        return ClaimType.RECOMMENDATION
    if " therefore " in lower or " violated " in lower:
        return ClaimType.LEGAL_CONCLUSION
    if (
        " law requires " in lower
        or " statute " in lower
        or " rule requires " in lower
        or " must be filed" in lower
        or " shall be filed" in lower
    ):
        return ClaimType.LEGAL_RULE
    if " calculated " in lower or " equals " in lower:
        return ClaimType.CALCULATION
    if '"' in claim:
        return ClaimType.QUOTATION
    return ClaimType.FACTUAL


class ClaimExtractor:
    """Deterministic sentence/clause extractor, spec-locked with the Swift one."""

    def extract(self, document: str) -> List[Claim]:
        claims: List[Claim] = []
        for match in _SENTENCE.finditer(document):
            raw = match.group(0)
            text = swift_trim_whitespace(raw)
            if not _is_material_claim(text):
                continue
            start = _utf16_offset(document, match.start())
            length = _utf16_length(raw)
            for index, clause in enumerate(_atomic_clauses(text)):
                claims.append(
                    Claim(
                        id=f"claim-{start}-{index}",
                        text=clause,
                        type=_classify(clause),
                        parent_text=None if clause == text else text,
                        range=(start, start + length),
                    )
                )
        return claims

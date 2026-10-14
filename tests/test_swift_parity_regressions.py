# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for parity divergences found by differential review.

Each case here was PROVEN to flip a verdict, fingerprint, or claim id between
this port and the Swift reference before the fix. Expected values were taken
from the Swift CLI/library output.
"""

import subprocess
import sys
import unicodedata

from claimproofkit import (
    Claim,
    ClaimExtractor,
    ClaimType,
    ClaimVerifier,
    EvidencePassage,
    SourceType,
    SupportStatus,
    VerificationPolicy,
    make_claim_fingerprint,
    policy_fingerprint,
)
from claimproofkit._text import swift_lower, swift_trim_whitespace
from claimproofkit.identity import swift_interpolation, swift_number


def test_trailing_newline_keeps_final_claim():
    # Swift extracts the unpunctuated final line; \Z (the old port) dropped it.
    for document in ("Alpha beta gamma delta\n", "Alpha beta gamma delta\r\n"):
        claims = ClaimExtractor().extract(document)
        assert [c.text for c in claims] == ["Alpha beta gamma delta"]
        assert claims[0].fingerprint == "6b934b388867b6ac"  # Swift CLI value


def test_final_sigma_matches_swift_lowercasing():
    # Swift lowercased() maps Σ→σ unconditionally; str.lower() yields ς finally.
    assert swift_lower("ΟΔΥΣΣΕΥΣ") == "οδυσσευσ"
    # Swift CLI fingerprint for this claim text:
    assert make_claim_fingerprint("ΟΔΥΣΣΕΥΣ granted the motion today.") == "8117edb91ca40630"


def test_nfd_nfc_terms_compare_canonically():
    nfd = unicodedata.normalize("NFD", "The résumé mentions marketing experience today.")
    nfc = unicodedata.normalize("NFC", "The résumé mentions marketing experience today.")
    claim = Claim(id="1", text=nfd, type=ClaimType.FACTUAL)
    evidence = [EvidencePassage(id="e", source="s", source_type=SourceType.EVIDENCE, text=nfc)]
    verdict = ClaimVerifier().verify(claim, evidence)
    assert verdict.status == SupportStatus.DIRECTLY_SUPPORTED
    assert verdict.evidence[0].score == 1.0


def test_information_separators_not_trimmed():
    # CharacterSet.whitespacesAndNewlines does not strip U+001C-U+001F.
    assert swift_trim_whitespace("\x1cThe tenant paid rent in June.") == "\x1cThe tenant paid rent in June."
    assert swift_trim_whitespace("  padded  ") == "padded"
    assert swift_trim_whitespace(" line ") == "line"
    # Swift CLI fingerprint for the claim retaining the leading U+001C:
    claims = ClaimExtractor().extract("\x1cThe tenant paid rent in June.")
    assert claims[0].fingerprint == "754d1380a6e79ffc"


def test_policy_fingerprint_uses_interpolation_rendering():
    # Swift interpolation renders Double(1.0) as "1.0" — verified against the
    # compiled Swift library.
    got = policy_fingerprint(
        VerificationPolicy(
            supported_threshold=1.0,
            ambiguous_threshold=0.5,
            contradiction_threshold=0.75,
            maximum_evidence_matches=3,
        )
    )
    assert got == "544a22323539401937706b28e0672db52d232d262cb5d686898a024c1faa4fb8"
    assert swift_interpolation(1.0) == "1.0"
    assert swift_interpolation(0.8) == "0.8"


def test_swift_number_json_rendering():
    assert swift_number(1.0) == "1"
    assert swift_number(0.75) == "0.75"
    assert swift_number(2 / 3) == "0.6666666666666666"
    assert swift_number(1e16) == "1e+16"
    assert swift_number(-0.0) == "-0"


def test_preexisting_unit_separator_splits_clauses():
    # Swift's U+001F sentinel splitting: a pre-existing U+001F acts as a boundary.
    document = "The tenant paid rent\x1fthe landlord accepted payment today."
    claims = ClaimExtractor().extract(document)
    assert [c.text for c in claims] == [
        "The tenant paid rent",
        "the landlord accepted payment today.",
    ]


def test_utf16_offsets_in_claim_ids():
    # An astral-plane emoji occupies two UTF-16 code units in Swift NSRange.
    # The second sentence match begins at the separating space: 34 code points
    # before it plus one extra UTF-16 unit for the emoji = offset 35.
    document = "🧾 receipt attached for the record. The tenant paid rent in June."
    claims = ClaimExtractor().extract(document)
    assert claims[1].id == "claim-35-0"


def test_cli_survives_non_utf8_stdout():
    result = subprocess.run(
        [sys.executable, "-m", "claimproofkit.cli", "--help"],
        capture_output=True,
        env={"PYTHONIOENCODING": "cp1252", "PATH": "/usr/bin:/bin"},
        check=False,
    )
    assert result.returncode == 0

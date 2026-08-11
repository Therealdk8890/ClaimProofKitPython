# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: BUSL-1.1

"""Core data model — mirrors the Swift ClaimProofKit `Models.swift` exactly.

Claim Proof Specification v1 locks the claim fingerprint algorithm here; the
rest of the identity surface lives in :mod:`claimproofkit.identity`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class SourceType(str, Enum):
    EVIDENCE = "evidence"
    DECLARATION = "declaration"
    COURT_RECORD = "courtRecord"
    STATUTE = "statute"
    REGULATION = "regulation"
    COURT_RULE = "courtRule"
    CASE_LAW = "caseLaw"
    CALCULATION_INPUT = "calculationInput"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EvidencePassage:
    id: str
    source: str
    text: str
    source_type: SourceType = SourceType.UNKNOWN


class ClaimType(str, Enum):
    FACTUAL = "factual"
    LEGAL_RULE = "legalRule"
    LEGAL_CONCLUSION = "legalConclusion"
    CALCULATION = "calculation"
    RECOMMENDATION = "recommendation"
    QUOTATION = "quotation"
    UNKNOWN = "unknown"


def make_claim_fingerprint(text: str) -> str:
    """FNV-1a 64-bit over the lowercased UTF-8 claim text, unpadded lowercase hex.

    Spec §1. Byte-for-byte identical to Swift's ``Claim.makeFingerprint``:
    offset basis 14695981039346656037, prime 1099511628211, XOR-then-wrapping-
    multiply per byte, rendered via ``String(hash, radix: 16)`` (no zero padding).
    Lowercasing uses ``swift_lower`` (no Final_Sigma rule) and hashes the
    original scalars — no Unicode normalization, matching Swift exactly.
    """
    from ._text import swift_lower

    fnv = 14_695_981_039_346_656_037
    for byte in swift_lower(text).encode("utf-8"):
        fnv ^= byte
        fnv = (fnv * 1_099_511_628_211) & 0xFFFF_FFFF_FFFF_FFFF
    return format(fnv, "x")


@dataclass(frozen=True)
class Claim:
    id: str
    text: str
    type: ClaimType = ClaimType.UNKNOWN
    parent_text: Optional[str] = None
    fingerprint: str = ""
    range: Optional[Tuple[int, int]] = None  # UTF-16 code-unit offsets, like Swift

    def __post_init__(self) -> None:
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", make_claim_fingerprint(self.text))


class SupportStatus(str, Enum):
    DIRECTLY_SUPPORTED = "directlySupported"
    SUPPORTED_BY_INFERENCE = "supportedByInference"
    PARTIALLY_SUPPORTED = "partiallySupported"
    CONTRADICTED = "contradicted"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"
    NOT_VERIFIABLE = "notVerifiable"


APPROVED_STATUSES = frozenset(
    {SupportStatus.DIRECTLY_SUPPORTED, SupportStatus.SUPPORTED_BY_INFERENCE}
)


@dataclass(frozen=True)
class EvidenceMatch:
    passage: EvidencePassage
    score: float
    matched_terms: Tuple[str, ...]


@dataclass(frozen=True)
class ClaimVerdict:
    claim: Claim
    status: SupportStatus
    confidence: float
    evidence: Tuple[EvidenceMatch, ...]
    explanation: str


@dataclass(frozen=True)
class ProofReport:
    verdicts: Tuple[ClaimVerdict, ...]
    version: int = 1
    created_at: float = 0.0  # POSIX seconds; explicit, never implicit "now"

    @property
    def is_safe_to_publish(self) -> bool:
        return all(v.status in APPROVED_STATUSES for v in self.verdicts)

    @property
    def support_rate(self) -> float:
        if not self.verdicts:
            return 1.0
        supported = sum(1 for v in self.verdicts if v.status in APPROVED_STATUSES)
        return supported / len(self.verdicts)


@dataclass(frozen=True)
class VerificationPolicy:
    supported_threshold: float = 0.80
    ambiguous_threshold: float = 0.40
    contradiction_threshold: float = 0.55
    maximum_evidence_matches: int = 3

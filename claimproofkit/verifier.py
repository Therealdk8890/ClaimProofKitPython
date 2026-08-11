# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: BUSL-1.1

"""Baseline lexical verifier — mirrors the Swift `ClaimVerifier.swift`.

Verdict semantics are part of Claim Proof Specification v1 (§6) and locked by
the ``verdict_semantics.json`` conformance vector. Any behavior change here
must match a corresponding Swift change and a verifier-version bump.
"""

from __future__ import annotations

from typing import FrozenSet, List, Sequence, Set

from ._text import canonical_compare_key, split_letter_runs, split_words, swift_lower
from .extractor import ClaimExtractor
from .models import (
    Claim,
    ClaimType,
    ClaimVerdict,
    EvidenceMatch,
    EvidencePassage,
    ProofReport,
    SourceType,
    SupportStatus,
    VerificationPolicy,
)

_STOP_WORDS: FrozenSet[str] = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "been", "by", "for", "from",
        "did", "does", "has", "have", "in", "is", "it", "no", "not", "of", "on", "or",
        "that", "the", "this", "to", "was", "were", "will", "with",
    }
)

_NEGATIONS: FrozenSet[str] = frozenset({"not", "no", "never", "without", "cannot"})

_SPECULATIVE: FrozenSet[str] = frozenset(
    {
        "considering", "possible", "possibly", "proposed", "proposal", "planned",
        "planning", "might", "could", "draft", "expected", "intends",
    }
)

_OPPOSITES = (
    ("grant", "deny"), ("approve", "reject"), ("admit", "deny"), ("before", "after"),
    ("increase", "decrease"), ("present", "absent"),
)

_IRREGULAR_STEMS = {
    "admitted": "admit", "decreased": "decrease", "denied": "deny", "filed": "file",
    "granted": "grant", "increased": "increase", "received": "receive",
}

_MONTH_NAMES: FrozenSet[str] = frozenset(
    {
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    }
)


def _normalized_term(term: str) -> str:
    irregular = _IRREGULAR_STEMS.get(term)
    if irregular is not None:
        return irregular
    if len(term) > 5 and term.endswith("ing"):
        return term[:-3]
    if len(term) > 4 and term.endswith("ed"):
        return term[:-2]
    if len(term) > 4 and term.endswith("s"):
        return term[:-1]
    return term


def _significant_terms(text: str) -> Set[str]:
    terms = set()
    for word in split_words(swift_lower(text)):
        normalized = _normalized_term(word)
        if len(normalized) > 1 and normalized not in _STOP_WORDS:
            terms.add(normalized)
    return terms


def _has_negation(text: str) -> bool:
    return bool(set(split_letter_runs(swift_lower(text))) & _NEGATIONS)


def _is_speculative(text: str) -> bool:
    return bool(set(split_letter_runs(swift_lower(text))) & _SPECULATIVE)


def _has_opposing_terms(lhs: str, rhs: str) -> bool:
    left = _significant_terms(lhs)
    right = _significant_terms(rhs)
    return any(
        (a in left and b in right) or (b in left and a in right) for a, b in _OPPOSITES
    )


def _structured_values(text: str) -> Set[str]:
    return {
        token
        for token in split_words(swift_lower(text))
        if any(ch.isnumeric() for ch in token) or token in _MONTH_NAMES
    }


def _has_structured_value_conflict(lhs: str, rhs: str) -> bool:
    left = _structured_values(lhs)
    right = _structured_values(rhs)
    if not left or not right:
        return False
    return not left.issubset(right) and not right.issubset(left)


def _is_verifiable(claim_type: ClaimType) -> bool:
    return claim_type not in (ClaimType.RECOMMENDATION, ClaimType.UNKNOWN)


def _is_eligible(source: SourceType, claim_type: ClaimType) -> bool:
    if source == SourceType.UNKNOWN:
        return True
    if claim_type == ClaimType.FACTUAL:
        return source in (SourceType.EVIDENCE, SourceType.DECLARATION, SourceType.COURT_RECORD)
    if claim_type == ClaimType.LEGAL_RULE:
        return source in (
            SourceType.STATUTE, SourceType.REGULATION, SourceType.COURT_RULE, SourceType.CASE_LAW,
        )
    if claim_type == ClaimType.LEGAL_CONCLUSION:
        return source != SourceType.CALCULATION_INPUT
    if claim_type == ClaimType.CALCULATION:
        return source == SourceType.CALCULATION_INPUT
    if claim_type == ClaimType.QUOTATION:
        return True
    return False  # recommendation, unknown


class ClaimVerifier:
    def __init__(self, policy: VerificationPolicy = VerificationPolicy()):
        self.policy = policy

    def verify_document(
        self, document: str, passages: Sequence[EvidencePassage], created_at: float = 0.0
    ) -> ProofReport:
        claims = ClaimExtractor().extract(document)
        return self.verify_claims(claims, passages, created_at=created_at)

    def verify_claims(
        self, claims: Sequence[Claim], passages: Sequence[EvidencePassage], created_at: float = 0.0
    ) -> ProofReport:
        return ProofReport(
            verdicts=tuple(self.verify(claim, passages) for claim in claims),
            created_at=created_at,
        )

    def verify(self, claim: Claim, passages: Sequence[EvidencePassage]) -> ClaimVerdict:
        if not _is_verifiable(claim.type):
            return self._verdict(
                claim, SupportStatus.NOT_VERIFIABLE, 1.0, (),
                "This claim type requires a verifier or proof policy that is not configured.",
            )

        eligible = [p for p in passages if _is_eligible(p.source_type, claim.type)]
        claim_terms = _significant_terms(claim.text)
        ranked: List[EvidenceMatch] = []
        for passage in eligible:
            passage_terms = _significant_terms(passage.text)
            matched = tuple(sorted(claim_terms & passage_terms))
            score = 0.0 if not claim_terms else len(matched) / len(claim_terms)
            ranked.append(EvidenceMatch(passage=passage, score=score, matched_terms=matched))
        # Deterministic ranking with the same tie-break as Swift: score
        # descending, then passage id ascending.
        ranked.sort(key=lambda m: (-m.score, canonical_compare_key(m.passage.id)))

        if not ranked or ranked[0].score <= 0:
            return self._verdict(
                claim, SupportStatus.UNSUPPORTED, 1.0, (),
                "No supplied evidence passage shares the claim's material terms.",
            )

        best = ranked[0]
        policy = self.policy
        evidence = tuple(
            m for m in ranked[: policy.maximum_evidence_matches] if m.score > 0
        )

        if (
            best.score >= policy.ambiguous_threshold
            and _is_speculative(best.passage.text)
            and not _is_speculative(claim.text)
        ):
            return self._verdict(
                claim, SupportStatus.UNSUPPORTED, best.score, evidence,
                "The passage discusses only a possible or proposed event and does not support the claim that it occurred.",
            )

        polarity_conflict = (
            _has_negation(claim.text) != _has_negation(best.passage.text)
            or _has_opposing_terms(claim.text, best.passage.text)
            or _has_structured_value_conflict(claim.text, best.passage.text)
        )

        if best.score >= policy.contradiction_threshold and polarity_conflict:
            return self._verdict(
                claim, SupportStatus.CONTRADICTED, best.score, evidence,
                "The closest evidence uses the same material terms but reverses the claim's polarity.",
            )
        if best.score >= policy.supported_threshold:
            return self._verdict(
                claim, SupportStatus.DIRECTLY_SUPPORTED, best.score, evidence,
                "A supplied passage covers the claim's material terms.",
            )
        if best.score >= policy.ambiguous_threshold:
            return self._verdict(
                claim, SupportStatus.PARTIALLY_SUPPORTED, best.score, evidence,
                "Related evidence exists, but it does not cover enough of the claim to prove it.",
            )
        return self._verdict(
            claim, SupportStatus.UNSUPPORTED, 1 - best.score, evidence,
            "The closest passage does not sufficiently support the claim.",
        )

    @staticmethod
    def _verdict(
        claim: Claim,
        status: SupportStatus,
        confidence: float,
        evidence: Sequence[EvidenceMatch],
        explanation: str,
    ) -> ClaimVerdict:
        return ClaimVerdict(
            claim=claim,
            status=status,
            confidence=min(max(confidence, 0.0), 1.0),
            evidence=tuple(evidence),
            explanation=explanation,
        )

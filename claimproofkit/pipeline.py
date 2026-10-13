# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: Apache-2.0

"""Pluggable verification pipeline — mirrors the Swift `VerificationProtocols.swift`
and `VerificationPipeline.swift` contracts so local or external verifiers
(semantic entailment, retrieval, human review) can be substituted without
changing the report contract. Swift's async protocol methods map to plain
Python methods; substitute async implementations by overriding `verify_document`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Sequence, Tuple

from .extractor import ClaimExtractor
from .models import Claim, ClaimVerdict, EvidencePassage, ProofReport, SupportStatus
from .verifier import ClaimVerifier


class AtomicClaimExtracting(ABC):
    @abstractmethod
    def extract(self, document: str) -> List[Claim]: ...


class EvidenceRetrieving(ABC):
    @abstractmethod
    def retrieve(
        self, claim: Claim, corpus: Sequence[EvidencePassage], limit: int
    ) -> List[EvidencePassage]: ...


class ClaimEntailmentVerifying(ABC):
    @abstractmethod
    def verify(self, claim: Claim, evidence: Sequence[EvidencePassage]) -> ClaimVerdict: ...


class ProofPolicyEvaluating(ABC):
    @abstractmethod
    def evaluate(self, report: ProofReport) -> "ProofDecision": ...


class TrustReportGenerating(ABC):
    @abstractmethod
    def generate(self, verdicts: Sequence[ClaimVerdict]) -> ProofReport: ...


class Disposition(str, Enum):
    ALLOW = "allow"
    REQUIRE_REVIEW = "requireReview"
    BLOCK = "block"


@dataclass(frozen=True)
class ProofDecision:
    disposition: Disposition
    blocking_claim_ids: Tuple[str, ...] = ()
    review_claim_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PipelineResult:
    report: ProofReport
    decision: ProofDecision


class PassthroughEvidenceRetriever(EvidenceRetrieving):
    def retrieve(
        self, claim: Claim, corpus: Sequence[EvidencePassage], limit: int
    ) -> List[EvidencePassage]:
        return list(corpus[: max(1, limit)])


class LexicalEntailmentVerifier(ClaimEntailmentVerifying):
    def __init__(self, verifier: "ClaimVerifier | None" = None):
        self._verifier = verifier if verifier is not None else ClaimVerifier()

    def verify(self, claim: Claim, evidence: Sequence[EvidencePassage]) -> ClaimVerdict:
        return self._verifier.verify(claim, evidence)


class DefaultTrustReportGenerator(TrustReportGenerating):
    def generate(self, verdicts: Sequence[ClaimVerdict]) -> ProofReport:
        return ProofReport(verdicts=tuple(verdicts))


class ConservativeProofPolicy(ProofPolicyEvaluating):
    def evaluate(self, report: ProofReport) -> ProofDecision:
        blocking = tuple(
            v.claim.id
            for v in report.verdicts
            if v.status in (SupportStatus.CONTRADICTED, SupportStatus.UNSUPPORTED)
        )
        review = tuple(
            v.claim.id
            for v in report.verdicts
            if v.status
            in (SupportStatus.PARTIALLY_SUPPORTED, SupportStatus.AMBIGUOUS, SupportStatus.NOT_VERIFIABLE)
        )
        if blocking:
            return ProofDecision(
                disposition=Disposition.BLOCK, blocking_claim_ids=blocking, review_claim_ids=review
            )
        if review:
            return ProofDecision(disposition=Disposition.REQUIRE_REVIEW, review_claim_ids=review)
        return ProofDecision(disposition=Disposition.ALLOW)


class VerificationPipeline:
    def __init__(
        self,
        extractor: "AtomicClaimExtracting | None" = None,
        retriever: "EvidenceRetrieving | None" = None,
        verifier: "ClaimEntailmentVerifying | None" = None,
        policy: "ProofPolicyEvaluating | None" = None,
        report_generator: "TrustReportGenerating | None" = None,
        evidence_limit: int = 20,
    ):
        self._extractor = extractor if extractor is not None else _DefaultExtractor()
        self._retriever = retriever if retriever is not None else PassthroughEvidenceRetriever()
        self._verifier = verifier if verifier is not None else LexicalEntailmentVerifier()
        self._policy = policy if policy is not None else ConservativeProofPolicy()
        self._report_generator = (
            report_generator if report_generator is not None else DefaultTrustReportGenerator()
        )
        self._evidence_limit = max(1, evidence_limit)

    def verify_document(self, document: str, corpus: Sequence[EvidencePassage]) -> PipelineResult:
        claims = self._extractor.extract(document)
        verdicts = []
        for claim in claims:
            evidence = self._retriever.retrieve(claim, corpus, self._evidence_limit)
            verdicts.append(self._verifier.verify(claim, evidence))
        report = self._report_generator.generate(verdicts)
        return PipelineResult(report=report, decision=self._policy.evaluate(report))


class _DefaultExtractor(AtomicClaimExtracting):
    def __init__(self) -> None:
        self._extractor = ClaimExtractor()

    def extract(self, document: str) -> List[Claim]:
        return self._extractor.extract(document)

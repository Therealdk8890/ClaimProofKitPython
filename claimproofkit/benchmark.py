# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: BUSL-1.1

"""Versioned benchmark harness — mirrors the Swift `BenchmarkModels.swift` /
`BenchmarkRunner.swift`, including the safety-gate semantics: a corpus with no
unsafe-expected cases must not pass vacuously."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from ._text import split_words, swift_lower
from .extractor import ClaimExtractor
from .models import (
    APPROVED_STATUSES,
    Claim,
    ClaimType,
    EvidencePassage,
    SupportStatus,
)
from .verifier import ClaimVerifier


_CATEGORIES = frozenset(
    {
        "directSupport", "reasonableInference", "partialSupport", "contradiction",
        "unsupported", "citationIntegrity", "sourceAuthority", "notVerifiable",
    }
)


def _validated_category(category: str) -> str:
    # Swift decodes category into an 8-case enum; unknown values must fail
    # decoding (exit 65 at the CLI), not pass through silently.
    if category not in _CATEGORIES:
        raise ValueError(f"unknown benchmark category: {category!r}")
    return category


@dataclass(frozen=True)
class ClaimBenchmarkCase:
    id: str
    category: str
    claim_text: str
    claim_type: ClaimType
    evidence: Tuple[EvidencePassage, ...]
    expected_status: SupportStatus
    rationale: str


@dataclass(frozen=True)
class ExtractionBenchmarkCase:
    id: str
    document: str
    expected_claims: Tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkCorpus:
    version: str
    name: str
    claim_cases: Tuple[ClaimBenchmarkCase, ...]
    extraction_cases: Tuple[ExtractionBenchmarkCase, ...]

    @staticmethod
    def from_dict(data: dict) -> "BenchmarkCorpus":
        from .models import SourceType

        return BenchmarkCorpus(
            version=data["version"],
            name=data["name"],
            claim_cases=tuple(
                ClaimBenchmarkCase(
                    id=case["id"],
                    category=_validated_category(case["category"]),
                    claim_text=case["claimText"],
                    claim_type=ClaimType(case["claimType"]),
                    evidence=tuple(
                        EvidencePassage(
                            id=p["id"],
                            source=p["source"],
                            source_type=SourceType(p["sourceType"]),
                            text=p["text"],
                        )
                        for p in case["evidence"]
                    ),
                    expected_status=SupportStatus(case["expectedStatus"]),
                    rationale=case["rationale"],
                )
                for case in data["claimCases"]
            ),
            extraction_cases=tuple(
                ExtractionBenchmarkCase(
                    id=case["id"],
                    document=case["document"],
                    expected_claims=tuple(case["expectedClaims"]),
                )
                for case in data["extractionCases"]
            ),
        )


@dataclass(frozen=True)
class BenchmarkThresholds:
    minimum_verdict_accuracy: float = 0.70
    maximum_false_supported_rate: float = 0.0
    minimum_contradiction_recall: float = 0.80
    minimum_extraction_precision: float = 0.80
    minimum_extraction_recall: float = 0.80
    # Ship criteria (feature go/no-go), evaluated separately from the regression gate.
    minimum_supported_precision: float = 0.95
    minimum_unsupported_recall: float = 0.90


@dataclass(frozen=True)
class StatusMetric:
    expected_count: int
    predicted_count: int
    match_count: int
    precision: float
    recall: float


@dataclass(frozen=True)
class CategoryMetric:
    case_count: int
    exact_match_count: int
    dangerous_approval_count: int
    exact_match_rate: float


@dataclass(frozen=True)
class CalibrationBin:
    lower_bound: float
    upper_bound: float
    case_count: int
    average_confidence: float
    exact_match_rate: float


@dataclass(frozen=True)
class CalibrationSummary:
    bins: Tuple[CalibrationBin, ...]
    expected_calibration_error: float


@dataclass(frozen=True)
class BenchmarkCaseResult:
    id: str
    category: str
    expected: SupportStatus
    predicted: SupportStatus
    confidence: float
    passed: bool
    dangerously_approved: bool


@dataclass(frozen=True)
class ExtractionCaseResult:
    id: str
    expected: Tuple[str, ...]
    predicted: Tuple[str, ...]
    true_positive_count: int
    false_positive_count: int
    false_negative_count: int


@dataclass(frozen=True)
class BenchmarkReport:
    corpus_version: str
    corpus_name: str
    thresholds: BenchmarkThresholds
    claim_results: Tuple[BenchmarkCaseResult, ...]
    extraction_results: Tuple[ExtractionCaseResult, ...]
    verdict_accuracy: float
    false_supported_rate: float
    contradiction_recall: float
    extraction_precision: float
    extraction_recall: float
    supported_precision: float
    unsupported_recall: float
    warning_precision: float
    abstention_precision: float
    abstention_recall: float
    status_metrics: Dict[str, StatusMetric]
    category_breakdown: Dict[str, CategoryMetric]
    calibration: CalibrationSummary
    confusion_matrix: Dict[str, Dict[str, int]]
    passes_safety_gate: bool
    meets_ship_criteria: bool


def _canonical_claim(text: str) -> str:
    return " ".join(split_words(swift_lower(text)))


def _ratio(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else numerator / denominator


def _is_abstention(status: SupportStatus) -> bool:
    return status in (SupportStatus.NOT_VERIFIABLE, SupportStatus.AMBIGUOUS)


def _calibration_summary(results: Tuple[BenchmarkCaseResult, ...]) -> CalibrationSummary:
    bin_count = 5
    binned: List[List[BenchmarkCaseResult]] = [[] for _ in range(bin_count)]
    for result in results:
        index = min(bin_count - 1, max(0, int(result.confidence * bin_count)))
        binned[index].append(result)
    bins: List[CalibrationBin] = []
    error_sum = 0.0
    for index, contents in enumerate(binned):
        lower = index / bin_count
        upper = (index + 1) / bin_count
        if contents:
            # Sequential left-to-right sum, matching Swift's reduce order so the
            # Double result is bit-identical.
            confidence_sum = 0.0
            for result in contents:
                confidence_sum += result.confidence
            average_confidence = confidence_sum / len(contents)
            exact_match_rate = sum(1 for r in contents if r.passed) / len(contents)
        else:
            average_confidence = 0.0
            exact_match_rate = 0.0
        bins.append(
            CalibrationBin(
                lower_bound=lower,
                upper_bound=upper,
                case_count=len(contents),
                average_confidence=average_confidence,
                exact_match_rate=exact_match_rate,
            )
        )
        if contents and results:
            weight = len(contents) / len(results)
            error_sum += weight * abs(exact_match_rate - average_confidence)
    return CalibrationSummary(bins=tuple(bins), expected_calibration_error=error_sum)


class BenchmarkRunner:
    def __init__(
        self,
        verifier: "ClaimVerifier | None" = None,
        extractor: "ClaimExtractor | None" = None,
        thresholds: BenchmarkThresholds = BenchmarkThresholds(),
    ):
        self.verifier = verifier if verifier is not None else ClaimVerifier()
        self.extractor = extractor if extractor is not None else ClaimExtractor()
        self.thresholds = thresholds

    def run(self, corpus: BenchmarkCorpus) -> BenchmarkReport:
        claim_results = tuple(self._run_claim_case(c) for c in corpus.claim_cases)
        extraction_results = tuple(self._run_extraction_case(c) for c in corpus.extraction_cases)

        accurate = sum(1 for r in claim_results if r.passed)
        verdict_accuracy = _ratio(accurate, len(claim_results))

        unsafe_cases = [r for r in claim_results if r.expected not in APPROVED_STATUSES]
        dangerous = sum(1 for r in unsafe_cases if r.dangerously_approved)
        # A failure rate is vacuously 0 (not 1) when no unsafe-expected cases exist.
        false_supported_rate = 0.0 if not unsafe_cases else _ratio(dangerous, len(unsafe_cases))

        expected_contradictions = [r for r in claim_results if r.expected == SupportStatus.CONTRADICTED]
        found = sum(1 for r in expected_contradictions if r.predicted == SupportStatus.CONTRADICTED)
        contradiction_recall = _ratio(found, len(expected_contradictions))

        tp = sum(r.true_positive_count for r in extraction_results)
        fp = sum(r.false_positive_count for r in extraction_results)
        fn = sum(r.false_negative_count for r in extraction_results)
        extraction_precision = _ratio(tp, tp + fp)
        extraction_recall = _ratio(tp, tp + fn)

        confusion: Dict[str, Dict[str, int]] = {}
        for result in claim_results:
            row = confusion.setdefault(result.expected.value, {})
            row[result.predicted.value] = row.get(result.predicted.value, 0) + 1

        # Binary safe/unsafe metrics — same definitions and operation order as
        # the Swift reference so the JSON reports compare equal.
        predicted_approved = [r for r in claim_results if r.predicted in APPROVED_STATUSES]
        supported_precision = _ratio(
            sum(1 for r in predicted_approved if r.expected in APPROVED_STATUSES),
            len(predicted_approved),
        )
        unsupported_recall = _ratio(
            sum(1 for r in unsafe_cases if r.predicted not in APPROVED_STATUSES),
            len(unsafe_cases),
        )
        predicted_flagged = [r for r in claim_results if r.predicted not in APPROVED_STATUSES]
        warning_precision = _ratio(
            sum(1 for r in predicted_flagged if r.expected not in APPROVED_STATUSES),
            len(predicted_flagged),
        )

        predicted_abstain = [r for r in claim_results if _is_abstention(r.predicted)]
        expected_abstain = [r for r in claim_results if _is_abstention(r.expected)]
        abstention_precision = _ratio(
            sum(1 for r in predicted_abstain if _is_abstention(r.expected)),
            len(predicted_abstain),
        )
        abstention_recall = _ratio(
            sum(1 for r in expected_abstain if _is_abstention(r.predicted)),
            len(expected_abstain),
        )

        status_metrics: Dict[str, StatusMetric] = {}
        for status in SupportStatus:
            expected_count = sum(1 for r in claim_results if r.expected == status)
            predicted_count = sum(1 for r in claim_results if r.predicted == status)
            matches = sum(1 for r in claim_results if r.expected == status and r.predicted == status)
            status_metrics[status.value] = StatusMetric(
                expected_count=expected_count,
                predicted_count=predicted_count,
                match_count=matches,
                precision=_ratio(matches, predicted_count),
                recall=_ratio(matches, expected_count),
            )

        category_breakdown: Dict[str, CategoryMetric] = {}
        for category in sorted(_CATEGORIES):
            cases = [r for r in claim_results if r.category == category]
            if not cases:
                continue
            exact = sum(1 for r in cases if r.passed)
            category_breakdown[category] = CategoryMetric(
                case_count=len(cases),
                exact_match_count=exact,
                dangerous_approval_count=sum(1 for r in cases if r.dangerously_approved),
                exact_match_rate=_ratio(exact, len(cases)),
            )

        calibration = _calibration_summary(claim_results)

        thresholds = self.thresholds
        # A corpus with no unsafe-expected cases cannot measure false approvals,
        # so it must not pass the safety gate vacuously.
        passes = (
            bool(unsafe_cases)
            and verdict_accuracy >= thresholds.minimum_verdict_accuracy
            and false_supported_rate <= thresholds.maximum_false_supported_rate
            and contradiction_recall >= thresholds.minimum_contradiction_recall
            and extraction_precision >= thresholds.minimum_extraction_precision
            and extraction_recall >= thresholds.minimum_extraction_recall
        )

        # The ship criteria are a stricter, separate bar: they gate whether the
        # verifier is fit to face users, not whether the build regressed.
        ships = (
            bool(unsafe_cases)
            and supported_precision >= thresholds.minimum_supported_precision
            and unsupported_recall >= thresholds.minimum_unsupported_recall
        )

        return BenchmarkReport(
            corpus_version=corpus.version,
            corpus_name=corpus.name,
            thresholds=thresholds,
            claim_results=claim_results,
            extraction_results=extraction_results,
            verdict_accuracy=verdict_accuracy,
            false_supported_rate=false_supported_rate,
            contradiction_recall=contradiction_recall,
            extraction_precision=extraction_precision,
            extraction_recall=extraction_recall,
            supported_precision=supported_precision,
            unsupported_recall=unsupported_recall,
            warning_precision=warning_precision,
            abstention_precision=abstention_precision,
            abstention_recall=abstention_recall,
            status_metrics=status_metrics,
            category_breakdown=category_breakdown,
            calibration=calibration,
            confusion_matrix=confusion,
            passes_safety_gate=passes,
            meets_ship_criteria=ships,
        )

    def _run_claim_case(self, case: ClaimBenchmarkCase) -> BenchmarkCaseResult:
        claim = Claim(id=case.id, text=case.claim_text, type=case.claim_type)
        verdict = self.verifier.verify(claim, case.evidence)
        approved_predicted = verdict.status in APPROVED_STATUSES
        approved_expected = case.expected_status in APPROVED_STATUSES
        return BenchmarkCaseResult(
            id=case.id,
            category=case.category,
            expected=case.expected_status,
            predicted=verdict.status,
            confidence=verdict.confidence,
            passed=verdict.status == case.expected_status,
            dangerously_approved=approved_predicted and not approved_expected,
        )

    def _run_extraction_case(self, case: ExtractionBenchmarkCase) -> ExtractionCaseResult:
        expected = {_canonical_claim(text) for text in case.expected_claims}
        predicted_claims = tuple(c.text for c in self.extractor.extract(case.document))
        predicted = {_canonical_claim(text) for text in predicted_claims}
        return ExtractionCaseResult(
            id=case.id,
            expected=case.expected_claims,
            predicted=predicted_claims,
            true_positive_count=len(expected & predicted),
            false_positive_count=len(predicted - expected),
            false_negative_count=len(expected - predicted),
        )

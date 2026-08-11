# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: BUSL-1.1

"""Per-class metric tests — mirrors the Swift `BenchmarkTests` additions."""

from claimproofkit import ClaimType, EvidencePassage, SourceType, SupportStatus
from claimproofkit.benchmark import (
    BenchmarkCorpus,
    BenchmarkRunner,
    ClaimBenchmarkCase,
)


def _case(case_id, category, claim, evidence_text, source_type, expected):
    return ClaimBenchmarkCase(
        id=case_id,
        category=category,
        claim_text=claim,
        claim_type=ClaimType.FACTUAL,
        evidence=(
            EvidencePassage(id="e", source="s", source_type=source_type, text=evidence_text),
        ),
        expected_status=expected,
        rationale="test",
    )


def test_lazy_approval_fails_ship_criteria():
    # Full lexical overlap with a different meaning: the baseline verifier
    # approves this, the gold label says it must not.
    corpus = BenchmarkCorpus(
        version="canary",
        name="lazy approval canary",
        claim_cases=(
            _case(
                "canary-1",
                "partialSupport",
                "The tenant paid rent in March.",
                "The tenant paid rent in March into escrow rather than to the landlord.",
                SourceType.EVIDENCE,
                SupportStatus.PARTIALLY_SUPPORTED,
            ),
            _case(
                "canary-2",
                "directSupport",
                "The court denied the request for an extension.",
                "The court denied the request for an extension.",
                SourceType.COURT_RECORD,
                SupportStatus.DIRECTLY_SUPPORTED,
            ),
        ),
        extraction_cases=(),
    )
    report = BenchmarkRunner().run(corpus)
    assert report.supported_precision == 0.5
    assert report.unsupported_recall == 0
    assert not report.meets_ship_criteria
    assert not report.passes_safety_gate


def test_calibration_bins_cover_all_cases():
    corpus = BenchmarkCorpus(
        version="t",
        name="t",
        claim_cases=(
            _case(
                "c-1",
                "contradiction",
                "The court did not deny the request for an extension.",
                "The court denied the request for an extension.",
                SourceType.COURT_RECORD,
                SupportStatus.CONTRADICTED,
            ),
        ),
        extraction_cases=(),
    )
    report = BenchmarkRunner().run(corpus)
    assert sum(b.case_count for b in report.calibration.bins) == len(report.claim_results)
    assert 0 <= report.calibration.expected_calibration_error <= 1
    assert report.status_metrics["contradicted"].recall == 1.0
    assert report.category_breakdown["contradiction"].case_count == 1

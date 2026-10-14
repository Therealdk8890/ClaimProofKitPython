# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: Apache-2.0

"""Human-readable and machine-readable report rendering — mirrors the Swift
`ReportRenderer.swift` and `BenchmarkReportRenderer.swift`, plus the Swift
CLI's ``--json`` benchmark wire format (camelCase, sorted keys)."""

from __future__ import annotations

import json
import math
from typing import Dict, List

from .benchmark import BenchmarkReport
from .models import APPROVED_STATUSES, ProofReport


def _swift_rounded(value: float) -> int:
    """Swift's ``Double.rounded()`` — half away from zero (non-negative inputs)."""
    return int(math.floor(value + 0.5))


def render_report_markdown(report: ProofReport) -> str:
    percent = _swift_rounded(report.support_rate * 100)
    supported = sum(1 for v in report.verdicts if v.status in APPROVED_STATUSES)
    lines: List[str] = [
        "# ClaimProof Report",
        "",
        f"**Publish status:** {'PASS' if report.is_safe_to_publish else 'BLOCKED'}",
        f"**Supported claims:** {percent}% ({supported}/{len(report.verdicts)})",
        "",
    ]
    for verdict in report.verdicts:
        lines.append(f"## [{verdict.status.value.upper()}] {verdict.claim.text}")
        lines.append("")
        lines.append(f"Type: `{verdict.claim.type.value}` · Fingerprint: `{verdict.claim.fingerprint}`")
        lines.append("")
        lines.append(verdict.explanation)
        for match in verdict.evidence:
            coverage = _swift_rounded(match.score * 100)
            lines.append(f"- `{match.passage.id}` {match.passage.source} — {coverage}% term coverage")
            lines.append(f"  > {match.passage.text.replace(chr(10), ' ')}")
        lines.append("")
    return "\n".join(lines)


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_benchmark_markdown(report: BenchmarkReport) -> str:
    failures = [r for r in report.claim_results if not r.passed]
    dangerous = [r for r in report.claim_results if r.dangerously_approved]
    t = report.thresholds
    lines: List[str] = [
        f"# ClaimProofKit Benchmark {report.corpus_version}",
        "",
        f"**Safety gate:** {'PASS' if report.passes_safety_gate else 'FAIL'}",
        f"**Corpus:** {report.corpus_name}",
        "",
        "| Metric | Result | Required |",
        "| --- | ---: | ---: |",
        f"| Verdict accuracy | {_percent(report.verdict_accuracy)} | ≥ {_percent(t.minimum_verdict_accuracy)} |",
        f"| False-supported rate | {_percent(report.false_supported_rate)} | ≤ {_percent(t.maximum_false_supported_rate)} |",
        f"| Contradiction recall | {_percent(report.contradiction_recall)} | ≥ {_percent(t.minimum_contradiction_recall)} |",
        f"| Extraction precision | {_percent(report.extraction_precision)} | ≥ {_percent(t.minimum_extraction_precision)} |",
        f"| Extraction recall | {_percent(report.extraction_recall)} | ≥ {_percent(t.minimum_extraction_recall)} |",
        "",
        f"Cases: {len(report.claim_results)} verdict · {len(report.extraction_results)} extraction · "
        f"{len(failures)} exact-verdict failures · {len(dangerous)} dangerous approvals",
        "",
        "## Ship criteria",
        "",
        f"**Ship criteria:** {'MET' if report.meets_ship_criteria else 'NOT MET'} — necessary on this development corpus, sufficient only on independently labeled realistic documents.",
        "",
        "| Metric | Result | Required |",
        "| --- | ---: | ---: |",
        f"| Supported-claim precision | {_percent(report.supported_precision)} | ≥ {_percent(t.minimum_supported_precision)} |",
        f"| Unsupported/contradicted recall | {_percent(report.unsupported_recall)} | ≥ {_percent(t.minimum_unsupported_recall)} |",
        "",
        "| Diagnostic (report-only) | Result |",
        "| --- | ---: |",
        f"| Warning precision | {_percent(report.warning_precision)} |",
        f"| Abstention precision | {_percent(report.abstention_precision)} |",
        f"| Abstention recall | {_percent(report.abstention_recall)} |",
        f"| Expected calibration error | {report.calibration.expected_calibration_error:.3f} |",
        "",
        "## Per-category outcomes",
        "",
        "| Category | Cases | Exact | Dangerous approvals |",
        "| --- | ---: | ---: | ---: |",
    ]
    for key in sorted(report.category_breakdown):
        metric = report.category_breakdown[key]
        lines.append(
            f"| {key} | {metric.case_count} | {metric.exact_match_count} ({_percent(metric.exact_match_rate)}) "
            f"| {metric.dangerous_approval_count} |"
        )
    lines.extend(
        [
            "",
            "## Calibration",
            "",
            "| Confidence | Cases | Avg confidence | Exact-match rate |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for bin_ in report.calibration.bins:
        if bin_.case_count > 0:
            lines.append(
                f"| {bin_.lower_bound:.1f}–{bin_.upper_bound:.1f} | {bin_.case_count} "
                f"| {bin_.average_confidence:.2f} | {_percent(bin_.exact_match_rate)} |"
            )
    if failures:
        lines.extend(["", "## Verdict mismatches", ""])
        for failure in failures:
            lines.append(
                f"- `{failure.id}` [{failure.category}]: expected `{failure.expected.value}`, "
                f"predicted `{failure.predicted.value}`"
            )
    extraction_failures = [
        r for r in report.extraction_results if r.false_positive_count > 0 or r.false_negative_count > 0
    ]
    if extraction_failures:
        lines.extend(["", "## Extraction mismatches", ""])
        for failure in extraction_failures:
            lines.append(f"- `{failure.id}`: {failure.false_positive_count} extra, {failure.false_negative_count} missed")
    return "\n".join(lines)


def benchmark_report_wire(report: BenchmarkReport) -> Dict[str, object]:
    """The Swift CLI's ``--json`` shape (camelCase keys), for cross-implementation
    comparison of full benchmark runs."""
    t = report.thresholds
    return {
        "corpusVersion": report.corpus_version,
        "corpusName": report.corpus_name,
        "thresholds": {
            "minimumVerdictAccuracy": t.minimum_verdict_accuracy,
            "maximumFalseSupportedRate": t.maximum_false_supported_rate,
            "minimumContradictionRecall": t.minimum_contradiction_recall,
            "minimumExtractionPrecision": t.minimum_extraction_precision,
            "minimumExtractionRecall": t.minimum_extraction_recall,
            "minimumSupportedPrecision": t.minimum_supported_precision,
            "minimumUnsupportedRecall": t.minimum_unsupported_recall,
        },
        "claimResults": [
            {
                "id": r.id,
                "category": r.category,
                "expected": r.expected.value,
                "predicted": r.predicted.value,
                "confidence": r.confidence,
                "passed": r.passed,
                "dangerouslyApproved": r.dangerously_approved,
            }
            for r in report.claim_results
        ],
        "extractionResults": [
            {
                "id": r.id,
                "expected": list(r.expected),
                "predicted": list(r.predicted),
                "truePositiveCount": r.true_positive_count,
                "falsePositiveCount": r.false_positive_count,
                "falseNegativeCount": r.false_negative_count,
            }
            for r in report.extraction_results
        ],
        "verdictAccuracy": report.verdict_accuracy,
        "falseSupportedRate": report.false_supported_rate,
        "contradictionRecall": report.contradiction_recall,
        "extractionPrecision": report.extraction_precision,
        "extractionRecall": report.extraction_recall,
        "supportedPrecision": report.supported_precision,
        "unsupportedRecall": report.unsupported_recall,
        "warningPrecision": report.warning_precision,
        "abstentionPrecision": report.abstention_precision,
        "abstentionRecall": report.abstention_recall,
        "statusMetrics": {
            status: {
                "expectedCount": m.expected_count,
                "predictedCount": m.predicted_count,
                "matchCount": m.match_count,
                "precision": m.precision,
                "recall": m.recall,
            }
            for status, m in report.status_metrics.items()
        },
        "categoryBreakdown": {
            category: {
                "caseCount": m.case_count,
                "exactMatchCount": m.exact_match_count,
                "dangerousApprovalCount": m.dangerous_approval_count,
                "exactMatchRate": m.exact_match_rate,
            }
            for category, m in report.category_breakdown.items()
        },
        "calibration": {
            "bins": [
                {
                    "lowerBound": b.lower_bound,
                    "upperBound": b.upper_bound,
                    "caseCount": b.case_count,
                    "averageConfidence": b.average_confidence,
                    "exactMatchRate": b.exact_match_rate,
                }
                for b in report.calibration.bins
            ],
            "expectedCalibrationError": report.calibration.expected_calibration_error,
        },
        "confusionMatrix": report.confusion_matrix,
        "passesSafetyGate": report.passes_safety_gate,
        "meetsShipCriteria": report.meets_ship_criteria,
    }


def benchmark_report_json(report: BenchmarkReport) -> str:
    return json.dumps(benchmark_report_wire(report), sort_keys=True, indent=2, ensure_ascii=False)

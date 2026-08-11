# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: BUSL-1.1

"""Claim Proof Specification v1 conformance runner.

Executes the golden vectors vendored under ``vectors/`` (source of truth: the
Swift ClaimProofKit repo's ConformanceHarness — the reference implementation)
against this Python implementation. Every fingerprint, verdict, and canonical
payload byte must match exactly.

Usage:
    python conformance/run_conformance.py [--vectors PATH]

Exit code 0 on full conformance, 1 on any failure.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from claimproofkit import (  # noqa: E402
    Claim,
    ClaimExtractor,
    ClaimType,
    ClaimVerdict,
    ClaimVerifier,
    EvidencePassage,
    ProofReport,
    ProvenanceExporter,
    SourceType,
    SupportStatus,
    VerificationPolicy,
    policy_fingerprint,
    report_fingerprint,
)
from claimproofkit.identity import SPEC_VERSION  # noqa: E402

FAILURES = 0


def check(name: str, passed: bool, detail: str = "") -> None:
    global FAILURES
    if passed:
        print(f"  PASS {name}")
    else:
        FAILURES += 1
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))


def load(vectors: pathlib.Path, name: str) -> dict:
    with open(vectors / name, encoding="utf-8") as handle:
        doc = json.load(handle)
    # An empty or truncated vector must fail loudly, not pass vacuously.
    check(f"{name} has cases", bool(doc.get("cases")) or name == "provenance_bridge.json")
    if name == "provenance_bridge.json":
        check(f"{name} has events", bool(doc.get("events")))
    return doc


def passages(wire: list) -> list:
    return [
        EvidencePassage(
            id=p["id"],
            source=p["source"],
            source_type=SourceType(p["sourceType"]),
            text=p["text"],
        )
        for p in wire
    ]


def check_claim_fingerprints(vectors: pathlib.Path) -> None:
    print("\n[1] claim fingerprint")
    doc = load(vectors, "claim_fingerprint.json")
    check("spec version", doc["specVersion"] == SPEC_VERSION)
    for i, case in enumerate(doc["cases"]):
        got = Claim(id="vector", text=case["text"]).fingerprint
        check(
            f"case {i}: {case['description']}",
            got == case["fingerprint"],
            f"expected {case['fingerprint']} got {got}",
        )


def check_policy_fingerprints(vectors: pathlib.Path) -> None:
    print("\n[2] policy fingerprint")
    doc = load(vectors, "policy_fingerprint.json")
    check("spec version", doc["specVersion"] == SPEC_VERSION)
    for i, case in enumerate(doc["cases"]):
        policy = VerificationPolicy(
            supported_threshold=case["supportedThreshold"],
            ambiguous_threshold=case["ambiguousThreshold"],
            contradiction_threshold=case["contradictionThreshold"],
            maximum_evidence_matches=case["maximumEvidenceMatches"],
        )
        got = policy_fingerprint(policy)
        check(
            f"case {i}: {case['description']}",
            got == case["fingerprint"],
            f"expected {case['fingerprint']} got {got}",
        )


def check_report_fingerprints(vectors: pathlib.Path) -> None:
    print("\n[3] report fingerprint")
    doc = load(vectors, "report_fingerprint.json")
    check("spec version", doc["specVersion"] == SPEC_VERSION)
    for i, case in enumerate(doc["cases"]):
        verdicts = tuple(
            ClaimVerdict(
                claim=Claim(id=f"vector-{j}", text=v["claimText"]),
                status=SupportStatus(v["status"]),
                confidence=1.0,
                evidence=(),
                explanation="conformance vector",
            )
            for j, v in enumerate(case["verdicts"])
        )
        got = report_fingerprint(ProofReport(verdicts=verdicts))
        check(
            f"case {i}: {case['description']}",
            got == case["fingerprint"],
            f"expected {case['fingerprint']} got {got}",
        )


def check_verdict_semantics(vectors: pathlib.Path) -> None:
    print("\n[4] verdict semantics")
    doc = load(vectors, "verdict_semantics.json")
    check("spec version", doc["specVersion"] == SPEC_VERSION)
    for i, case in enumerate(doc["cases"]):
        claim = Claim(id="vector", text=case["claimText"], type=ClaimType(case["claimType"]))
        verdict = ClaimVerifier().verify(claim, passages(case["evidence"]))
        check(
            f"case {i}: {case['description']}",
            verdict.status.value == case["expectedStatus"],
            f"expected {case['expectedStatus']} got {verdict.status.value}",
        )


def check_provenance_bridge(vectors: pathlib.Path):
    print("\n[5] provenance bridge")
    doc = load(vectors, "provenance_bridge.json")
    check("spec version", doc["specVersion"] == SPEC_VERSION)

    evidence = passages(doc["evidence"])
    claims = ClaimExtractor().extract(doc["document"])
    verifier = ClaimVerifier()
    report = ProofReport(
        verdicts=tuple(verifier.verify(claim, evidence) for claim in claims),
        created_at=doc["createdAtEpochSeconds"],
    )
    trace = ProvenanceExporter().trace(report, VerificationPolicy())

    check(
        "report fingerprint",
        report_fingerprint(report) == doc["reportFingerprint"],
        f"expected {doc['reportFingerprint']} got {report_fingerprint(report)}",
    )
    check("policy fingerprint", policy_fingerprint(VerificationPolicy()) == doc["policyFingerprint"])
    check(
        "run fingerprint",
        trace.run_fingerprint == doc["runFingerprint"],
        f"expected {doc['runFingerprint']} got {trace.run_fingerprint}",
    )
    check(
        "event count",
        len(trace.events) == len(doc["events"]),
        f"expected {len(doc['events'])} got {len(trace.events)}",
    )
    for i, (event, expected) in enumerate(zip(trace.events, doc["events"])):
        check(f"event {i} type", event.payload.type_identifier == expected["typeIdentifier"])
        check(f"event {i} priority", event.payload.priority_value == expected["priorityValue"])
        check(
            f"event {i} canonical payload",
            event.payload.raw_json == expected["rawJSON"],
            f"expected {expected['rawJSON']} got {event.payload.raw_json}",
        )

    sequence_by_id = {event.id: event.sequence for event in trace.events}
    got_edges = [
        {
            "sourceSequence": sequence_by_id[e.source_id],
            "targetSequence": sequence_by_id[e.target_id],
            "type": e.type,
        }
        for e in trace.edges
    ]
    check("edges", got_edges == doc["edges"], f"expected {doc['edges']} got {got_edges}")
    return trace


def check_dprovenancekit_roundtrip(trace) -> None:
    """Optional: prove the run fingerprint against the real Python dprovenancekit.

    Runs when the ``dprovenancekit`` package is importable (installed, or the
    sibling checkout is present); skips otherwise.
    """
    print("\n[6] dprovenancekit round-trip (live package)")
    sibling = pathlib.Path.home() / "DProvenanceKitPython"
    if sibling.is_dir():
        sys.path.insert(0, str(sibling))
    try:
        import dprovenancekit  # noqa: F401
        from dprovenancekit.sqlite_store import SQLiteTraceStore
    except Exception as error:  # pragma: no cover - environment-dependent
        import os

        if os.environ.get("CPK_REQUIRE_DPK_ROUNDTRIP"):
            check("dprovenancekit importable", False, str(error))
        else:
            print(f"  SKIP dprovenancekit not importable ({error})")
        return

    import tempfile

    from dprovenancekit.event import TraceEvent, TraceableEvent
    from dprovenancekit.priority import TracePriority

    class Erased(TraceableEvent):
        def __init__(self, type_identifier: str, priority_value: int, raw_json: str):
            self._type = type_identifier
            self._priority = priority_value
            self._raw = raw_json

        @property
        def type_identifier(self) -> str:
            return self._type

        @property
        def priority(self) -> TracePriority:
            return TracePriority(self._priority)

        def to_dict(self) -> dict:
            return json.loads(self._raw)

    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "roundtrip.sqlite"
        store = SQLiteTraceStore(Erased, str(path))
        run_id = uuid.uuid4()
        for event in trace.events:
            store.record(
                TraceEvent(
                    run_id=run_id,
                    context_id=event.context_id,
                    engine_name=event.engine_name,
                    schema_version=event.schema_version,
                    sequence=event.sequence,
                    span_id=None,
                    parent_span_id=None,
                    payload=Erased(
                        event.payload.type_identifier,
                        event.payload.priority_value,
                        event.payload.raw_json,
                    ),
                )
            )
        store.flush()
        import sqlite3

        connection = sqlite3.connect(str(path))
        row = connection.execute("SELECT fingerprint FROM runs LIMIT 1").fetchone()
        connection.close()
        stored = row[0] if row else "<none>"
        check(
            "store fingerprint matches bridge fingerprint",
            stored == trace.run_fingerprint,
            f"expected {trace.run_fingerprint} got {stored}",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--vectors",
        default=str(pathlib.Path(__file__).resolve().parent / "vectors"),
        help="Path to the golden vector directory",
    )
    args = parser.parse_args()
    vectors = pathlib.Path(args.vectors)

    print(f"Claim Proof Specification v{SPEC_VERSION} conformance (Python)")
    check_claim_fingerprints(vectors)
    check_policy_fingerprints(vectors)
    check_report_fingerprints(vectors)
    check_verdict_semantics(vectors)
    trace = check_provenance_bridge(vectors)
    check_dprovenancekit_roundtrip(trace)

    if FAILURES:
        print(f"\n{FAILURES} conformance failure(s)")
        return 1
    print("\nAll conformance checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

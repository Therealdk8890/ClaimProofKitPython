# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: Apache-2.0

"""Port of the Swift proof-identity and provenance-export tests."""

import json
import uuid

from claimproofkit import (
    Claim,
    ClaimType,
    ClaimVerdict,
    ClaimVerifier,
    EvidencePassage,
    ProofReport,
    ProvenanceExporter,
    SourceType,
    SupportStatus,
    VerificationPolicy,
    evidence_content_fingerprint,
    policy_fingerprint,
    report_fingerprint,
)

EVIDENCE = [
    EvidencePassage(
        id="order-1",
        source="Scheduling Order",
        source_type=SourceType.COURT_RECORD,
        text="The court denied the request for an extension.",
    )
]


def _verdict(text: str, status: SupportStatus) -> ClaimVerdict:
    return ClaimVerdict(
        claim=Claim(id=f"c-{len(text)}", text=text),
        status=status,
        confidence=1.0,
        evidence=(),
        explanation="test",
    )


def _report() -> ProofReport:
    claims = [
        Claim(id="1", text="The court denied the request for an extension.", type=ClaimType.FACTUAL),
        Claim(id="2", text="The court granted the request for an extension.", type=ClaimType.FACTUAL),
    ]
    verifier = ClaimVerifier()
    return ProofReport(
        verdicts=tuple(verifier.verify(c, EVIDENCE) for c in claims),
        created_at=1_760_000_000.0,
    )


def test_report_fingerprint_stability_and_sensitivity():
    supported = _verdict("The court granted the motion.", SupportStatus.DIRECTLY_SUPPORTED)
    contradicted = _verdict("The court granted the motion.", SupportStatus.CONTRADICTED)
    other = _verdict("The tenant paid rent in March.", SupportStatus.DIRECTLY_SUPPORTED)

    base = report_fingerprint(ProofReport(verdicts=(supported, other)))
    assert len(base) == 64
    assert report_fingerprint(ProofReport(verdicts=(supported, other), created_at=99.0)) == base
    assert report_fingerprint(ProofReport(verdicts=(contradicted, other))) != base
    assert report_fingerprint(ProofReport(verdicts=(other, supported))) != base


def test_policy_fingerprint_pins_thresholds_and_verifier():
    base = policy_fingerprint(VerificationPolicy())
    assert len(base) == 64
    assert policy_fingerprint(VerificationPolicy(supported_threshold=0.9)) != base
    assert policy_fingerprint(VerificationPolicy(), verifier="custom-nli") != base


def test_evidence_fingerprint_is_byte_exact():
    a = EvidencePassage(id="e", source="s", text="The rent was paid.")
    b = EvidencePassage(id="e", source="s", text="The rent was paid. ")
    upper = EvidencePassage(id="e", source="s", text="THE RENT WAS PAID.")
    assert evidence_content_fingerprint(a) != evidence_content_fingerprint(b)
    assert evidence_content_fingerprint(a) != evidence_content_fingerprint(upper)


def test_export_vocabulary_order_and_edges():
    trace = ProvenanceExporter().trace(_report(), VerificationPolicy())
    assert [e.payload.type_identifier for e in trace.events] == [
        "cpk_claim_extracted", "cpk_claim_verified",
        "cpk_claim_extracted", "cpk_claim_verified",
        "cpk_report_finalized",
    ]
    assert [e.sequence for e in trace.events] == [0, 1, 2, 3, 4]
    assert len({e.run_id for e in trace.events}) == 1

    verified_by = [e for e in trace.edges if e.type == "verifiedBy"]
    derived_from = [e for e in trace.edges if e.type == "derivedFrom"]
    assert len(verified_by) == 2 and len(derived_from) == 2
    report_event = trace.events[-1]
    assert all(e.target_id == report_event.id for e in derived_from)


def test_run_fingerprint_deterministic_and_engine_sensitive():
    report = _report()
    first = ProvenanceExporter().trace(report, VerificationPolicy(), run_id=uuid.uuid4())
    second = ProvenanceExporter().trace(report, VerificationPolicy(), run_id=uuid.uuid4())
    assert first.run_fingerprint == second.run_fingerprint
    assert len(first.run_fingerprint) == 40
    custom = ProvenanceExporter(engine_name="Custom").trace(report, VerificationPolicy())
    assert custom.run_fingerprint != first.run_fingerprint


def test_wire_json_shapes():
    trace = ProvenanceExporter().trace(_report(), VerificationPolicy())
    events = json.loads(trace.events_json())
    assert len(events) == 5
    for wire in events:
        assert set(wire).issuperset(
            {"id", "runID", "contextID", "engineName", "schemaVersion", "sequence", "payload", "timestamp"}
        )
        assert set(wire["payload"]) == {"typeIdentifier", "priorityValue", "rawJSON"}
        # rawJSON top-level keys must appear in sorted byte order.
        raw = wire["payload"]["rawJSON"]
        keys = list(json.loads(raw))
        positions = [raw.index(f'"{key}":') for key in keys]
        assert [k for _, k in sorted(zip(positions, keys))] == sorted(keys)

    manifest = json.loads(trace.manifest_json())
    assert manifest["bridgeVersion"] == "1.0"
    assert manifest["runFingerprint"] == trace.run_fingerprint
    assert len(manifest["edges"]) == 4


def test_empty_report_exports_lone_finalization():
    trace = ProvenanceExporter().trace(ProofReport(verdicts=()), VerificationPolicy())
    assert [e.payload.type_identifier for e in trace.events] == ["cpk_report_finalized"]
    assert trace.edges == []

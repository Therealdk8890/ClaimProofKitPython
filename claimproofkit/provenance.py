# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: BUSL-1.1

"""DProvenanceKit bridge — mirrors the Swift `ClaimProofProvenance` target.

Emits envelopes wire-compatible with DProvenanceKit's
``TraceEvent<AnyTraceableEvent>`` (camelCase keys, Swift reference-date
timestamps), with canonical payload bytes per Trace Specification v1 §2 and
the §5 run fingerprint. Parity with the Swift bridge is locked by the
``provenance_bridge.json`` conformance vector.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .identity import (
    SPEC_VERSION,
    canonical_json,
    evidence_content_fingerprint,
    policy_fingerprint,
    report_fingerprint,
    swift_number,
)
from .models import ClaimVerdict, ProofReport, VerificationPolicy

BRIDGE_VERSION = "1.0"

CLAIM_EXTRACTED = "cpk_claim_extracted"
CLAIM_VERIFIED = "cpk_claim_verified"
REPORT_FINALIZED = "cpk_report_finalized"

PRIORITY_TELEMETRY = 0
PRIORITY_DIAGNOSTIC = 1
PRIORITY_STRUCTURAL = 2
PRIORITY_CRITICAL = 3

EDGE_DERIVED_FROM = "derivedFrom"
EDGE_VERIFIED_BY = "verifiedBy"

_SWIFT_REFERENCE_EPOCH = 978_307_200.0  # 2001-01-01T00:00:00Z in POSIX seconds


def _claim_extracted_payload(verdict: ClaimVerdict) -> Dict[str, object]:
    claim = verdict.claim
    return {
        "claimID": claim.id,
        "claimType": claim.type.value,
        "fingerprint": claim.fingerprint,
        "text": claim.text,
    }


def _claim_verified_payload(verdict: ClaimVerdict) -> Dict[str, object]:
    return {
        "claimFingerprint": verdict.claim.fingerprint,
        "confidence": verdict.confidence,
        "evidenceFingerprints": [
            evidence_content_fingerprint(match.passage) for match in verdict.evidence
        ],
        "status": verdict.status.value,
    }


def _report_finalized_payload(
    report: ProofReport, policy: VerificationPolicy
) -> Dict[str, object]:
    counts: Dict[str, int] = {}
    for verdict in report.verdicts:
        counts[verdict.status.value] = counts.get(verdict.status.value, 0) + 1
    return {
        "policyFingerprint": policy_fingerprint(policy),
        "reportFingerprint": report_fingerprint(report),
        "safeToPublish": report.is_safe_to_publish,
        "specVersion": SPEC_VERSION,
        "statusCounts": counts,
    }


def semantic_key(verdict: ClaimVerdict) -> str:
    """Runtime equivalence hint, mirroring the Swift bridge (never serialized)."""
    return f"{CLAIM_VERIFIED}:{verdict.claim.fingerprint}:{verdict.status.value}"


@dataclass(frozen=True)
class ErasedProvenancePayload:
    type_identifier: str
    priority_value: int
    raw_json: str

    def to_wire(self) -> Dict[str, object]:
        return {
            "typeIdentifier": self.type_identifier,
            "priorityValue": self.priority_value,
            "rawJSON": self.raw_json,
        }


@dataclass(frozen=True)
class ProvenanceEventEnvelope:
    id: uuid.UUID
    run_id: uuid.UUID
    context_id: str
    engine_name: str
    schema_version: int
    sequence: int
    payload: ErasedProvenancePayload
    timestamp: float  # POSIX seconds
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None

    def to_wire(self) -> Dict[str, object]:
        wire: Dict[str, object] = {
            "id": str(self.id).upper(),  # Swift UUID strings are uppercase
            "runID": str(self.run_id).upper(),
            "contextID": self.context_id,
            "engineName": self.engine_name,
            "schemaVersion": self.schema_version,
            "sequence": self.sequence,
            "payload": self.payload.to_wire(),
            # Swift Codable Date: seconds since the 2001 reference date.
            "timestamp": _RawNumber(self.timestamp - _SWIFT_REFERENCE_EPOCH),
        }
        if self.span_id is not None:
            wire["spanID"] = self.span_id
        if self.parent_span_id is not None:
            wire["parentSpanID"] = self.parent_span_id
        return wire


@dataclass(frozen=True)
class ProvenanceEdge:
    source_id: uuid.UUID
    target_id: uuid.UUID
    type: str

    def to_wire(self) -> Dict[str, object]:
        return {
            "sourceID": str(self.source_id).upper(),
            "targetID": str(self.target_id).upper(),
            "type": self.type,
        }


class _RawNumber(float):
    """Marker so the wire encoder renders a float Swift-style ("1" not "1.0")."""


def _wire_default(value: object) -> object:
    raise TypeError(f"not wire-encodable: {type(value).__name__}")


def _encode_wire(value: object, indent: int = 2) -> str:
    """Pretty, sorted-keys JSON with Swift-style number rendering."""

    def transform(node: object) -> object:
        if isinstance(node, _RawNumber):
            # json.dumps would render 1.0; Swift renders 1. Wrap via int when exact.
            return int(node) if float(node).is_integer() else float(node)
        if isinstance(node, dict):
            return {k: transform(v) for k, v in node.items()}
        if isinstance(node, list):
            return [transform(v) for v in node]
        return node

    return json.dumps(transform(value), sort_keys=True, indent=indent, separators=(",", " : "), ensure_ascii=False, default=_wire_default)


@dataclass(frozen=True)
class ProvenanceTrace:
    events: List[ProvenanceEventEnvelope]
    edges: List[ProvenanceEdge]
    run_fingerprint: str
    report_fingerprint: str
    policy_fingerprint: str
    engine_name: str
    context_id: str

    def events_json(self) -> str:
        """Bare JSON array of envelopes — decodes in the Swift DProvenanceKit as
        ``[TraceEvent<AnyTraceableEvent>]`` with a default ``JSONDecoder``."""
        return _encode_wire([event.to_wire() for event in self.events])

    def manifest_json(self) -> str:
        """Full manifest matching the Swift bridge's ``ProvenanceManifest``."""
        return _encode_wire(
            {
                "bridgeVersion": BRIDGE_VERSION,
                "specVersion": SPEC_VERSION,
                "engineName": self.engine_name,
                "contextID": self.context_id,
                "runFingerprint": self.run_fingerprint,
                "reportFingerprint": self.report_fingerprint,
                "policyFingerprint": self.policy_fingerprint,
                "events": [event.to_wire() for event in self.events],
                "edges": [edge.to_wire() for edge in self.edges],
            }
        )


def run_fingerprint_of(events: Sequence[ProvenanceEventEnvelope]) -> str:
    """Trace Specification v1 §5: SHA-1 over ``type:engine|`` per event in order."""
    digest = hashlib.sha1()
    for event in events:
        digest.update(f"{event.payload.type_identifier}:{event.engine_name}|".encode("utf-8"))
    return digest.hexdigest()


@dataclass(frozen=True)
class ProvenanceExporter:
    engine_name: str = "ClaimProofKit"
    context_id: str = "claimproof"
    schema_version: int = 1

    def trace(
        self,
        report: ProofReport,
        policy: VerificationPolicy,
        run_id: Optional[uuid.UUID] = None,
    ) -> ProvenanceTrace:
        """Builds the trace for a report. ``policy`` is deliberately required —
        ``ProofReport`` does not carry the policy it was produced under, so the
        caller must pass the one actually used."""
        rid = run_id if run_id is not None else uuid.uuid4()
        events: List[ProvenanceEventEnvelope] = []
        edges: List[ProvenanceEdge] = []

        def append(payload_dict: Dict[str, object], type_identifier: str, priority: int) -> uuid.UUID:
            envelope = ProvenanceEventEnvelope(
                id=uuid.uuid4(),
                run_id=rid,
                context_id=self.context_id,
                engine_name=self.engine_name,
                schema_version=self.schema_version,
                sequence=len(events),
                payload=ErasedProvenancePayload(
                    type_identifier=type_identifier,
                    priority_value=priority,
                    raw_json=canonical_json(payload_dict),
                ),
                timestamp=report.created_at,
            )
            events.append(envelope)
            return envelope.id

        verdict_event_ids: List[uuid.UUID] = []
        for verdict in report.verdicts:
            extracted_id = append(
                _claim_extracted_payload(verdict), CLAIM_EXTRACTED, PRIORITY_STRUCTURAL
            )
            verified_id = append(
                _claim_verified_payload(verdict), CLAIM_VERIFIED, PRIORITY_CRITICAL
            )
            edges.append(
                ProvenanceEdge(source_id=extracted_id, target_id=verified_id, type=EDGE_VERIFIED_BY)
            )
            verdict_event_ids.append(verified_id)

        report_event_id = append(
            _report_finalized_payload(report, policy), REPORT_FINALIZED, PRIORITY_CRITICAL
        )
        for verdict_event_id in verdict_event_ids:
            edges.append(
                ProvenanceEdge(source_id=verdict_event_id, target_id=report_event_id, type=EDGE_DERIVED_FROM)
            )

        return ProvenanceTrace(
            events=events,
            edges=edges,
            run_fingerprint=run_fingerprint_of(events),
            report_fingerprint=report_fingerprint(report),
            policy_fingerprint=policy_fingerprint(policy),
            engine_name=self.engine_name,
            context_id=self.context_id,
        )

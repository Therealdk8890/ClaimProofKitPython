# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: BUSL-1.1

"""claimproofkit — evidence-bound claim verification.

Python implementation of Claim Proof Specification v1, in locked parity with
the Swift ClaimProofKit (the reference implementation). Parity is proved by
the conformance runner under ``conformance/``, which executes the same golden
vectors the Swift repo locks in CI.
"""

from .extractor import ClaimExtractor
from .identity import (
    SPEC_VERSION,
    VERIFIER_IDENTIFIER,
    VERIFIER_VERSION,
    canonical_json,
    evidence_content_fingerprint,
    policy_fingerprint,
    report_fingerprint,
)
from .models import (
    APPROVED_STATUSES,
    Claim,
    ClaimType,
    ClaimVerdict,
    EvidenceMatch,
    EvidencePassage,
    ProofReport,
    SourceType,
    SupportStatus,
    VerificationPolicy,
    make_claim_fingerprint,
)
from .provenance import (
    BRIDGE_VERSION,
    CLAIM_EXTRACTED,
    CLAIM_VERIFIED,
    REPORT_FINALIZED,
    ProvenanceEdge,
    ProvenanceEventEnvelope,
    ProvenanceExporter,
    ProvenanceTrace,
    run_fingerprint_of,
)
from .pipeline import (
    AtomicClaimExtracting,
    ClaimEntailmentVerifying,
    ConservativeProofPolicy,
    DefaultTrustReportGenerator,
    Disposition,
    EvidenceRetrieving,
    LexicalEntailmentVerifier,
    PassthroughEvidenceRetriever,
    PipelineResult,
    ProofDecision,
    ProofPolicyEvaluating,
    TrustReportGenerating,
    VerificationPipeline,
)
from .verifier import ClaimVerifier

__version__ = "0.1.0"

__all__ = [
    "APPROVED_STATUSES",
    "BRIDGE_VERSION",
    "CLAIM_EXTRACTED",
    "CLAIM_VERIFIED",
    "REPORT_FINALIZED",
    "SPEC_VERSION",
    "VERIFIER_IDENTIFIER",
    "VERIFIER_VERSION",
    "Claim",
    "ClaimExtractor",
    "ClaimType",
    "ClaimVerdict",
    "ClaimVerifier",
    "EvidenceMatch",
    "EvidencePassage",
    "ProofReport",
    "ProvenanceEdge",
    "ProvenanceEventEnvelope",
    "ProvenanceExporter",
    "ProvenanceTrace",
    "SourceType",
    "SupportStatus",
    "VerificationPolicy",
    "canonical_json",
    "evidence_content_fingerprint",
    "make_claim_fingerprint",
    "policy_fingerprint",
    "report_fingerprint",
    "run_fingerprint_of",
]

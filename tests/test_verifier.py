# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: BUSL-1.1

"""Port of the Swift `ClaimProofKitTests` verdict tests."""

from claimproofkit import (
    Claim,
    ClaimType,
    ClaimVerifier,
    EvidencePassage,
    SourceType,
    SupportStatus,
)

EVIDENCE = [
    EvidencePassage(
        id="rule-5",
        source="Local Rule 5",
        source_type=SourceType.COURT_RULE,
        text="A response must be filed within 14 days after service of the motion.",
    ),
    EvidencePassage(
        id="order-1",
        source="Scheduling Order",
        source_type=SourceType.COURT_RECORD,
        text="The court denied the request for an extension.",
    ),
]


def test_directly_grounded_claim_is_supported():
    claim = Claim(
        id="1",
        text="The response must be filed within 14 days after service of the motion.",
        type=ClaimType.LEGAL_RULE,
    )
    result = ClaimVerifier().verify(claim, EVIDENCE)
    assert result.status == SupportStatus.DIRECTLY_SUPPORTED
    assert result.evidence[0].passage.id == "rule-5"


def test_polarity_reversal_is_contradicted():
    claim = Claim(
        id="2", text="The court did not deny the request for an extension.", type=ClaimType.FACTUAL
    )
    result = ClaimVerifier().verify(claim, EVIDENCE)
    assert result.status == SupportStatus.CONTRADICTED


def test_invented_fact_is_unsupported():
    claim = Claim(
        id="3", text="The plaintiff filed a second amended complaint.", type=ClaimType.FACTUAL
    )
    result = ClaimVerifier().verify(claim, EVIDENCE)
    assert result.status == SupportStatus.UNSUPPORTED


def test_recommendation_is_not_verifiable():
    claim = Claim(
        id="4", text="You should file a motion to compel.", type=ClaimType.RECOMMENDATION
    )
    result = ClaimVerifier().verify(claim, EVIDENCE)
    assert result.status == SupportStatus.NOT_VERIFIABLE


def test_evidence_ranking_tie_break_is_deterministic():
    twin_a = EvidencePassage(id="a-passage", source="A", text="The tenant paid rent in March.")
    twin_b = EvidencePassage(id="b-passage", source="B", text="The tenant paid rent in March.")
    claim = Claim(id="5", text="The tenant paid rent in March.", type=ClaimType.FACTUAL)
    result = ClaimVerifier().verify(claim, [twin_b, twin_a])
    assert result.evidence[0].passage.id == "a-passage"


def test_mixed_document_blocks_publication():
    verifier = ClaimVerifier()
    report = verifier.verify_document(
        "The court denied the request for an extension. The plaintiff filed a second amended complaint.",
        EVIDENCE,
    )
    assert not report.is_safe_to_publish
    statuses = [v.status for v in report.verdicts]
    assert SupportStatus.DIRECTLY_SUPPORTED in statuses
    assert SupportStatus.UNSUPPORTED in statuses


def test_empty_document_is_not_safe_to_publish():
    report = ClaimVerifier().verify_document("", EVIDENCE)
    assert report.verdicts == ()
    assert not report.is_safe_to_publish
    assert report.support_rate == 0.0


def test_document_without_extractable_claims_is_not_safe_to_publish():
    report = ClaimVerifier().verify_document("?", EVIDENCE)
    assert report.verdicts == ()
    assert not report.is_safe_to_publish
    assert report.support_rate == 0.0

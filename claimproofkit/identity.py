# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: Apache-2.0

"""Claim Proof Specification v1 identity algorithms.

Mirrors the Swift `ProofIdentity.swift` byte-for-byte. Every function here is
locked by the golden vectors vendored under ``conformance/vectors`` (whose
source of truth is the Swift repo's ConformanceHarness).
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .models import EvidencePassage, ProofReport, VerificationPolicy

SPEC_VERSION = "1.0"
VERIFIER_IDENTIFIER = "cpk-lexical"
VERIFIER_VERSION = "1.0"


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def swift_number(value: Any) -> str:
    """Render a number the way Swift's ``JSONEncoder`` does.

    Integral Doubles print without a fractional part (``Double(1)`` → ``"1"``)
    up to the magnitude where Swift switches to exponent form (1e16); above
    that, and for all non-integral values, Swift uses shortest round-trip
    rendering, which matches Python's ``repr`` for finite floats. Negative
    zero stays ``"-0"``.
    """
    if isinstance(value, bool):  # bool is an int subclass; keep JSON booleans out
        raise TypeError("swift_number does not take booleans")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite numbers are not canonically encodable")
        if value == 0 and math.copysign(1, value) < 0:
            return "-0"
        if value.is_integer() and abs(value) < 1e16:
            return str(int(value))
        return repr(value)
    raise TypeError(f"not a number: {value!r}")


def swift_interpolation(value: Any) -> str:
    """Render a number the way Swift STRING INTERPOLATION does — distinct from
    JSON encoding: ``"\\(Double(1))"`` is ``"1.0"``, not ``"1"``. Python's
    ``repr`` for floats matches Swift's Double description exactly for the
    shortest-round-trip cases used in fingerprint listings.
    """
    if isinstance(value, bool):
        raise TypeError("swift_interpolation does not take booleans")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite numbers are not interpolatable")
        return repr(value)
    raise TypeError(f"not a number: {value!r}")


def _json_string(text: str) -> str:
    # Swift's JSONEncoder escapes forward slashes by default (the bridge encodes
    # rawJSON with plain .sortedKeys), so the canonical form does too.
    return json.dumps(text, ensure_ascii=False).replace("/", "\\/")


def _canonical_fragment(value: Any) -> str:
    if isinstance(value, str):
        return _json_string(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return swift_number(value)
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda kv: kv[0])
        inner = ",".join(f"{_json_string(k)}:{_canonical_fragment(v)}" for k, v in items)
        return "{" + inner + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_canonical_fragment(v) for v in value) + "]"
    if value is None:
        return "null"
    raise TypeError(f"not canonically encodable: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Canonical payload encoding (Spec §2): sorted keys, UTF-8, no extra
    whitespace, Swift number rendering. Byte-identical to Swift's
    ``JSONEncoder`` with ``.sortedKeys`` for the payload types used on the wire.
    """
    return _canonical_fragment(value)


def evidence_content_fingerprint(passage: EvidencePassage) -> str:
    """Spec §5: SHA-256 over the exact UTF-8 bytes of the passage text."""
    return sha256_hex(passage.text)


def report_fingerprint(report: ProofReport) -> str:
    """Spec §3: SHA-256 over the domain-separated verdict signature string."""
    signature = "".join(f"{v.claim.fingerprint}:{v.status.value}|" for v in report.verdicts)
    return sha256_hex("cpk:v1:report:" + signature)


def policy_fingerprint(
    policy: VerificationPolicy,
    verifier: str = VERIFIER_IDENTIFIER,
    verifier_version: str = VERIFIER_VERSION,
) -> str:
    """Spec §4: SHA-256 over the frozen newline-delimited key:value listing.

    The Swift reference builds this listing with STRING INTERPOLATION (not
    JSONEncoder), so integral thresholds render as ``1.0``, never ``1``.
    """
    canonical = "\n".join(
        [
            f"specVersion:{SPEC_VERSION}",
            f"verifier:{verifier}",
            f"verifierVersion:{verifier_version}",
            f"supportedThreshold:{swift_interpolation(float(policy.supported_threshold))}",
            f"ambiguousThreshold:{swift_interpolation(float(policy.ambiguous_threshold))}",
            f"contradictionThreshold:{swift_interpolation(float(policy.contradiction_threshold))}",
            f"maximumEvidenceMatches:{policy.maximum_evidence_matches}",
        ]
    )
    return sha256_hex(canonical)

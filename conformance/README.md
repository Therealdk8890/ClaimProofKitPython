# Claim Proof Specification v1 conformance (Python)

This directory proves the Python implementation is in **locked parity** with
the Swift ClaimProofKit — the reference implementation of Claim Proof
Specification v1 — by executing the same golden vectors the Swift repo locks
in CI (`ClaimProofKit/ConformanceHarness/vectors`, vendored here via
`sync-vectors.sh`).

Every check is byte-exact: claim/policy/report fingerprints, verifier
verdicts, canonical payload JSON, and the DProvenanceKit run fingerprint.
When the `dprovenancekit` Python package is importable, the runner
additionally records the bridge trace through its real SQLite store and
asserts the store reproduces the bridge's run fingerprint — the same
round-trip the Swift harness performs against the Swift DProvenanceKit.

```sh
python conformance/run_conformance.py          # exit 0 pass, 1 fail
conformance/sync-vectors.sh                    # re-vendor from the Swift repo
```

The spec itself lives in the Swift repo: `ClaimProofKit/Docs/PROOF_SPEC_V1.md`.
Behavior changes originate there (with a spec-version bump and regenerated
vectors); this repo then re-syncs and conforms.

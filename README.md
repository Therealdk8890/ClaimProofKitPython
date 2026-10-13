# ClaimProofKitPython

Python implementation of **Claim Proof Specification v1** — evidence-bound
claim verification that blocks generated documents whose material claims the
supplied evidence does not support. Pure standard library, zero dependencies.

The Swift [ClaimProofKit](https://github.com/Therealdk8890/ClaimProofKit) is the reference
implementation; this package is held in **locked parity** with it by the
golden vectors under `conformance/vectors` (vendored from the Swift repo's
ConformanceHarness). Every fingerprint, verifier verdict, and canonical
payload byte is identical across both implementations — CI fails on any
drift, in either repo.

```sh
pip install -e ".[dev]"
pytest
python conformance/run_conformance.py
```

## Verify a document

A document with no extractable material claims is **not** considered safe to publish. A successful verification gate requires at least one claim, and every extracted claim must have an approved verdict. This avoids treating an empty or unrecognized document as verified by vacuous success.

```python
from claimproofkit import ClaimVerifier, EvidencePassage, SourceType

evidence = [
    EvidencePassage(
        id="order-1",
        source="Scheduling Order",
        source_type=SourceType.COURT_RECORD,
        text="The court denied the request for an extension.",
    )
]
report = ClaimVerifier().verify_document(
    "The court denied the request for an extension.", evidence
)
assert report.is_safe_to_publish
```

Or from the CLI, with the same command semantics and exit codes as the Swift binary
(0 published, 2 blocked, 3 benchmark gate failed, 64 usage, 65 unreadable
input, 73 trace write failed):

```sh
claimproofkit verify input.json [--provenance trace.json]
claimproofkit benchmark corpus.json [--json]
```

## Working with DProvenanceKit

`claimproofkit.provenance` exports a verification run as a
DProvenanceKit-compatible trace, identical to the Swift bridge's output:
stable `cpk_*` event vocabulary, canonical payload bytes (Trace Specification
v1 §2), lineage edges, and the §5 run fingerprint.

```python
from claimproofkit import ProvenanceExporter, VerificationPolicy

trace = ProvenanceExporter().trace(report, VerificationPolicy())
trace.events_json()    # decodes as [TraceEvent<AnyTraceableEvent>] in Swift DProvenanceKit
trace.manifest_json()  # full manifest with fingerprints and edges
```

The conformance runner proves the fingerprint against the real Python
[`dprovenancekit`](https://github.com/Therealdk8890/DProvenanceKitPython)
package when it is importable: recording the trace through its SQLite store
reproduces the bridge's run fingerprint byte-for-byte. The same trace
fingerprints identically in Swift ClaimProofKit, Swift DProvenanceKit, and
Python dprovenancekit.

## Changing locked behavior

Spec changes originate in the Swift repo (`Docs/PROOF_SPEC_V1.md`): bump the
spec/verifier version there, regenerate vectors, then re-sync here with
`conformance/sync-vectors.sh` and update this implementation to conform.

ClaimProofKitPython is source-available under the [Business Source License
1.1](LICENSE). Non-production evaluation, development, testing, and personal
study are permitted. Production use requires a separate commercial license
until the Change Date, when that version converts to Apache 2.0. See
[Commercial licensing](COMMERCIAL_LICENSING.md).

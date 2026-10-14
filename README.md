# ClaimProofKit — Python implementation

**Apache-2.0 licensed** · Evidence-bound claim verification · Zero runtime dependencies

ClaimProofKit implements **Claim Proof Specification v1**: it checks whether the material claims in a generated document are supported by supplied evidence, and blocks publication when claims are unsupported or when no material claims can be extracted. It uses only the Python standard library at runtime.

The Swift [ClaimProofKit](https://github.com/Therealdk8890/ClaimProofKit) is the reference implementation. This Python implementation is held in **locked parity** with it through the golden vectors under `conformance/vectors`. Fingerprints, verifier verdicts, and canonical payload bytes are checked across both implementations.

## License

ClaimProofKit is licensed under the [Apache License, Version 2.0](LICENSE). You may use, modify, distribute, and include it in commercial products subject to the license terms. **No separate production-use license is required.** See [NOTICE](NOTICE) and [Licensing and commercial use](COMMERCIAL_LICENSING.md).

The Apache-2.0 license applies to the code in this repository; it does not grant rights to project trademarks or imply endorsement.

## Install and test

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

The CLI exposes the same command semantics and exit codes as the Swift binary (0 published, 2 blocked, 3 benchmark gate failed, 64 usage, 65 unreadable input, 73 trace write failed):

```sh
claimproofkit verify input.json [--provenance trace.json]
claimproofkit benchmark corpus.json [--json]
```

## Working with DProvenanceKit

`claimproofkit.provenance` exports a verification run as a DProvenanceKit-compatible trace, identical to the Swift bridge's output: stable `cpk_*` event vocabulary, canonical payload bytes (Trace Specification v1 §2), lineage edges, and the §5 run fingerprint.

```python
from claimproofkit import ProvenanceExporter, VerificationPolicy

trace = ProvenanceExporter().trace(report, VerificationPolicy())
trace.events_json()    # decodes as [TraceEvent<AnyTraceableEvent>] in Swift DProvenanceKit
trace.manifest_json()  # full manifest with fingerprints and edges
```

The conformance runner proves the fingerprint against the real Python [dprovenancekit](https://github.com/Therealdk8890/DProvenanceKitPython) package when it is importable: recording the trace through its SQLite store reproduces the bridge's run fingerprint byte-for-byte. The same trace fingerprints identically in Swift ClaimProofKit, Swift DProvenanceKit, and Python dprovenancekit.

## Changing locked behavior

Specification changes originate in the Swift repo ([`Docs/PROOF_SPEC_V1.md`](https://github.com/Therealdk8890/ClaimProofKit/blob/main/Docs/PROOF_SPEC_V1.md)): bump the spec/verifier version there, regenerate vectors, then re-sync here with `conformance/sync-vectors.sh` and update this implementation to conform.

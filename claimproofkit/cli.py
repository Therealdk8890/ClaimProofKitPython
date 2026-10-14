# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: Apache-2.0

"""claimproofkit CLI — mirrors the Swift executable's commands and exit codes.

Exit codes: 0 published / gate passed, 2 blocked, 3 benchmark gate failed,
64 usage, 65 unreadable input, 73 provenance trace write failed.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import List, Optional

from .benchmark import BenchmarkCorpus, BenchmarkRunner
from .models import EvidencePassage, SourceType, VerificationPolicy
from .provenance import ProvenanceExporter
from .report import benchmark_report_json, render_benchmark_markdown, render_report_markdown
from .verifier import ClaimVerifier

USAGE = """Usage:
  claimproofkit verify <input.json|folder> [--provenance <trace.json|trace-folder>]
  claimproofkit benchmark <corpus.json> [--json]

When input is a folder, ClaimProofKit verifies each top-level *.json file in
filename order. Each JSON file must use the normal single-document input
schema. All files are processed; the command fails closed if any file is
unreadable or any report is blocked. With folder input, --provenance names an
output folder and each trace is written as <input-stem>.trace.json.

--provenance writes a DProvenanceKit-compatible trace manifest of the
verification run alongside the report.

Exit codes: 0 published, 2 blocked, 3 benchmark gate failed,
64 usage, 65 unreadable input, 73 provenance trace write failed.

Backward compatibility: claimproofkit <input.json> runs verification.
"""


def _usage(code: int) -> int:
    sys.stderr.write(USAGE)
    return code


def _read_and_verify(path: str):
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    evidence = [
        EvidencePassage(
            id=p["id"],
            source=p["source"],
            source_type=SourceType(p["sourceType"]),
            text=p["text"],
        )
        for p in data["evidence"]
    ]
    policy = VerificationPolicy()
    report = ClaimVerifier(policy).verify_document(data["document"], evidence, created_at=time.time())
    return report, policy


def _run_verification(path: str, provenance_path: Optional[str]) -> int:
    try:
        report, policy = _read_and_verify(path)
    except Exception as error:  # noqa: BLE001 - CLI boundary
        sys.stderr.write(f"claimproofkit: failed to verify {path}: {error}\n")
        return 65

    # The report is always emitted, even if the trace write fails afterwards.
    print(render_report_markdown(report))
    if provenance_path is not None:
        try:
            trace = ProvenanceExporter().trace(report, policy)
            with open(provenance_path, "w", encoding="utf-8") as handle:
                handle.write(trace.manifest_json())
            sys.stderr.write(
                f"provenance trace written to {provenance_path} (run fingerprint {trace.run_fingerprint})\n"
            )
        except Exception as error:  # noqa: BLE001 - CLI boundary
            sys.stderr.write(f"claimproofkit: failed to write provenance trace to {provenance_path}: {error}\n")
            return 73
    return 0 if report.is_safe_to_publish else 2


def _run_verification_folder(folder_path: str, provenance_path: Optional[str]) -> int:
    folder = Path(folder_path)
    try:
        if not folder.is_dir():
            raise NotADirectoryError(f"not a directory: {folder}")
        # Snapshot inputs before writing any provenance traces.
        inputs = sorted(
            (entry for entry in folder.iterdir() if entry.is_file() and entry.suffix == ".json"),
            key=lambda entry: entry.name,
        )
    except Exception as error:  # noqa: BLE001 - CLI boundary
        sys.stderr.write(f"claimproofkit: cannot read input folder {folder}: {error}\n")
        return 65

    if not inputs:
        sys.stderr.write(f"claimproofkit: no top-level .json documents found in {folder}\n")
        return 65

    trace_folder: Optional[Path] = None
    if provenance_path is not None:
        trace_folder = Path(provenance_path)
        try:
            if trace_folder.resolve() == folder.resolve():
                sys.stderr.write("claimproofkit: provenance output folder must differ from the input folder\n")
                return 64
            trace_folder.mkdir(parents=True, exist_ok=True)
            if not trace_folder.is_dir():
                raise NotADirectoryError(str(trace_folder))
        except Exception as error:  # noqa: BLE001 - CLI boundary
            sys.stderr.write(f"claimproofkit: cannot prepare provenance output folder {trace_folder}: {error}\n")
            return 73

    results = []
    for path in inputs:
        print(f"\n## Document: {path.name}\n")
        trace_path = str(trace_folder / f"{path.stem}.trace.json") if trace_folder is not None else None
        results.append((path.name, _run_verification(str(path), trace_path)))

    passed = sum(code == 0 for _, code in results)
    blocked = sum(code == 2 for _, code in results)
    unreadable = sum(code == 65 for _, code in results)
    trace_errors = sum(code == 73 for _, code in results)
    print(
        f"\n## Folder summary\n\n"
        f"Documents: {len(results)} · Safe to publish: {passed} · "
        f"Blocked: {blocked} · Unreadable: {unreadable} · Trace errors: {trace_errors}"
    )

    # A folder is successful only when every document passes and every requested
    # trace is written. Input errors and trace errors must not be hidden by a pass.
    if trace_errors:
        return 73
    if unreadable:
        return 65
    if blocked:
        return 2
    return 0


def _run_benchmark(path: str, as_json: bool) -> int:
    try:
        with open(path, encoding="utf-8") as handle:
            corpus = BenchmarkCorpus.from_dict(json.load(handle))
    except Exception as error:  # noqa: BLE001 - CLI boundary
        sys.stderr.write(f"claimproofkit: {error}\n")
        return 65
    report = BenchmarkRunner().run(corpus)
    print(benchmark_report_json(report) if as_json else render_benchmark_markdown(report))
    return 0 if report.passes_safety_gate else 3


def main(argv: Optional[List[str]] = None) -> int:
    # The Swift CLI writes UTF-8 bytes unconditionally; without this, a
    # non-UTF-8 stdout (e.g. cp1252) crashes mid-print with exit 1 and breaks
    # the documented exit-code contract.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--help" in arguments or "-h" in arguments:
        sys.stderr.write(USAGE)
        return 0
    if not arguments:
        return _usage(64)

    command = arguments[0]
    if command == "verify":
        path: Optional[str] = None
        provenance: Optional[str] = None
        rest = arguments[1:]
        while rest:
            argument = rest.pop(0)
            if argument == "--provenance":
                if provenance is not None or not rest:
                    return _usage(64)
                provenance = rest.pop(0)
            elif path is None:
                path = argument
            else:
                return _usage(64)
        if path is None:
            return _usage(64)
        if Path(path).is_dir():
            return _run_verification_folder(path, provenance)
        return _run_verification(path, provenance)
    if command == "benchmark":
        rest = arguments[1:]
        if len(rest) == 1:
            return _run_benchmark(rest[0], as_json=False)
        if len(rest) == 2 and rest[1] == "--json":
            return _run_benchmark(rest[0], as_json=True)
        return _usage(64)
    if len(arguments) == 1:
        # Backward compatibility: a lone path runs verification.
        path = arguments[0]
        if Path(path).is_dir():
            return _run_verification_folder(path, None)
        return _run_verification(path, None)
    return _usage(64)


if __name__ == "__main__":
    raise SystemExit(main())

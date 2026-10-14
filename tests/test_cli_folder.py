# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: Apache-2.0

"""Folder-mode CLI tests."""

import json
import os
import subprocess
import sys
from pathlib import Path


def _write_input(path: Path, document: str) -> None:
    path.write_text(
        json.dumps(
            {
                "document": document,
                "evidence": [
                    {
                        "id": "order-1",
                        "source": "Scheduling Order",
                        "sourceType": "courtRecord",
                        "text": "The court denied the request for an extension.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _run(folder: Path, *extra: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "claimproofkit.cli", "verify", str(folder), *extra],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )


def test_folder_verification_processes_json_in_filename_order_and_passes(tmp_path: Path):
    _write_input(tmp_path / "b.json", "The court denied the request for an extension.")
    _write_input(tmp_path / "a.json", "The court denied the request for an extension.")
    (tmp_path / "notes.txt").write_text("not an input", encoding="utf-8")

    result = _run(tmp_path)

    assert result.returncode == 0
    assert result.stdout.index("Document: a.json") < result.stdout.index("Document: b.json")
    assert "Documents: 2 · Safe to publish: 2 · Blocked: 0" in result.stdout


def test_folder_verification_fails_closed_when_any_document_is_blocked(tmp_path: Path):
    _write_input(tmp_path / "supported.json", "The court denied the request for an extension.")
    _write_input(tmp_path / "unsupported.json", "The plaintiff filed a second amended complaint.")

    result = _run(tmp_path)

    assert result.returncode == 2
    assert "Safe to publish: 1 · Blocked: 1" in result.stdout
    assert "Document: supported.json" in result.stdout
    assert "Document: unsupported.json" in result.stdout


def test_folder_verification_continues_after_unreadable_document(tmp_path: Path):
    _write_input(tmp_path / "a-good.json", "The court denied the request for an extension.")
    (tmp_path / "b-bad.json").write_text("{not json", encoding="utf-8")
    _write_input(tmp_path / "c-good.json", "The court denied the request for an extension.")

    result = _run(tmp_path)

    assert result.returncode == 65
    assert "Document: c-good.json" in result.stdout
    assert "Unreadable: 1" in result.stdout
    assert "failed to verify" in result.stderr


def test_folder_verification_rejects_empty_folder(tmp_path: Path):
    result = _run(tmp_path)

    assert result.returncode == 65
    assert "no top-level .json documents found" in result.stderr


def test_folder_provenance_writes_one_trace_per_input(tmp_path: Path):
    _write_input(tmp_path / "a.json", "The court denied the request for an extension.")
    _write_input(tmp_path / "b.json", "The court denied the request for an extension.")
    trace_folder = tmp_path / "traces"

    result = _run(tmp_path, "--provenance", str(trace_folder))

    assert result.returncode == 0
    assert (trace_folder / "a.trace.json").is_file()
    assert (trace_folder / "b.trace.json").is_file()

# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: BUSL-1.1

"""The conformance suite IS the parity contract — run it under pytest too."""

import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent


def test_conformance_vectors_pass():
    result = subprocess.run(
        [sys.executable, str(REPO / "conformance" / "run_conformance.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"conformance failed:\n{result.stdout}\n{result.stderr}"
    assert "All conformance checks passed." in result.stdout

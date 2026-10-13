#!/usr/bin/env bash
# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: Apache-2.0
#
# Re-sync the Claim Proof Specification v1 vectors from the canonical Swift repo,
# then show what changed. The Swift ClaimProofKit is the source of truth (the
# reference implementation); this directory keeps a vendored copy so the Python
# conformance runner stays self-contained.
#
#   conformance/sync-vectors.sh [path-to-swift-vectors]
#   CPK_SWIFT_VECTORS=/path/to/vectors conformance/sync-vectors.sh
set -euo pipefail
SRC="${1:-${CPK_SWIFT_VECTORS:-$HOME/ClaimProofKit/ConformanceHarness/vectors}}"
DEST="$(cd "$(dirname "$0")" && pwd)/vectors"
if [ ! -d "$SRC" ]; then
    echo "canonical vectors not found: $SRC" >&2
    echo "pass the path as an argument or set CPK_SWIFT_VECTORS." >&2
    exit 1
fi
cp "$SRC"/*.json "$DEST"/
echo "synced vectors from: $SRC"
git -C "$DEST" status --short -- . 2>/dev/null || true

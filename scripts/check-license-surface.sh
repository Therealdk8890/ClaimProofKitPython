#!/usr/bin/env bash
# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: BUSL-1.1

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

required_license_lines=(
    'Business Source License 1.1'
    'Licensor:             Daniel Kissel'
    'Licensed Work:        ClaimProofKitPython'
    'Additional Use Grant: None'
    'Change Date:          2030-08-11'
    'Change License:       Apache License, Version 2.0'
)

for line in "${required_license_lines[@]}"; do
    if ! grep -Fqx "$line" LICENSE; then
        printf 'license surface check failed: LICENSE is missing: %s\n' "$line" >&2
        exit 1
    fi
done

missing_header=0
while IFS= read -r path; do
    if ! grep -Fq 'SPDX-License-Identifier: BUSL-1.1' "$path"; then
        printf 'license surface check failed: missing BUSL-1.1 header: %s\n' "$path" >&2
        missing_header=1
    fi
done < <(
    find claimproofkit tests conformance scripts \
        -type f \( -name '*.py' -o -name '*.sh' \) -print | sort
)

if [[ "$missing_header" -ne 0 ]]; then
    exit 1
fi

stale_matches=$(git grep -nE \
    'Licensed under the Apache License|license = "Apache-2.0"' \
    -- ':!LICENSE' ':!scripts/check-license-surface.sh' || true)

if [[ -n "$stale_matches" ]]; then
    printf '%s\n' "$stale_matches" >&2
    printf 'license surface check failed: stale Apache licensing wording found\n' >&2
    exit 1
fi

if ! grep -Fqx 'license = "BUSL-1.1"' pyproject.toml; then
    printf 'license surface check failed: pyproject.toml is not BUSL-1.1\n' >&2
    exit 1
fi

if ! grep -Fq 'source-available under the [Business Source License' README.md; then
    printf 'license surface check failed: README does not identify BUSL-1.1\n' >&2
    exit 1
fi

printf 'BUSL-1.1 license surface check passed.\n'

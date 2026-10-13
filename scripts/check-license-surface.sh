#!/usr/bin/env bash
# Copyright 2026 Daniel Kissel
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

if ! grep -Fq 'Apache License' LICENSE || ! grep -Fq 'Version 2.0' LICENSE; then
    printf 'license surface check failed: LICENSE is not Apache-2.0\n' >&2
    exit 1
fi

if ! grep -Fqx 'license = "Apache-2.0"' pyproject.toml; then
    printf 'license surface check failed: pyproject.toml is not Apache-2.0\n' >&2
    exit 1
fi

if ! grep -Fq 'licensed under the [Apache License, Version 2.0]' README.md; then
    printf 'license surface check failed: README does not identify Apache-2.0\n' >&2
    exit 1
fi

if git grep -nE 'BUSL-1\.1|Business Source License 1\.1|source-available under the Business Source License' -- ':!LICENSE' ':!COMMERCIAL_LICENSING.md'; then
    printf 'license surface check failed: stale BUSL licensing wording found\n' >&2
    exit 1
fi

printf 'Apache-2.0 license surface check passed.\n'

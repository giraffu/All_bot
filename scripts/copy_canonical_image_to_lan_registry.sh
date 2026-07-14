#!/usr/bin/env bash
set -euo pipefail

execute=false
source_ref=""
destination_ref=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --source) source_ref="${2:?missing --source value}"; shift 2 ;;
        --destination) destination_ref="${2:?missing --destination value}"; shift 2 ;;
        --execute) execute=true; shift ;;
        -h|--help)
            echo "Usage: $0 --source <canonical@sha256:...> --destination <lan-registry/repo:tag> [--execute]"
            exit 0
            ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

if [[ ! "$source_ref" =~ @sha256:[0-9a-f]{64}$ ]]; then
    echo "source must be a canonical digest-pinned image" >&2
    exit 2
fi
if [ -z "$destination_ref" ] || [[ "$destination_ref" == *@* ]]; then
    echo "destination must be a LAN registry repository:tag" >&2
    exit 2
fi
command -v crane >/dev/null 2>&1 || {
    echo "crane is required to preserve the canonical manifest" >&2
    exit 2
}

expected_digest="${source_ref##*@}"
if [ "$execute" != true ]; then
    echo "[dry-run] crane copy canonical digest to LAN registry"
    echo "[dry-run] verify destination digest equals ${expected_digest}"
    exit 0
fi

crane copy "$source_ref" "$destination_ref"
actual_digest="$(crane digest "$destination_ref")"
if [ "$actual_digest" != "$expected_digest" ]; then
    echo "LAN registry digest mismatch: expected ${expected_digest}, got ${actual_digest}" >&2
    exit 1
fi
echo "LAN registry canonical digest verified: ${actual_digest}"

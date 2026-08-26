#!/bin/sh
set -eu

umask 077
state_path=${STATE_PATH:-/state}
mkdir -p "$state_path"
date -u +%Y-%m-%dT%H:%M:%SZ > "$state_path/reauth-required"
echo "iCloud authentication renewal is required" >&2


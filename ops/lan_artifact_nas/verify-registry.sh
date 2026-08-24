#!/usr/bin/env bash
set -euo pipefail

source_registry="${1:-127.0.0.1:5000}"
target_registry="${2:-10.250.150.2:5000}"
command -v crane >/dev/null || { echo "crane is required" >&2; exit 2; }

tmp_dir="$(mktemp -d)"
trap 'find "$tmp_dir" -xdev -depth -mindepth 1 -delete; rmdir "$tmp_dir"' EXIT
crane catalog "$source_registry" --insecure | sort >"$tmp_dir/source-catalog"
crane catalog "$target_registry" --insecure | sort >"$tmp_dir/target-catalog"
diff -u "$tmp_dir/source-catalog" "$tmp_dir/target-catalog"

while IFS= read -r repository; do
  crane ls "${source_registry}/${repository}" --insecure | sort >"$tmp_dir/source-tags"
  crane ls "${target_registry}/${repository}" --insecure | sort >"$tmp_dir/target-tags"
  diff -u "$tmp_dir/source-tags" "$tmp_dir/target-tags"
  while IFS= read -r tag; do
    source_digest="$(crane digest "${source_registry}/${repository}:${tag}" --insecure)"
    target_digest="$(crane digest "${target_registry}/${repository}:${tag}" --insecure)"
    if [ "$source_digest" != "$target_digest" ]; then
      echo "digest mismatch: ${repository}:${tag}" >&2
      exit 1
    fi
  done <"$tmp_dir/source-tags"
done <"$tmp_dir/source-catalog"
echo "registry catalogs, tags, and manifest digests match"


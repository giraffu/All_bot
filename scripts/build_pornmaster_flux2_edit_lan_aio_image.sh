#!/usr/bin/env bash
set -euo pipefail

REGISTRY="${PORNMASTER_FLUX2_EDIT_REGISTRY:-192.168.1.115:5000}"
TAG="${PORNMASTER_FLUX2_EDIT_IMAGE_TAG:-20260627-pornmaster-flux2-edit-cu128-core1}"
IMAGE_REF="${PORNMASTER_FLUX2_EDIT_IMAGE_REF:-${REGISTRY}/allbot/comfy-runpod-pornmaster-flux2-edit:${TAG}}"
BASE_IMAGE="${PORNMASTER_FLUX2_EDIT_BASE_IMAGE:-${REGISTRY}/allbot/comfy-runpod-i2i-pro:20260614-i2ipro-b75c6a9-cu128-min5-ssh}"
PUSH="false"
SMOKE="true"

usage() {
  cat <<'USAGE'
Usage:
  scripts/build_pornmaster_flux2_edit_lan_aio_image.sh [options]

Options:
  --push              Push the image to the LAN registry after build/smoke.
  --no-smoke          Skip the container smoke test.
  --image-ref <ref>   Override target image ref.
  --tag <tag>         Override default LAN registry tag.
  --registry <host>   Override LAN registry host. Default 192.168.1.115:5000.
  --base-image <ref>  Override base image.
  -h, --help          Show this help.

Model weights are not baked into the image. The runtime syncs
allbot-model-cache/pornmaster_flux2_edit/2026-06-27/manifest.json at startup.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --push)
      PUSH="true"
      shift
      ;;
    --no-smoke)
      SMOKE="false"
      shift
      ;;
    --image-ref)
      IMAGE_REF="${2:?missing value for --image-ref}"
      shift 2
      ;;
    --tag)
      TAG="${2:?missing value for --tag}"
      IMAGE_REF="${REGISTRY}/allbot/comfy-runpod-pornmaster-flux2-edit:${TAG}"
      shift 2
      ;;
    --registry)
      REGISTRY="${2:?missing value for --registry}"
      IMAGE_REF="${REGISTRY}/allbot/comfy-runpod-pornmaster-flux2-edit:${TAG}"
      BASE_IMAGE="${BASE_IMAGE/192.168.1.115:5000/${REGISTRY}}"
      shift 2
      ;;
    --base-image)
      BASE_IMAGE="${2:?missing value for --base-image}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

args=(
  --profile pornmaster_flux2_edit
  --image-ref "$IMAGE_REF"
  --base-image "$BASE_IMAGE"
)
if [ "$SMOKE" = "false" ]; then
  args+=(--no-smoke)
fi
if [ "$PUSH" = "true" ]; then
  :
fi

scripts/build_runpod_profile_image.sh "${args[@]}"

if [ "$PUSH" = "true" ]; then
  push_ref="${PORNMASTER_FLUX2_EDIT_PUSH_IMAGE_REF:-}"
  if [ -z "$push_ref" ]; then
    push_ref="$IMAGE_REF"
    if [ "$REGISTRY" != "localhost:5000" ] && [ "$REGISTRY" != "127.0.0.1:5000" ]; then
      if curl -fsS "http://localhost:5000/v2/" >/dev/null 2>&1; then
        push_ref="localhost:5000/${IMAGE_REF#${REGISTRY}/}"
      fi
    fi
  fi
  if [ "$push_ref" != "$IMAGE_REF" ]; then
    docker tag "$IMAGE_REF" "$push_ref"
  fi
  docker push "$push_ref"
fi

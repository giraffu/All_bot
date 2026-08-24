# AllBot GPU Pool Controller v1

This subsystem is dry-run first. It records the LAN GPU pool, model bundles, image
registry targets, and desired worker/task assignments without mutating production
workers or GPU nodes by default.

Useful commands:

```bash
python scripts/gpu_pool_controller.py inventory
python scripts/gpu_pool_controller.py plan
python scripts/gpu_pool_controller.py image-plan \
  --source-image workers_cloud-prod-comfy-agent-1:latest \
  --repository allbot/worker-agent \
  --tag "$(git rev-parse --short HEAD)"
python scripts/gpu_pool_controller.py canary --assignment lan-252-8188-worker-04
python scripts/gpu_pool_controller.py runtime-plan --assignment lan-002-8188-worker-06
python scripts/gpu_pool_controller.py runtime-render --assignment lan-002-8188-worker-06
python scripts/gpu_pool_controller.py runtime-plan \
  --assignment lan-002-8188-worker-06 \
  --profile image_to_video \
  --host-port 8190
python scripts/gpu_pool_controller.py runtime-render \
  --assignment lan-002-8188-worker-06 \
  --profile image_to_video \
  --host-port 8190
python scripts/gpu_pool_controller.py switch-profile \
  --assignment lan-002-8188-worker-06 \
  --profile image_to_video
python scripts/gpu_pool_controller.py workflow-model-check
python scripts/gpu_pool_controller.py model-import-plan
python scripts/gpu_pool_controller.py model-import-execute
python scripts/gpu_pool_controller.py runpod canary \
  --env-file .env.cloud.test \
  --quiet
```

Runtime commands are dry-run first:

- `runtime-plan` emits runtime/image/model/worker-env diffs.
- `runtime-render` renders a standard ComfyUI Docker Compose file for review.
- `runtime-plan` and `runtime-render` accept canary overrides such as
  `--host-port 8190`, `--container-name`, `--api-url`, and `--ws-url`; a host
  port different from the configured production port renders canary metadata
  and leaves the production port unchanged.
- `runtime-apply`, `switch-profile`, and `rollback-profile` accept `--execute`,
  but execution is intentionally disabled until Phase 1 canary validation and a
  maintenance window.
- `host_service` runtimes such as `gpu-226` are observation-only and never render
  Docker runtime operations.

RunPod canary is also dry-run first. The one-command dry-run validates the
RunPod key, managed Pod count, reconcile state, and cloud-test create payload.
Real execution still requires the explicit cost gates and `--execute`:

```bash
RUNPOD_DRY_RUN=false \
RUNPOD_AUTOSCALER_ENABLED=true \
RUNPOD_MAX_PODS_TOTAL=1 \
RUNPOD_MAX_PODS_PER_TYPE=1 \
python scripts/gpu_pool_controller.py runpod canary \
  --env-file .env.cloud.test \
  --prompt "图片中出现一个黑人女性" \
  --download-results-dir /tmp/allbot_runpod_canary/results \
  --execute
```

It only targets cloud-test. For `img2img_lora` it creates one Pod, uploads one
generated PNG, runs three `img2img/img2img_lora` tasks, restores test workers,
deletes the Pod, and checks for post-cleanup orphans. For profile-specific
canaries use `--task-type`; SCAIL-2 uses two inputs and two 5s Web tasks:

```bash
python scripts/prepare_scail2_model_r2_bundle.py --env-file .env.cloud.test
python scripts/gpu_pool_controller.py runpod render-create --task-type scail2 --env cloud-test
python scripts/gpu_pool_controller.py runpod canary --task-type scail2 --env-file .env.cloud.test --quiet
```

`prepare_scail2_model_r2_bundle.py --execute` writes only to
`allbot-model-cache/scail2/2026-06-17-test`; RunPod SCAIL-2 user inputs and
results use `user-data-test` for cloud-test and `user-data-prod` for
cloud-prod.

Formal SCAIL-2 RunPod workers use the same model cache bundle but a prod
manual worker profile:

```bash
RUNPOD_IMAGE_NAME_SCAIL2=ghcr.io/giraffu/allbot-comfy-runpod-scail2:<prod-tag> \
python scripts/gpu_pool_controller.py runpod prod-worker render --profile scail2 --slot 01
scripts/runpod_prod_ops.sh add --profile scail2 --count 1 --execute
scripts/runpod_prod_ops.sh canary --profile scail2 --slot 01 --execute
scripts/runpod_prod_ops.sh enable --profile scail2 --slot 01 --execute
```

Formal LTX RunPod workers use the `ltx_video` profile, the public GHCR
profile image, and the `ltx_video/2026-06-10` model manifest. They default to
the 10Eros v1.2 workflow override and stay disabled after canary until
explicitly enabled:

```bash
RUNPOD_IMAGE_NAME_LTX_VIDEO=ghcr.io/giraffu/allbot-comfy-runpod-ltx-video-v2:<prod-tag> \
python scripts/gpu_pool_controller.py runpod prod-worker render --profile ltx_video --slot 01
scripts/runpod_prod_ops.sh up --profile ltx_video --slot 01 --retry-unavailable --execute
scripts/runpod_prod_ops.sh canary --profile ltx_video --slot 01 --execute
scripts/runpod_prod_ops.sh enable --profile ltx_video --slot 01 --execute
```

Model registry layout:

```text
/srv/allbot/model-registry
  blobs/sha256/<prefix>/<sha256>
  bundles/<bundle>/<version>/manifest.yml
```

`model-import-plan` / `model-import-execute` derive bundle manifests from the
runtime workflow files. For bundles whose workers use
`TASK_TYPE_WORKFLOW_OVERRIDES`, the import spec must carry the same override
mapping; otherwise the plan would pull models from the legacy default workflow
instead of the workflow that actually receives tasks. The current
`i2i_pro_baseline` covers `i2i_pro`, `t2i-pornmaster-turbo` via
`txt2img_from_i2i_pro.json`, and both `face_swap_v2` and legacy `face_swap` via
`face_swap_v2.json` with the same six Flux2/Z-Image model files. The legacy
business task remains distinct for pricing and history, while every current
LAN/RunPod execution profile maps both face-swap task types to
`face_swap_v2.json`.

LAN model cache uses the dedicated MinIO service at `192.168.1.115:9010` with
bucket `allbot-model-cache`; do not reuse runtime `user-data-*` buckets.
The endpoint may be a compatibility proxy to the NAS-local service declared in
`ops/lan_artifact_nas/`; workers must continue using the established endpoint
and digest-addressed manifests. The model source registry may be a hard NFS mount
from the same NAS at `/srv/allbot/model-registry`, but runtime model workspaces
remain local to each GPU node.
Use a redacted loader for `.env.lan.model-cache`. The all-task helper builds
canonical manifests on top of a shared object pool:

```bash
python scripts/upload_all_task_models_to_lan_cache.py \
  --env-file .env.lan.model-cache
```

The current LAN cache has manifests for `img2img_lora/2026-06-10`,
`i2i_pro/2026-06-14-test`, `scail2/2026-06-17-test`, and
`ltx_video/2026-06-10` (including both the old v1 LTX main model and
10Eros v1.2). The all-task target set additionally prepares
`image_to_video/2026-07-18-lora5`, `wan22_video_v2/2026-07-21-pruned-v11`,
`wan22_aio_video/2026-07-18-lora5`, `ltx_video/2026-06-10`, and
`face_i2i_t2i/2026-06-10`. `video_basic/2026-06-10` is not a primary manifest;
legacy `video_insert` and `video_edit` are compatibility task types that run as
`image_to_video`. Model blobs are keyed as `models/by-sha256/<sha[:2]>/<sha>`,
while manifests may reuse older object keys that already validate by size and
sha256 metadata.

Local Docker registry layout:

```text
/srv/allbot/docker-registry
```

Start the local registry only during an ops window. The service binds loopback for
local push/pull and the LAN address for GPU-node pull:

```bash
scripts/manage_local_registry.sh --dry-run
scripts/manage_local_registry.sh --execute
```

GPU nodes still need their Docker daemon configured to trust
`192.168.1.115:5000` before they can pull from the local registry.
On the main server, push and verify through `localhost:5000`/`127.0.0.1:5000`
so the host Docker daemon does not need the LAN IP registered as insecure.

Existing LAN profile images may be mirrors of verified GHCR RunPod images. The
LAN-only `all` profile is built from protected-main source with both of its
container inputs pinned to exact digests in the local registry. Invoke
`build_runpod_profile_image.sh --profile all --reuse-base-custom-nodes` with a
digest-pinned LAN LTX base and Wan node-source image; the builder rejects
non-local or mutable source refs and records both refs in OCI labels. Push the
result to `localhost:5000`, verify its digest and revision labels, then pin that
LAN digest in the catalog before any GPU slot consumes it. GPU nodes pull the
result only from `192.168.1.115:5000`; model files remain outside the image and
move only through the LAN model cache.

Current profile image relationships:

| Profile | LAN image |
| :--- | :--- |
| `img2img_lora` | `192.168.1.115:5000/allbot/comfy-runpod-img2img:20260612-img2img-lora-kjnodes7967a946` |
| `i2i_pro` | `192.168.1.115:5000/allbot/comfy-runpod-i2i-pro:v2-47c1219f-i2ipro` |
| `image_to_video` / `video_basic` / `wan22_video_v2` / `wan22_aio_video` | `192.168.1.115:5000/allbot/comfy-runpod-wan22-aio-video:20260619-wan22aio-rife-bcf3ebd` |
| `scail2` | `192.168.1.115:5000/allbot/comfy-runpod-scail2:20260617-scail2-cu128-<shortsha>` |

Existing running slots may retain an older verified digest until an explicit
single-slot restart or takeover. Updating the profile catalog does not authorize
or perform that production mutation.

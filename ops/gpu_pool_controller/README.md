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
  --profile video_basic \
  --host-port 8190
python scripts/gpu_pool_controller.py runtime-render \
  --assignment lan-002-8188-worker-06 \
  --profile video_basic \
  --host-port 8190
python scripts/gpu_pool_controller.py switch-profile \
  --assignment lan-002-8188-worker-06 \
  --profile video_basic
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

It only targets cloud-test: one Pod, one generated PNG upload, three
`img2img/img2img_lora` tasks, test-worker restore, Pod delete, and post-cleanup
orphan checks.

Model registry layout:

```text
/srv/allbot/model-registry
  blobs/sha256/<prefix>/<sha256>
  bundles/<bundle>/<version>/manifest.yml
```

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

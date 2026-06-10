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
python scripts/gpu_pool_controller.py switch-profile \
  --assignment lan-002-8188-worker-06 \
  --profile video_basic
python scripts/gpu_pool_controller.py workflow-model-check
python scripts/gpu_pool_controller.py model-import-plan
python scripts/gpu_pool_controller.py model-import-execute
```

Runtime commands are dry-run first:

- `runtime-plan` emits runtime/image/model/worker-env diffs.
- `runtime-render` renders a standard ComfyUI Docker Compose file for review.
- `runtime-apply`, `switch-profile`, and `rollback-profile` accept `--execute`,
  but execution is intentionally disabled until Phase 1 canary validation and a
  maintenance window.
- `host_service` runtimes such as `gpu-226` are observation-only and never render
  Docker runtime operations.

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

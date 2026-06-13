# Remote Workers

This folder is a standalone package for attaching remote GPU workers to the
cloud production Central API through a local relay. It includes the current
Comfy agent code, workflow assets, a minimal compatibility `src/` package, and
Windows-first venv launchers so a remote host can sparse-checkout only this
folder and run without the main project tree.

No real secrets should be committed here. Copy `env/*.example` to real `.env`
files on each remote host.

## Layout

- `comfy_agent/`: bundled current worker agent and workflow files.
- `remote_relay/`: standalone FastAPI relay and upload sidecar.
- `src/`: minimal pure-Python compatibility modules required by the agent.
- `env/*.relay.env.example`: relay env templates for the two remote workers.
- `env/*.agent.env.example`: optional bundled-agent override templates.
- `scripts/`: Linux/macOS Bash and Windows PowerShell helpers.

## Pull Only This Folder

```bash
git clone --filter=blob:none --sparse <All_bot repository url> All_bot_remote
cd All_bot_remote
git sparse-checkout set remote_workers
cd remote_workers
```

Use your own GitHub credentials. Do not put access tokens into committed files.

## Configure One Remote Host

For `worker_remote_01`:

```bash
cp env/worker_remote_01.relay.env.example env/worker_remote_01.relay.env
```

Edit `env/worker_remote_01.relay.env`:

- `CENTRAL_API_URL`: dedicated Cloudflare Tunnel hostname for Central API 8003.
  It must be a Central API root URL such as
  `https://worker-central.aivison.it.com`, not `api.aivison.it.com`, and not a
  URL ending in `/api`.
- `AGENT_SECRET_TOKEN`: cloud production agent token.
- `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`: R2 S3 credentials.

For `worker_remote_02`, use the matching `worker_remote_02.*` templates.

The bundled agent can reuse secrets from `*.relay.env`. Create `*.agent.env`
only when you need to override local ComfyUI address, task types, or local
paths:

```powershell
copy env\worker_remote_01.agent.env.example env\worker_remote_01.agent.env
```

The most common values to check are:

```env
SUPPORTED_TASK_TYPES=img2img
COMFY_API_URL=http://127.0.0.1:8111/
COMFY_WS_URL=ws://127.0.0.1:8111/ws
COMFY_INPUT_DIR=./input
COMFY_OUTPUT_DIR=./output
```

If ComfyUI is on another LAN address, put that real address in the agent env.

## Start Bundled Worker With venv

Windows Server PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_worker_remote_01.ps1
powershell -ExecutionPolicy Bypass -File scripts/start_worker_remote_02.ps1
```

Or from `cmd.exe`:

```bat
scripts\start_worker_remote_01.cmd
scripts\start_worker_remote_02.cmd
```

On first run, the launcher creates `.venv`, upgrades `pip`, installs
`requirements.txt`, starts the relay in a new PowerShell window, and runs the
bundled agent in the current window. Later restarts reuse the same venv.

To force dependency refresh:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_worker_remote_01.ps1 -UpdateDeps
```

To run only one side while debugging:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_worker_remote_01.ps1 -RelayOnly
powershell -ExecutionPolicy Bypass -File scripts/start_worker_remote_01.ps1 -AgentOnly
```

## Start Relay Only

Linux/macOS:

```bash
bash scripts/install_venv.sh
bash scripts/start_relay.sh env/worker_remote_01.relay.env
```

Windows Server PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_relay.ps1 -EnvFile env\worker_remote_01.relay.env
```

Health check:

```bash
bash scripts/check_relay.sh env/worker_remote_01.relay.env
```

Windows health check:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check_relay.ps1
```

The expected response includes `{"status":"ok"}` and the configured upstream.

## RunPod Pod Template Entry

RunPod cloud-test canaries use the same bundled remote worker package, but run
inside a single Pod with ComfyUI, the relay/upload sidecar, and the agent:

```bash
docker build \
  -f remote_workers/Dockerfile.runpod \
  -t allbot/comfy-runpod-img2img:canary \
  .
```

The image entrypoint is `remote_workers/scripts/runpod_entrypoint.sh`. Its
startup order is fixed:

```text
ComfyUI ready -> remote relay ready -> comfy agent heartbeat
```

`remote_workers/Dockerfile.runpod` is the bundled worker/relay image entry. For
RunPod ComfyUI runtime profiles, use the profile image builder instead:

```bash
scripts/build_runpod_profile_image.sh \
  --image-ref ghcr.io/giraffu/allbot-comfy-runpod-img2img-lora:<tag>
```

The `img2img_lora` profile image bakes ComfyUI system dependencies and
`ComfyUI-KJNodes` into the ComfyUI base image. It intentionally does not bake
Qwen checkpoint or LoRA model files; keep `RUNPOD_MODEL_SYNC_ENABLED=true` and
sync models from the R2 manifest at Pod startup. If GitHub is unavailable during
build, export or copy a verified `ComfyUI-KJNodes` directory and run:

```bash
scripts/build_runpod_profile_image.sh \
  --image-ref ghcr.io/giraffu/allbot-comfy-runpod-img2img-lora:<tag> \
  --kjnodes-source /path/to/ComfyUI-KJNodes
```

Prefer GitHub Actions for the Wan22 RunPod profile image:

```text
.github/workflows/runpod_wan22_profile_image.yml
```

Run the workflow manually with an optional `image_tag`. It builds
`ghcr.io/giraffu/allbot-comfy-runpod-wan22-aio-video:<tag>`, runs the same smoke
test, pushes with the repository `GITHUB_TOKEN`, and verifies anonymous GHCR
manifest access before the image is used by RunPod.

The Wan22 workflow defaults to `yanwk/comfyui-boot:cu128-slim`, matching the
LAN-proven `192.168.1.2:8189` ComfyUI runtime shape (`cu128`, ComfyUI
`0.22.0`, PyTorch `2.11.0+cu128`). If the base lacks ComfyUI, the Dockerfile
installs ComfyUI into `/opt/ComfyUI`, writes `/opt/allbot-comfyui-dir`, and
strips custom node `.git` directories plus pip caches from the final image
layer. Do not use `docker commit` on the LAN container as a release artifact:
its ComfyUI root and `custom_nodes/models/workflows` are mounted volumes/binds,
so commit would miss the important runtime content. Pass `base_image` in the
workflow or `--base-image` locally only when intentionally testing a different
base.

Use the local script as a fallback or for profile debugging. Only push locally
after choosing a registry namespace that RunPod can pull:

```bash
printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u <github_user> --password-stdin
scripts/build_runpod_profile_image.sh \
  --image-ref ghcr.io/giraffu/allbot-comfy-runpod-img2img-lora:<tag> \
  --kjnodes-source /path/to/ComfyUI-KJNodes \
  --push
DOCKER_CONFIG="$(mktemp -d)" docker manifest inspect \
  ghcr.io/giraffu/allbot-comfy-runpod-img2img-lora:<tag> >/dev/null
```

The GitHub/GHCR token is only for Docker registry authentication. It is not a
RunPod API key, not an R2 key, and must not be passed into RunPod Pod env. If the
token is stored in `.env.cloud.*` under a non-shell key such as
`all-github-token`, map it to `GHCR_TOKEN` or `GITHUB_TOKEN` in the current shell
before running `docker login`. RunPod canary images should be public; verify with
an empty `DOCKER_CONFIG` before using the image in a paid Pod.

When using the baked profile image, set RunPod env so startup does not reinstall
custom nodes:

```env
RUNPOD_USE_TEMPLATE_IMG2IMG_LORA=false
RUNPOD_IMAGE_NAME_IMG2IMG_LORA=ghcr.io/giraffu/allbot-comfy-runpod-img2img-lora:<tag>
RUNPOD_COMFY_CUSTOM_NODES_ENABLED=false
RUNPOD_COMFY_KJNODES_ENABLED=false
```

For the first cloud-test canary, the expected profile is:

```env
RUNPOD_MANAGED=true
RUNPOD_ENVIRONMENT=cloud-test
RUNPOD_TASK_TYPE=img2img_lora
AGENT_ID=runpod_test_img2img_lora_${RUNPOD_POD_ID:-pending}
CENTRAL_API_URL=https://worker-central-test.aivison.it.com
SUPPORTED_TASK_TYPES=img2img,img2img_lora
POOL_PROVIDER=runpod
POOL_RUNTIME_PROFILE=img2img_lora
PIPELINE_MAX_RUNNING_TASKS=1
COMFY_API_URL=http://127.0.0.1:8188
MINIO_INPUT_BUCKET=user-data-test
MINIO_RESULT_BUCKET=user-data-test
MINIO_TEMPLATE_BUCKET=user-data-test
```

The Pod should not expose ComfyUI publicly. It only needs outbound access to the
cloud-test worker Central hostname and R2. Model files should come from the
image, a RunPod volume, Hugging Face cache, or R2 warm cache; do not pull large
models from the local main server or the LAN Docker registry over the public
internet.

## Legacy Old Agent Option

The bundled agent is preferred. If you must keep the old Comfy agent on the same
host, point it at the local relay:

```env
MASTER_API_URL=http://127.0.0.1:8013
UPLOAD_SIDECAR_URL=http://127.0.0.1:8013
MINIO_INPUT_BUCKET=user-data-prod
MINIO_RESULT_BUCKET=user-data-prod
MINIO_TEMPLATE_BUCKET=user-data-prod
MINIO_SECURE=true
```

If the old agent runs in Docker and the relay runs on the host, use
`http://host.docker.internal:8013` when the container runtime supports it.

For both bundled and old agents, start with a conservative
`SUPPORTED_TASK_TYPES`, for example `img2img`, and expand only after a
successful end-to-end task and Central `/system/workers` shows the remote worker
healthy.

## Cloudflare Central API Domain

Create a dedicated Cloudflare Tunnel hostname for remote workers, for example
`worker-central.aivison.it.com`, and route it to the cloud Central API service
on port `8003`.

Do not reuse `api.aivison.it.com`; that is the public Web API entrypoint.
Restrict the worker hostname with Cloudflare WAF/rate limits and, if possible,
source IP allowlists for these two remote worker nodes.

Production status as of 2026-06-12:

- `worker-central.aivison.it.com` is the currently verified production worker
  Central hostname and returns Central `/health`.
- The production control host also runs a separate
  `cloudflared-runpod-prod.service` connector for the RunPod production tunnel,
  with the token stored in a root-only token file and the origin set to
  `http://100.107.220.127:8003`.
- If a new RunPod-specific hostname is desired, bind that public hostname to the
  RunPod production tunnel in Cloudflare first, then verify `/health` before
  pointing any RunPod Pod at it.

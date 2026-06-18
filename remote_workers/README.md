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

The entrypoint supervises ComfyUI, the relay, and the agent together. If any
managed process exits, including ComfyUI being killed by the host OOM killer,
the container exits so the runtime restart policy can create a clean process
tree instead of leaving an agent heartbeat with a dead local ComfyUI.

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

Wan22 V82 uses `FL_RIFE` post-processing. New Wan22 profile images must bake
`rife49.pth` into both `ComfyUI_Fill-Nodes` and `ComfyUI-Frame-Interpolation`
cache paths, while business model weights still come from the R2 manifest at
startup. The RunPod bootstrap and entrypoint run
`scripts/ensure_wan22_rife_cache.py` before ComfyUI starts; for
`image_to_video`, `wan22_video_v2`, or `wan22_aio_video`, missing RIFE cache is
an exit-75 startup failure, not a runtime HuggingFace download attempt.

Prefer GitHub Actions for the `i2i_pro` RunPod profile image as well:

```text
.github/workflows/runpod_i2i_pro_profile_image.yml
```

It builds `ghcr.io/giraffu/allbot-comfy-runpod-i2i-pro:<tag>` from
`remote_workers/docker/runpod_profiles/i2i_pro/`, defaults to
`yanwk/comfyui-boot:cu128-slim`, pins ComfyUI to
`16cd8d8a8f5f16ce7e5f929fdba9f783990254ea`, and verifies anonymous GHCR
manifest access after push. The smoke test asserts ComfyUI/core node source
files needed by `workers/comfy_agent/workflows/i2i_pro.json`, `ffmpeg`, `curl`,
`git`, and the RunPod bootstrap Python path. It intentionally avoids importing
GPU-touching ComfyUI modules on the CPU GitHub runner; GPU import and execution
are verified by the cloud-test canary. No business model weights are baked into
this image.

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

For the `i2i_pro` cloud-test profile image, use profile-specific env:

```env
RUNPOD_USE_TEMPLATE_I2I_PRO=false
RUNPOD_IMAGE_NAME_I2I_PRO=ghcr.io/giraffu/allbot-comfy-runpod-i2i-pro:<tag>
RUNPOD_MODEL_PREFIX_I2I_PRO=i2i_pro/2026-06-14-test
RUNPOD_MODEL_MANIFEST_KEY_I2I_PRO=i2i_pro/2026-06-14-test/manifest.json
RUNPOD_TASK_TYPE_WORKFLOW_OVERRIDES_I2I_PRO={"t2i-pornmaster-turbo":"txt2img_from_i2i_pro.json","face_swap":"face_swap_v2.json"}
RUNPOD_CONTAINER_DISK_GB=120
RUNPOD_COMFY_CUSTOM_NODES_ENABLED=false
RUNPOD_COMFY_KJNODES_ENABLED=false
```

The `i2i_pro` RunPod runtime can support three execution types from one Pod:
`i2i_pro`, `t2i-pornmaster-turbo` (Web `txt2img`), and `face_swap`. The profile
must render `SUPPORTED_TASK_TYPES=i2i_pro,t2i-pornmaster-turbo,face_swap` and
`TASK_TYPE_WORKFLOW_OVERRIDES` so text-to-image uses
`txt2img_from_i2i_pro.json` and face swap uses `face_swap_v2.json`. These files
must exist under `remote_workers/comfy_agent/workflows/`; updating only the
main `workers/` tree is not enough for RunPod.

The `i2i_pro_baseline` model manifest lives in
`allbot-model-cache/i2i_pro/2026-06-14-test/manifest.json` and is sourced from
known-good `gpu-226` / `192.168.1.226:8188`. It contains only these model files:
`text_encoders/qwen_3_8b_fp8mixed.safetensors`,
`vae/flux2-vae.safetensors`,
`unet/DarkBeast-Klein9b-V2-BFS-FP8-ComfyUI.safetensors`,
`text_encoders/z_image/qwen_3_4b.safetensors`,
`vae/z_image/ae.safetensors`, and
`unet/DarkBeastZ6-BlitZ-BF16-ComfyUI.safetensors`. Runtime model sync must write
only under ComfyUI `models/`; it must not write into
`input/output/temp/custom_nodes/workflows`.

`runpod_bootstrap_from_git.sh` clones the AllBot `deploy` branch into
`/workspace/allbot/repo` only when no remote worker bundle already exists. A
new or rebuilt Pod therefore picks up the latest `deploy` fixes, but an old Pod
restarted in place may reuse an existing bundle. Before relying on an old Pod
after workflow/override changes, disable its Central agent control and either
update `/workspace/allbot/repo` in the Pod or recreate the Pod.

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

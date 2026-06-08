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

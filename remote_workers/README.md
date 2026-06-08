# Remote Workers

This folder is a standalone package for attaching old remote GPU workers to the
cloud production Central API through a local relay. It is intentionally separate
from the main `workers/` tree so a remote host can sparse-checkout only this
folder and start the relay with a Python venv.

No real secrets should be committed here. Copy `env/*.example` to real `.env`
files on each remote host.

## Layout

- `remote_relay/`: standalone FastAPI relay and upload sidecar.
- `env/*.relay.env.example`: relay env templates for the two remote workers.
- `env/*.agent.env.example`: optional env patch templates for the old agent.
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

## Start Relay With venv

Linux/macOS:

```bash
bash scripts/install_venv.sh
bash scripts/start_relay.sh env/worker_remote_01.relay.env
```

Windows Server PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_relay.ps1 -EnvFile env\worker_remote_01.relay.env
```

On first run, `start_relay.ps1` creates `.venv`, upgrades `pip`, installs
`requirements.txt`, loads the selected env file, and starts the relay. Later
restarts reuse the same venv. To force dependency refresh:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_relay.ps1 -EnvFile env\worker_remote_01.relay.env -UpdateDeps
```

Convenience launchers are also available:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_worker_remote_01.ps1
powershell -ExecutionPolicy Bypass -File scripts/start_worker_remote_02.ps1
```

Or from `cmd.exe`:

```bat
scripts\start_worker_remote_01.cmd
scripts\start_worker_remote_02.cmd
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

## Patch the Old Agent

Keep the old Comfy agent on the same host, but point it at the local relay:

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

Start with a conservative `SUPPORTED_TASK_TYPES`, for example `img2img`, and
expand only after a successful end-to-end task and Central `/system/workers`
shows the remote worker healthy.

## Cloudflare Central API Domain

Create a dedicated Cloudflare Tunnel hostname for remote workers, for example
`worker-central.aivison.it.com`, and route it to the cloud Central API service
on port `8003`.

Do not reuse `api.aivison.it.com`; that is the public Web API entrypoint.
Restrict the worker hostname with Cloudflare WAF/rate limits and, if possible,
source IP allowlists for these two remote worker nodes.

# 真境智影（Clarity AI）Media Enhancement Platform

An independent bilingual image/video enhancement product inside the AllBot
monorepo. It owns its frontend, API, PostgreSQL schema, object storage and
worker protocol. It does not import AllBot users, credits, task core, Telegram
objects or production GPU state.

## Local LAN start

1. Run `sh scripts/init_local_env.sh`. It creates an ignored `.env` and an
   ignored `.local-admin-credentials`, both with mode `0600`.
2. Run `docker compose up --build -d`.
3. Open `http://<this-host-LAN-IP>:8095`.
4. Register a normal user or read the local administrator login from
   `.local-admin-credentials`.

The initializer refuses to overwrite existing credentials. `.env.example`
documents the required keys but its `CHANGE_ME` values must never be used for
a shared LAN instance.

The site intentionally starts without a GPU worker. Submitted jobs remain
`queued` with reason `no_worker_online`; reserved points are not captured.

Useful checks:

```bash
docker compose ps
curl -fsS http://127.0.0.1:8095/health
curl -fsS http://127.0.0.1:8095/api/health
```

Stop the local stack without deleting data:

```bash
docker compose down
```

Named PostgreSQL and MinIO volumes are retained. Removing those volumes is a
separate destructive action and is intentionally not part of normal commands.

## Development

Backend:

```bash
python -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
PYTHONPATH=backend .venv/bin/pytest -q backend/tests
```

Frontend:

```bash
cd frontend
npm install
npm run test
npm run build
```

Workflow contract:

```bash
PYTHONPATH=. .venv/bin/python -c \
  "from worker_contract.workflow import validate_catalog; assert not validate_catalog()"
```

## Boundaries

- No cloud-test, cloud-prod, Cloudflare, RunPod or LAN AIO deployment is part
  of V1.
- `task_id` identifies the durable business request; `attempt_id` identifies a
  leased execution.
- Source and result files are retained until a user or administrator explicitly
  deletes them.
- Terms and privacy pages are structural drafts and must be replaced with
  reviewed operator-specific text before public launch.

# 真境智影（Clarity AI）Media Enhancement Platform

An independent bilingual video enhancement product inside the AllBot
monorepo. It owns its frontend, API, PostgreSQL schema, object storage and
worker protocol. It does not import AllBot users, credits, task core, Telegram
objects or production GPU state.

The public workspace currently exposes only the existing 2x video upscale test
capability: one MP4/MOV/WebM video, at most five seconds and 40 MB. Image
upscale and frame interpolation remain unavailable to users and are rejected
again by the API.

New accounts are created with a mainland China mobile number, an SMS code and
a password; email registration is disabled. Existing email accounts and the
environment-provisioned administrator retain legacy email login. The database
stores an HMAC identifier, masked number and verification timestamp rather
than the plaintext number. This proves control of a phone number; it is not
identity-card real-name verification.

## Local LAN start

1. Run `sh scripts/init_local_env.sh`. It creates an ignored `.env` and an
   ignored `.local-admin-credentials`, both with mode `0600`.
2. Run `docker compose up --build -d`.
3. Open `http://<this-host-LAN-IP>:8095`.
4. Register a normal user by phone or read the legacy local administrator login from
   `.local-admin-credentials`.

The currently operated public entry is `https://wuhanzhenjing.cn/`; it proxies
to this platform's Nginx/API while PostgreSQL, MinIO and the backend remain
unpublished. Public deployment records and backups are runtime evidence under
`~/.local/state/allbot/media-enhance-*`, not stable defaults in this README.

The initializer refuses to overwrite existing credentials. `.env.example`
documents the required keys but its `CHANGE_ME` values must never be used for
a shared LAN instance.

SMS is fail-closed by default (`CLARITY_SMS_PROVIDER=disabled`). To enable it,
configure a least-privilege RAM credential plus the system-provided PNVS
signature and binding template, then select `aliyun_pnvs`. Use the PNVS
`SendSmsVerifyCode` / `CheckSmsVerifyCode` product only; ordinary Alibaba Cloud
SMS signatures and templates are not interchangeable. Never commit these
values. `CLARITY_PHONE_HASH_SECRET` is a separate durable secret: back it up
and do not rotate it casually because it anchors phone uniqueness without
storing plaintext numbers. Registration and legacy-account binding challenges
have separate purposes and cannot be consumed across flows. The API enforces
per-number/account cooldown and daily limits, a separate requester-IP daily
limit, and a global daily ceiling to bound SMS cost during abuse.

The site intentionally starts without a GPU worker. Submitted jobs remain
`queued` with reason `no_worker_online`; reserved points are not captured.

## Optional AllBot test-worker bridge

The `test-worker` Compose profile runs a narrow adapter between the platform's
Worker HTTP contract and the existing AllBot test Central
`ltx25_video_upscale` consumer. It never connects to prod Central or a prod
bucket. Configure these values only in the ignored `.env`:

- `CLARITY_TEST_CENTRAL_URL` and `CLARITY_TEST_CENTRAL_API_TOKEN`
- `CLARITY_TEST_INPUT_S3_ENDPOINT_URL`
- `CLARITY_TEST_INPUT_S3_ACCESS_KEY` and `CLARITY_TEST_INPUT_S3_SECRET_KEY`
- optional `CLARITY_TEST_INPUT_S3_BUCKET` (defaults to `user-data-test`)

Then start the optional profile:

```bash
docker compose --profile test-worker up --build -d
```

Each website attempt is bound to a durable provider task ID before submission.
If the bridge restarts, it resumes that provider task instead of creating a
duplicate. User cancellation propagates to Central, and a late provider result
cannot resurrect a canceled website task. Enabling the profile is an
environment mutation; code availability by itself does not mean the bridge is
running or the GPU path has passed a live canary.

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

- The public gateway does not turn this module into a cloud-test, cloud-prod,
  RunPod or LAN AIO deployment. The optional bridge only consumes an already-operated
  test Central and test input bucket after explicit environment configuration.
- `task_id` identifies the durable business request; `attempt_id` identifies a
  leased execution.
- Source and result files are retained until a user or administrator explicitly
  deletes them.
- Unverified accounts can inspect existing history but cannot upload new source
  media or submit a new task.
- Terms and privacy pages are structural drafts. Because the site is already
  public, replacing them with reviewed operator-specific text is an outstanding
  high-priority compliance task.

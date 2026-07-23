# AllBot Independent Media Enhance Platform

## Trigger

Use this skill for changes under `media_enhance_platform/`, including the
Clarity AI frontend, API, credit ledger, media lifecycle, worker protocol,
workflow assets and local Compose stack.

## Required context

Read `docs/子模块_独立媒体增强平台_media_enhance_platform.md` before changing
cross-service contracts. Also load:

- `allbot-billing-auth` for auth or ledger semantics.
- `allbot-task-engine` for task, attempt, lease, retry or cancellation changes.
- `allbot-comfy-models` for workflow or ComfyUI node changes.
- `allbot-ops-deployment` for Compose, migration or deployment changes.
- `vue-best-practices` for Vue code.

## Boundaries

- The platform is an independent product. Do not import or reuse AllBot users,
  credits, task core, Telegram objects, PostgreSQL schema or runtime queues.
- Keep `frontend/`, `backend/`, `worker_contract/` and GPU execution separately
  deployable. A Worker talks only to the Worker HTTP contract and object/file
  endpoints; it never reads the product database.
- `task_id` is a durable business request. `attempt_id` is a leased execution.
  Retries create a new attempt without charging again.
- Credits use an immutable ledger: reserve on submit, capture on success,
  release on failure/cancel, and refund with an idempotency key.
- With no online Worker, tasks remain `queued` with `no_worker_online`.
  Never manufacture a successful result.
- Workflow JSON is versioned in this subproject and must pass catalog, node,
  input and output mapping validation. Do not load templates from an installed
  Python package at runtime.
- Do not modify cloud-test, cloud-prod, Cloudflare, RunPod, LAN AIO or existing
  AllBot Worker capabilities unless the user separately authorizes that scope.
- Legal pages are marked drafts until operator identity and reviewed text are
  supplied.

## Minimum verification

```bash
cd media_enhance_platform
.venv/bin/python -m pytest -q backend/tests
cd frontend && npm test -- --run && npm run build
cd .. && docker compose --env-file .env.example config -q
```

For UI changes, run the browser preview skill at desktop and mobile viewports.
For contract changes, cover no-worker queueing plus fake-worker success/failure.

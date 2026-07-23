# Clarity Worker Contract

V1 intentionally starts no GPU worker. A future worker authenticates with
`X-Agent-Token` and identifies itself with `X-Worker-Id` after claiming work.

1. `POST /api/worker/heartbeat`
2. `POST /api/worker/tasks/claim`
3. Download the source from the returned worker-only path.
4. Build a copied workflow with `build_workflow(...)` and execute it in ComfyUI.
5. Report `preprocessing`, `running`, or `uploading` progress before the lease
   expires.
6. Submit the result to `complete`, or a classified error to `fail`.

`task_id` is the durable business task. `attempt_id` is the execution identity
and lease owner. A stale attempt must never complete another attempt's task.

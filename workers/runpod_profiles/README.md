# LAN / RunPod GPU Profiles

Each subdirectory defines an immutable GPU profile image. Docker builds use the
repository root as context and compose `workers/comfy_agent/`, `src/`, `shared/`
and the thin `workers/runpod_runtime/` adapter into
`/opt/allbot/runtime/runpod_worker`. Worker source and workflows are never
copied back into `runpod_runtime`.

Profile build targets are declared independently in `deploy/module-catalog.json`.
The operator explicitly builds one profile and deploys its exact digest to one
slot; no release index, attestation or canary evidence is consulted.

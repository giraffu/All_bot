# LAN / RunPod GPU Profiles

Each subdirectory defines an immutable GPU profile image. Docker builds use the
repository root as context and bake `workers/runpod_runtime/` into
`/opt/allbot/runtime/runpod_worker`.

Profile build targets are declared independently in `deploy/module-catalog.json`.
The operator explicitly builds one profile and deploys its exact digest to one
slot; no release index, attestation or canary evidence is consulted.

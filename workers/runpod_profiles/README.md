# LAN / RunPod GPU Profiles

Each subdirectory defines an immutable GPU profile image. Docker builds use the
repository root as context and bake `workers/runpod_runtime/` into
`/opt/allbot/runtime/runpod_worker`.

Profile inputs are declared in `deploy/release-artifacts-v2.json`; changes must
produce the corresponding GPU artifact and pass the configured attestation and
canary gates.

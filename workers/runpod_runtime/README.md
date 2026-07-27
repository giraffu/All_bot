# LAN / RunPod Worker Runtime

This directory is the self-contained worker bundle baked into LAN AIO and
RunPod GPU profile images. It is not a standalone remote-host deployment kit.

- `comfy_agent/`: production GPU agent, workflow mappings, and RunPod pipeline
  controls.
- `runpod_relay/`: Pod-local Central API and result-upload relay.
- `scripts/`: image startup, model sync, and runtime validation.
- `src/`: minimal domain/config modules required by the baked bundle.
- `../runpod_profiles/`: profile Dockerfiles that copy this bundle to
  `/opt/allbot/runtime/runpod_worker`.

There is no standalone host compatibility entrypoint. Change this runtime only
together with the affected GPU artifact, parity tests, and release/canary
gates.

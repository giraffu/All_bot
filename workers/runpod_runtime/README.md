# LAN / RunPod Worker Runtime

This directory contains only the RunPod/LAN adapter around the canonical GPU
worker. It is not a second worker package or a standalone host deployment kit.

- `runpod_relay/`: Pod-local Central API and result-upload relay.
- `scripts/`: image startup, model sync, and runtime validation.
- `requirements.txt`: dependencies installed by GPU profile images.
- `../comfy_agent/`: the sole agent, patcher and workflow source.
- `../../src/`: the sole domain/config source consumed by the image.
- `../runpod_profiles/`: profile Dockerfiles that copy this bundle to
  `/opt/allbot/runtime/runpod_worker`.

Profile Dockerfiles compose these sources at `/opt/allbot/runtime/runpod_worker`.
Builds embed Git SHA, canonical package hash and workflow mapping hash; the
agent verifies and reports them in heartbeat metadata. Change the adapter only
with the affected artifact, focused tests and per-profile canary gate.

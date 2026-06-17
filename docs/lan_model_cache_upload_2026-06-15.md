# LAN Model Cache Upload Verification - 2026-06-15

## Scope

This record freezes the all-task LAN model cache upload phase for the
RunPod-style LAN all-in-one runtime work.

- Cache endpoint: `192.168.1.115:9010`
- Bucket: `allbot-model-cache`
- Data root: `/srv/allbot/model-cache-lan`
- Object pool: `models/by-sha256/<sha[:2]>/<sha>`
- Env policy: credentials stay only in ignored local env files; no env values,
  tokens, presigned URLs, or raw task payloads are recorded here.
- Runtime policy: no canary window was opened, no worker control was changed,
  and no RunPod Pod was created.

## Upload Summary

Command shape:

```bash
python3 scripts/upload_all_task_models_to_lan_cache.py \
  --env-file .env.lan.model-cache \
  --execute
```

Sanitized result:

- `ok=true`
- `dry_run=false`
- `existing_cached_unique_model_count=12`
- `target_unique_model_count=59`
- `target_unique_total_gib=245.15`
- `upload_count=47`
- `upload_total_gib=179.49`
- `skipped_existing_count=12`
- `missing_local_blob_count=0`
- `manifest_upload_count=5`
- `manifest_skip_count=2`

## Post-Upload Dry Run

Command shape:

```bash
python3 scripts/upload_all_task_models_to_lan_cache.py \
  --env-file .env.lan.model-cache
```

Sanitized result:

- `ok=true`
- `dry_run=true`
- `existing_cached_unique_model_count=59`
- `target_unique_model_count=59`
- `target_unique_total_gib=245.15`
- `upload_count=0`
- `upload_total_gib=0.0`
- `skipped_existing_count=59`
- `missing_local_blob_count=0`
- `manifest_upload_count=0`
- `manifest_skip_count=7`

## Manifest Verification

Each manifest was fetched from LAN MinIO and every referenced model object was
checked with S3 HEAD. `ContentLength` matched `size_bytes`, and sha256 object
metadata matched the manifest sha256 for every unique object.

| Manifest | Files | Total GiB |
| --- | ---: | ---: |
| `img2img_lora/2026-06-10/manifest.json` | 6 | 29.55 |
| `i2i_pro/2026-06-14-test/manifest.json` | 6 | 36.11 |
| `image_to_video/2026-06-13-test/manifest.json` | 21 | 43.69 |
| `wan22_video_v2/2026-06-13-test/manifest.json` | 5 | 48.59 |
| `wan22_aio_video/2026-06-12-test/manifest.json` | 23 | 79.50 |
| `ltx_video/2026-06-10/manifest.json` | 19 | 60.42 |
| `face_i2i_t2i/2026-06-10/manifest.json` | 36 | 124.15 |

Additional verification:

- Unique model object HEAD checks: `59`
- HEAD verification errors: `0`
- Legacy independent `video_basic/2026-06-10/manifest.json`: absent
- LAN cache health check: ready
- Disk after upload: `/srv/allbot/model-cache-lan` about `246G`, filesystem about
  `45%` used

## SCAIL-2 LAN AIO Runtime Addendum - 2026-06-17

SCAIL-2 ComfyUI workflow assets and model weights are staged for the gpu-002
LAN AIO SCAIL-2 runtime. This runtime backs the Web test station and test Bot features
`scail2_action_transfer` (动作迁移) and `scail2_video_replacement` (视频换人),
but it is not a cloud-prod capability and does not register itself as a
Central worker. The runtime container provides ComfyUI; the test worker
`cloud_worker_test_08` performs Central queue polling and points to
`http://192.168.1.2:8190`.

- Workflow source: `https://comfyui.nomadoor.net/en/basic-workflows/scail-2/`
- Workflow files staged under both `workers/comfy_agent/workflows/` and
  `remote_workers/comfy_agent/workflows/`:
  - `SCAIL-2_Animation.json`
  - `SCAIL-2_Replacement.json`
  - `SCAIL-2_Animation_multi-char.json`
  - `SCAIL-2_Animation_WAN-Context-Windows.json`
  - `SCAIL-2_Animation_multi-char.api.json`
  - `SCAIL-2_Replacement.api.json`
- Workflow status: the four Nomadoor UI workflow JSON files are kept for
  manual ComfyUI editing/loading. Business execution uses API-format derived
  workflows only: `SCAIL-2_Animation_multi-char.api.json` for
  `scail2_action_transfer`, and `SCAIL-2_Replacement.api.json` for
  `scail2_video_replacement`.
- LAN cache manifest: `scail2/2026-06-17-test/manifest.json`
- Files: `6`
- Total size: about `26.48 GiB`
- Included model paths:
  - `checkpoints/sam3.1_multiplex_fp16.safetensors`
  - `clip_vision/clip_vision_h.safetensors`
  - `diffusion_models/wan2.1_14B_SCAIL_2_fp8_scaled.safetensors`
  - `loras/Wan2.1/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors`
  - `text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors`
  - `vae/wan_2.1_vae.safetensors`

Verification performed:

- Fetched `scail2/2026-06-17-test/manifest.json` from LAN MinIO.
- Checked every manifest object with S3 HEAD and matched `ContentLength` to
  `size_bytes`.
- Reused existing LAN cache objects for `umt5_xxl_fp8_e4m3fn_scaled.safetensors`
  and `wan_2.1_vae.safetensors`.
- Updated the LoRA `relative_path` to the workflow dropdown path
  `loras/Wan2.1/Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors`
  while reusing the existing sha256 object.
- Validated worker workflow mappings for both local and remote worker workflow
  directories, including the two SCAIL-2 API workflows.
- LAN AIO runtime helper: `scripts/lan_scail2_aio_test.sh`; container
  `allbot-lan-aio-gpu-002-gpu0-scail2-test` uses the same LAN manifest, exposes
  ComfyUI on `http://192.168.1.2:8190`, and intentionally does not set
  `AGENT_ID`, `CENTRAL_API_URL`, or `SUPPORTED_TASK_TYPES`.

## Regression

```bash
pytest -q \
  tests/ops/test_lan_model_cache_upload.py \
  tests/ops/test_model_bundle_r2_upload.py \
  tests/ops/test_gpu_pool_controller.py
```

Result: `28 passed`.

```bash
python3 scripts/gpu_pool_controller.py workflow-model-check
```

Result: `reference_count=66`, `found_count=66`, `missing_count=0`.

`runtime-render --runtime-shape runpod_all_in_one` was dry-rendered for
`img2img_lora`, `image_to_video`, `wan22_video_v2`, and `i2i_pro`. Each render
resolved the expected LAN manifest, kept `production_port_unchanged=true`, set
`PIPELINE_MAX_RUNNING_TASKS=1`, and restricted model sync to
`/workspace/ComfyUI/models`.

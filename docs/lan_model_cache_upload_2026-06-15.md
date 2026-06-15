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

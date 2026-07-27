# LAN AIO Production Canary Record - 2026-06-16

## Scope

- Environment: cloud-prod
- Node: `gpu-002`
- Slot: slot1 / GPU 1
- Legacy worker: `cloud_prod_worker_07`
- Temporary AIO agent: `lan_aio_prod_gpu002_gpu1_image_to_video_01`
- Runtime profile: `image_to_video`
- Host port: `8191`
- Central: production worker Central
- Storage bucket: `user-data-prod`

No RunPod Pod was created. No production Web task type was changed. Secrets, JWTs,
presigned URLs and env values are intentionally omitted from this record.

## Canary Results

| Submitted type | Central execution type | Task id | Temporary agent hit | Central status | Web result | Download check |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `image_to_video` | `image_to_video` | `5f60f20e-1484-4e0f-9ba7-4364ab883b11` | yes | `done` | `success` | MP4 download OK |
| `video_insert` | `image_to_video` | `24e1c422-c616-47d6-ad54-33e1e8cacc57` | yes | `done` | `success` | MP4 and `last_frame` download OK |
| `video_edit` | `image_to_video` | `4449333d-a8c9-465f-9dc5-75250d52b523` | yes | `done` | `success` | MP4 and `last_frame` download OK |

## Fixes Applied

  LAN model cache sync. This prevents missing runtime modules such as `minio`
  or `uvicorn` during model sync and relay startup.
- The production canary helper treats a worker as busy when it is `running` or
  has `current_task_type`; a stale `current_task_id` left on an idle heartbeat
  no longer blocks drain/restore logic.

## Restore State

- Temporary AIO agent was disabled after canary.
- The slot1 AIO container was stopped.
- `cloud_prod_worker_07` was restored to production service.
- gpu-002 original `comfy1` on `8189` remained the production baseline.

## Follow-Up

- 2026-06-16 later update: gpu-002 slot0 and slot1 were converted from
  one-off canary use to production AIO intake.
- First steady-state production scope:
  - slot0: `img2img,img2img_lora`
  - slot1: `image_to_video,video_insert,video_edit`
- Legacy `cloud_prod_worker_06/07` were drained before switch, then disabled.
  AIO agents were enabled after the legacy workers and original `8188/8189`
  queues were idle.
- Original gpu-002 `comfy0/comfy1` containers were intentionally left running
  during the switch as a hot rollback baseline. After AIO success was observed
  on both slots, the old containers were stopped, not deleted.
- Legacy `cloud-prod-comfy-agent-6/7` containers were also stopped, not
  deleted, after AIO success to prevent them from repeatedly reporting errors
  against the intentionally stopped old ComfyUI ports.

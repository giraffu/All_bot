from __future__ import annotations


MINIMAX_H3_TASK_SCOPE = "minimax_h3"
MINIMAX_H3_TASK_TYPES = (
    "minimax_h3_t2v",
    "minimax_h3_i2v",
    "minimax_h3_flf2v",
    "minimax_h3_ref2v",
)

# UserLog.operation_type stores the public task type used for the debit. Keep this
# catalog local because the analytics image intentionally contains only app/ and
# static/, not the production service package.
GENERATION_OPERATION_TYPES = [
    "edit",
    "custom_video",
    "img2img_lora",
    "face_swap",
    "image",
    "video_lora",
    "undress",
    "perfect_video_insert",
    "i2i_pro",
    "ltx_video",
    "closeup_blowjob",
    "masturbation",
    "blowjob",
    "undress_tongue",
    "doggy_style",
    "wan22_video_v2",
    "txt2img",
    "i2i_draw",
    "face_video_step1",
    "penetration",
    "scail2_action_transfer",
    "text_to_image",
    "face_video",
    "scail2_video_replacement",
    "fuck",
    "scail2_face_swap_v2",
    "face_show",
    "face_tongue",
    "video_pro",
    "video_edit",
    "video_insert",
    "image_to_video",
    *MINIMAX_H3_TASK_TYPES,
]

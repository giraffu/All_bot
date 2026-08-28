export type RunPodProfile = {
  profile: string
  label: string
  supported_task_types: string[]
}

export const RUNPOD_FALLBACK_PROFILES: RunPodProfile[] = [
  {
    profile: 'img2img',
    label: 'img2img / img2img_lora',
    supported_task_types: ['img2img', 'img2img_lora'],
  },
  {
    profile: 'image_to_video',
    label: 'image_to_video',
    supported_task_types: ['image_to_video', 'video_insert', 'video_edit'],
  },
  {
    profile: 'wan22_video_v2',
    label: 'wan22_video_v2',
    supported_task_types: ['wan22_video_v2'],
  },
  {
    profile: 'i2i_pro',
    label: 'i2i_pro / txt2img / face_swap_v2 / face_swap',
    supported_task_types: [
      'i2i_pro',
      't2i-pornmaster-turbo',
      'face_swap_v2',
      'face_swap',
    ],
  },
  {
    profile: 'scail2',
    label: 'scail2 / 视频生视频',
    supported_task_types: ['scail2_action_transfer', 'scail2_video_replacement'],
  },
  {
    profile: 'ltx_video',
    label: 'ltx_video / 高级图生视频',
    supported_task_types: ['ltx_video', 'ltx_video_flf2v', 'ltx_video_v2v_audio'],
  },
  {
    profile: 'ltx_t2v',
    label: 'ltx_t2v / Sulphur + Ingredients',
    supported_task_types: ['ltx_t2v', 'ltx_t2v_ic'],
  },
  {
    profile: 'pornmaster_flux2_edit',
    label: 'pornmaster_flux2 / 自由P图 v2',
    supported_task_types: [
      'pornmaster_flux2_single_edit',
      'pornmaster_flux2_multi_edit',
    ],
  },
  {
    profile: 'pornmaster_flux2_edit_bf16',
    label: 'pornmaster_flux2 BF16 / 自由P图 v2.5 + v3 共用执行池',
    supported_task_types: [
      'character_reference_build',
      'pornmaster_flux2_edit_bf16',
      'pornmaster_flux2_multi_edit_bf16',
    ],
  },
]

const RUNPOD_MANUAL_AGENT_ID_PATTERN =
  /^runpod_prod_(img2img|image_to_video|wan22_video_v2|i2i_pro|scail2|ltx_video|ltx_t2v|minimax_h3|pornmaster_flux2_edit|pornmaster_flux2_edit_bf16)_manual_\d+$/

export const isRunPodManualAgentId = (agentId: string) =>
  RUNPOD_MANUAL_AGENT_ID_PATTERN.test(agentId)

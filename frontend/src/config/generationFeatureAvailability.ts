import { getRuntimeFlag } from '@/config/runtime'

const WEB_LAB_MODE_ENTRY_FLAGS: Record<string, string> = {
  edit: 'enable_edit_entry',
  edit_v2_5: 'enable_edit_v2_5_entry',
  edit_v3: 'enable_edit_v3_entry',
  txt2img: 'enable_txt2img_entry',
  i2i_pro: 'enable_i2i_pro_entry',
  custom_video: 'enable_custom_video_entry',
  face_swap: 'enable_face_swap_entry',
  random_faceswap: 'enable_random_faceswap_entry',
  ltx_video: 'enable_ltx_video_entry',
  ltx_video_v2: 'enable_ltx_video_v2_entry',
  ltx_t2v: 'enable_ltx_t2v_entry',
  minimax_h3: 'enable_minimax_h3_entry',
  wan22_video_v2: 'enable_wan22_video_v2_entry',
  scail2_action_transfer: 'enable_scail2_action_transfer_entry',
  scail2_video_replacement: 'enable_scail2_video_replacement_entry',
  scail2_face_swap_v2: 'enable_scail2_face_swap_v2_entry',
  character_reference: 'enable_character_assets_entry',
}

const GALLERY_TASK_TYPE_ENTRY_FLAGS: Record<string, string> = {
  txt2img: 'enable_gallery_txt2img_entry',
  i2i_pro: 'enable_gallery_i2i_pro_entry',
  edit: 'enable_gallery_edit_entry',
  img2img_lora: 'enable_gallery_edit_entry',
  edit_group: 'enable_gallery_edit_entry',
  free_edit_v2_5: 'enable_gallery_free_edit_v2_5_entry',
  free_edit_v2_5_group: 'enable_gallery_free_edit_v2_5_entry',
  pornmaster_flux2_edit_bf16: 'enable_gallery_free_edit_v3_entry',
  pornmaster_flux2_single_edit: 'enable_gallery_free_edit_v3_entry',
  pornmaster_flux2_multi_edit: 'enable_gallery_free_edit_v3_entry',
  free_edit_v3_group: 'enable_gallery_free_edit_v3_entry',
  custom_video: 'enable_gallery_custom_video_entry',
  video_lora: 'enable_gallery_custom_video_entry',
  img2video_group: 'enable_gallery_custom_video_entry',
  ltx_video: 'enable_gallery_ltx_video_entry',
  ltx_video_flf2v: 'enable_gallery_ltx_video_entry',
  minimax_h3: 'enable_gallery_minimax_h3_entry',
  minimax_h3_i2v: 'enable_gallery_minimax_h3_entry',
  minimax_h3_flf2v: 'enable_gallery_minimax_h3_entry',
  minimax_h3_ref2v: 'enable_gallery_minimax_h3_entry',
  wan22_video_v2: 'enable_gallery_wan22_video_v2_entry',
  scail2_action_transfer: 'enable_gallery_scail2_action_transfer_entry',
  scail2_action_transfer_long: 'enable_gallery_scail2_action_transfer_entry',
  scail2_video_replacement: 'enable_gallery_scail2_video_replacement_entry',
  scail2_face_swap_v2: 'enable_gallery_scail2_face_swap_v2_entry',
}

export const isWebLabModeEntryEnabled = (modeId: string): boolean => {
  const flagName = WEB_LAB_MODE_ENTRY_FLAGS[modeId]
  return flagName ? getRuntimeFlag(flagName, true) : true
}

export const isLtxVideoFeatureEnabled = (): boolean =>
  getRuntimeFlag('enable_ltx_video', true)

export const isMinimaxH3FeatureEnabled = (): boolean =>
  getRuntimeFlag('enable_minimax_h3', false)

export const isMinimaxH3EntryEnabled = (): boolean =>
  isMinimaxH3FeatureEnabled()
  && getRuntimeFlag('enable_minimax_h3_entry', false)

export const isMinimaxH3GalleryEntryEnabled = (): boolean =>
  isMinimaxH3FeatureEnabled()
  && getRuntimeFlag(
    'enable_gallery_minimax_h3_entry',
    isMinimaxH3EntryEnabled(),
  )

export const isGalleryTaskTypeEntryEnabled = (taskType: string): boolean => {
  if (taskType === 'minimax_h3' || taskType.startsWith('minimax_h3_')) {
    return isMinimaxH3GalleryEntryEnabled()
  }
  const flagName = GALLERY_TASK_TYPE_ENTRY_FLAGS[taskType]
  return getRuntimeFlag(flagName, true) && isGenerationTaskTypeEnabled(taskType)
}

export const isGenerationTaskTypeEnabled = (taskType: string): boolean => {
  if (taskType === 'ltx_video' || taskType === 'ltx_video_flf2v') {
    return isLtxVideoFeatureEnabled()
  }
  if (taskType === 'minimax_h3_ref2v') {
    return isMinimaxH3FeatureEnabled()
      && getRuntimeFlag('enable_minimax_h3_ref2v', false)
  }
  if (taskType === 'minimax_h3' || taskType.startsWith('minimax_h3_')) {
    return isMinimaxH3FeatureEnabled()
  }
  return true
}

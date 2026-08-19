import { isGenerationTaskTypeEnabled } from '@/config/generationFeatureAvailability'

export interface GallerySubmissionCandidate {
  type?: string | null
  allow_contribute?: boolean | null
}

const GALLERY_SUBMISSION_TASK_TYPES = new Set([
  'txt2img', 'i2i_pro', 'i2i_draw', 'edit', 'custom_video', 'video_lora',
  'img2img_lora', 'free_edit_v2_5', 'pornmaster_flux2_edit_bf16',
  'pornmaster_flux2_single_edit', 'pornmaster_flux2_multi_edit',
  'ltx_video', 'ltx_video_flf2v', 'wan22_video_v2',
  'scail2_action_transfer', 'scail2_action_transfer_long',
  'scail2_video_replacement', 'scail2_face_swap_v2',
  'minimax_h3_i2v', 'minimax_h3_flf2v',
])

export const isGallerySubmissionEligible = (
  candidate: GallerySubmissionCandidate | null | undefined,
): boolean => Boolean(
  candidate
  && candidate.allow_contribute !== false
  && isGenerationTaskTypeEnabled(String(candidate.type || ''))
  && GALLERY_SUBMISSION_TASK_TYPES.has(String(candidate.type || ''))
)

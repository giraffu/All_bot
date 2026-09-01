export const VIDEO_UPSCALE_MAX_BYTES = 40 * 1024 * 1024
export const VIDEO_UPSCALE_MAX_SECONDS = 5
export const VIDEO_UPSCALE_MULTIPLIER = 2

const SUPPORTED_VIDEO_TYPES = new Set([
  'video/mp4',
  'video/quicktime',
  'video/webm',
])

export type VideoSelectionError =
  | 'video_only'
  | 'unsupported_video'
  | 'video_too_large'
  | 'video_too_long'
  | 'video_metadata_failed'

interface VideoSelection {
  type: string
  size: number
}

export function validateVideoSelection(
  file: VideoSelection,
  durationSeconds: number,
): VideoSelectionError | null {
  if (!file.type.startsWith('video/')) return 'video_only'
  if (!SUPPORTED_VIDEO_TYPES.has(file.type)) return 'unsupported_video'
  if (file.size > VIDEO_UPSCALE_MAX_BYTES) return 'video_too_large'
  if (!Number.isFinite(durationSeconds) || durationSeconds <= 0) {
    return 'video_metadata_failed'
  }
  if (durationSeconds > VIDEO_UPSCALE_MAX_SECONDS) return 'video_too_long'
  return null
}

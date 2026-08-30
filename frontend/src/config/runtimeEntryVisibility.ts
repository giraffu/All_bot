import { getRuntimeConfig } from './runtime'

const ENTRY_VISIBILITY_KEYS = [
  'enable_edit_entry',
  'enable_edit_v2_5_entry',
  'enable_edit_v3_entry',
  'enable_txt2img_entry',
  'enable_i2i_pro_entry',
  'enable_custom_video_entry',
  'enable_face_swap_entry',
  'enable_random_faceswap_entry',
  'enable_ltx_video_entry',
  'enable_ltx_video_v2_entry',
  'enable_ltx_t2v_entry',
  'enable_minimax_h3_entry',
  'enable_wan22_video_v2_entry',
  'enable_scail2_action_transfer_entry',
  'enable_scail2_video_replacement_entry',
  'enable_scail2_face_swap_v2_entry',
  'enable_ltx25_video_upscale_entry',
  'enable_character_assets_entry',
  'enable_gallery_txt2img_entry',
  'enable_gallery_i2i_pro_entry',
  'enable_gallery_edit_entry',
  'enable_gallery_free_edit_v2_5_entry',
  'enable_gallery_free_edit_v3_entry',
  'enable_gallery_custom_video_entry',
  'enable_gallery_ltx_video_entry',
  'enable_gallery_minimax_h3_entry',
  'enable_gallery_wan22_video_v2_entry',
  'enable_gallery_scail2_action_transfer_entry',
  'enable_gallery_scail2_video_replacement_entry',
  'enable_gallery_scail2_face_swap_v2_entry',
] as const

type EntryVisibilityKey = typeof ENTRY_VISIBILITY_KEYS[number]

interface EntryVisibilityResponse {
  flags?: Partial<Record<EntryVisibilityKey, unknown>>
}

export const hydrateRuntimeEntryVisibility = async (
  fetchImpl: typeof fetch = fetch,
): Promise<boolean> => {
  if (typeof window === 'undefined') return false

  const apiBaseUrl = getRuntimeConfig('api_base_url', '/api').replace(/\/$/, '')
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), 3000)
  try {
    const response = await fetchImpl(`${apiBaseUrl}/app/entry-visibility`, {
      cache: 'no-store',
      credentials: 'omit',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
    if (!response.ok) return false

    const payload = await response.json() as EntryVisibilityResponse
    const safeFlags = Object.fromEntries(
      ENTRY_VISIBILITY_KEYS.flatMap((key) => (
        typeof payload.flags?.[key] === 'boolean'
          ? [[key, payload.flags[key]]]
          : []
      )),
    )
    window.__ALLBOT_CONFIG__ = Object.freeze({
      ...(window.__ALLBOT_CONFIG__ ?? {}),
      ...safeFlags,
    })
    return Object.keys(safeFlags).length > 0
  } catch {
    return false
  } finally {
    window.clearTimeout(timeoutId)
  }
}

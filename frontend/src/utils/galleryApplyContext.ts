export const GALLERY_APPLY_CONTEXT_STORAGE_KEY = 'galleryApplyContext'

export function saveGalleryApplyContext(rawContext: unknown): void {
  try {
    sessionStorage.setItem(
      GALLERY_APPLY_CONTEXT_STORAGE_KEY,
      JSON.stringify(rawContext)
    )
  } catch (error) {
    console.error('Failed to persist gallery apply context', error)
  }
}

export function loadGalleryApplyContext<T = Record<string, any>>(): T | null {
  try {
    const raw = sessionStorage.getItem(GALLERY_APPLY_CONTEXT_STORAGE_KEY)
    if (!raw) {
      return null
    }
    return JSON.parse(raw) as T
  } catch (error) {
    console.error('Failed to parse gallery apply context', error)
    sessionStorage.removeItem(GALLERY_APPLY_CONTEXT_STORAGE_KEY)
    return null
  }
}

export function clearGalleryApplyContext(): void {
  sessionStorage.removeItem(GALLERY_APPLY_CONTEXT_STORAGE_KEY)
}

import {
  clearGalleryApplyContext,
  loadGalleryApplyContext,
  saveGalleryApplyContext
} from '@/utils/galleryApplyContext'

export function useGalleryApplyContext() {
  return {
    saveApplyContext: saveGalleryApplyContext,
    loadApplyContext: loadGalleryApplyContext,
    clearApplyContext: clearGalleryApplyContext
  }
}

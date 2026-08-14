export const GALLERY_MOBILE_BREAKPOINT = 640

export const getGalleryTableColumnWidths = (compact: boolean) => ({
  preview: compact ? 104 : 120,
  action: compact ? 112 : 320,
})

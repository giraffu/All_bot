class GalleryCoreError(Exception):
    default_reason = "gallery_error"

    def __init__(self, message: str, *, reason: str | None = None):
        super().__init__(message)
        self.reason = reason or self.default_reason


class DuplicateInteractionError(GalleryCoreError):
    default_reason = "duplicate_interaction"


class GalleryPostNotFoundError(GalleryCoreError):
    default_reason = "post_not_found"

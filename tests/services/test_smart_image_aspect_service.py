from PIL import Image

from src.services.smart_image_aspect_service import (
    AspectAdaptationMode,
    FocusDetectionUnavailable,
    FocusRegion,
    adapt_image_to_aspect,
)


def test_face_aware_crop_moves_the_window_to_keep_a_head_near_the_top():
    image = Image.new("RGB", (300, 400), "black")
    for x in range(120, 180):
        for y in range(5, 65):
            image.putpixel((x, y), (255, 0, 0))

    result = adapt_image_to_aspect(
        image,
        aspect=(1, 1),
        focus_detector=lambda _: [FocusRegion(120, 5, 180, 65)],
    )

    assert result.mode is AspectAdaptationMode.FOCUS_CROP
    assert result.image.size == (300, 300)
    assert result.crop_box == (0, 0, 300, 300)
    assert result.image.getpixel((150, 5)) == (255, 0, 0)


def test_multiple_faces_that_cannot_fit_trigger_full_frame_padding():
    image = Image.new("RGB", (400, 300), "blue")

    result = adapt_image_to_aspect(
        image,
        aspect=(1, 1),
        focus_detector=lambda _: [
            FocusRegion(0, 40, 80, 120),
            FocusRegion(320, 40, 400, 120),
        ],
    )

    assert result.mode is AspectAdaptationMode.BLURRED_PADDING
    assert result.image.size == (400, 400)
    assert result.crop_box is None


def test_extreme_ratio_change_pads_before_discarding_most_of_the_frame():
    image = Image.new("RGB", (160, 90), "green")
    detector_called = False

    def detector(_):
        nonlocal detector_called
        detector_called = True
        return []

    result = adapt_image_to_aspect(
        image,
        aspect=(9, 16),
        focus_detector=detector,
    )

    assert result.mode is AspectAdaptationMode.BLURRED_PADDING
    assert result.image.size == (90, 160)
    assert result.retained_area < 0.55
    assert detector_called is False


def test_detector_failure_fails_safe_to_padding_instead_of_center_crop():
    def unavailable(_):
        raise FocusDetectionUnavailable("model missing")

    result = adapt_image_to_aspect(
        Image.new("RGB", (400, 300), "purple"),
        aspect=(1, 1),
        focus_detector=unavailable,
    )

    assert result.mode is AspectAdaptationMode.BLURRED_PADDING
    assert result.image.size == (400, 400)


def test_saliency_cropper_is_used_when_face_detection_succeeds_with_no_faces():
    image = Image.new("RGB", (400, 300), "black")
    for x in range(100, 400):
        for y in range(300):
            image.putpixel((x, y), (x // 2, 0, 0))

    result = adapt_image_to_aspect(
        image,
        aspect=(1, 1),
        focus_detector=lambda _: [],
        saliency_cropper=lambda _image, _size: (100, 0, 400, 300),
    )

    assert result.mode is AspectAdaptationMode.SALIENCY_CROP
    assert result.crop_box == (100, 0, 400, 300)
    assert result.image.size == (300, 300)


def test_same_ratio_returns_an_independent_image_without_detection():
    detector_called = False

    def detector(_):
        nonlocal detector_called
        detector_called = True
        return []

    image = Image.new("RGB", (320, 180), "white")
    result = adapt_image_to_aspect(
        image,
        aspect=(16, 9),
        focus_detector=detector,
    )

    assert result.mode is AspectAdaptationMode.UNCHANGED
    assert result.image.size == image.size
    assert result.image is not image
    assert detector_called is False

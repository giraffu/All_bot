from io import BytesIO

import pytest
from PIL import Image

from src.services.qqcc_video_frame_adapter import (
    QqccVideoFrameAdaptationError,
    adapt_qqcc_video_frame_bytes,
    adapt_qqcc_video_frame_file,
)
from src.services.smart_image_aspect_service import FocusRegion


def _no_faces(_image):
    return []


def _center_crop(_image, crop_size):
    width, height = _image.size
    crop_width, crop_height = crop_size
    left = (width - crop_width) // 2
    top = (height - crop_height) // 2
    return left, top, left + crop_width, top + crop_height


def _image_bytes(size: tuple[int, int], *, image_format: str = "PNG") -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color=(200, 100, 50)).save(output, format=image_format)
    return output.getvalue()


@pytest.mark.parametrize(
    ("source_size", "aspect_ratio", "expected_size"),
    [
        ((400, 300), "9:16", (225, 400)),
        ((300, 400), "16:9", (400, 225)),
        ((401, 300), "1:1", (300, 300)),
    ],
)
def test_adapt_bytes_pads_extreme_changes_and_crops_safe_changes(
    source_size: tuple[int, int],
    aspect_ratio: str,
    expected_size: tuple[int, int],
):
    adapted = adapt_qqcc_video_frame_bytes(
        _image_bytes(source_size),
        aspect_ratio=aspect_ratio,
        focus_detector=_no_faces,
        saliency_cropper=_center_crop,
    )

    with Image.open(BytesIO(adapted)) as image:
        assert image.size == expected_size


def test_source_bytes_are_validated_and_returned_unchanged():
    content = _image_bytes((320, 240), image_format="JPEG")

    assert adapt_qqcc_video_frame_bytes(content, aspect_ratio="source") is content


def test_source_file_returns_original_path_without_creating_copy(tmp_path):
    source = tmp_path / "input.png"
    source.write_bytes(_image_bytes((320, 240)))

    result = adapt_qqcc_video_frame_file(
        str(source),
        aspect_ratio="source",
        output_dir=str(tmp_path),
    )

    assert result == str(source)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["input.png"]


def test_adapt_file_writes_managed_png_copy(tmp_path):
    source = tmp_path / "input.jpg"
    source.write_bytes(_image_bytes((400, 300), image_format="JPEG"))

    result = adapt_qqcc_video_frame_file(
        str(source),
        aspect_ratio="1:1",
        output_dir=str(tmp_path),
        focus_detector=_no_faces,
        saliency_cropper=_center_crop,
    )

    assert result != str(source)
    assert result.endswith(".png")
    with Image.open(result) as image:
        assert image.size == (300, 300)


def test_saliency_fallback_can_choose_the_middle_of_the_source_image():
    source = Image.new("RGB", (6, 4))
    for x in range(6):
        for y in range(4):
            source.putpixel((x, y), (x * 20, 0, 0))
    content = BytesIO()
    source.save(content, format="PNG")

    adapted = adapt_qqcc_video_frame_bytes(
        content.getvalue(),
        aspect_ratio="1:1",
        focus_detector=_no_faces,
        saliency_cropper=_center_crop,
    )

    with Image.open(BytesIO(adapted)) as image:
        assert image.getpixel((0, 0)) == (20, 0, 0)
        assert image.getpixel((3, 0)) == (80, 0, 0)


def test_exif_orientation_is_applied_before_cropping():
    source = Image.new("RGB", (40, 20), "blue")
    exif = source.getexif()
    exif[274] = 6
    content = BytesIO()
    source.save(content, format="JPEG", exif=exif)

    adapted = adapt_qqcc_video_frame_bytes(
        content.getvalue(),
        aspect_ratio="9:16",
        focus_detector=_no_faces,
        saliency_cropper=_center_crop,
    )

    with Image.open(BytesIO(adapted)) as image:
        assert image.size == (18, 32)


def test_reapplying_the_same_ratio_is_content_idempotent():
    first = adapt_qqcc_video_frame_bytes(
        _image_bytes((400, 300)),
        aspect_ratio="16:9",
        focus_detector=_no_faces,
        saliency_cropper=_center_crop,
    )

    second = adapt_qqcc_video_frame_bytes(
        first,
        aspect_ratio="16:9",
        focus_detector=_no_faces,
        saliency_cropper=_center_crop,
    )

    assert second == first


def test_invalid_file_does_not_leave_a_derived_temp_file(tmp_path):
    source = tmp_path / "broken.png"
    source.write_bytes(b"not-an-image")

    with pytest.raises(QqccVideoFrameAdaptationError):
        adapt_qqcc_video_frame_file(
            str(source),
            aspect_ratio="16:9",
            output_dir=str(tmp_path),
        )

    assert sorted(path.name for path in tmp_path.iterdir()) == ["broken.png"]


@pytest.mark.parametrize("content", [b"", b"not-an-image"])
def test_invalid_image_is_rejected(content: bytes):
    with pytest.raises(QqccVideoFrameAdaptationError):
        adapt_qqcc_video_frame_bytes(content, aspect_ratio="9:16")


def test_face_detector_moves_a_safe_crop_up_to_preserve_the_head():
    source = Image.new("RGB", (300, 400), "black")
    for x in range(120, 180):
        for y in range(5, 65):
            source.putpixel((x, y), (255, 0, 0))
    content = BytesIO()
    source.save(content, format="PNG")

    adapted = adapt_qqcc_video_frame_bytes(
        content.getvalue(),
        aspect_ratio="1:1",
        focus_detector=lambda _: [FocusRegion(120, 5, 180, 65)],
        saliency_cropper=_center_crop,
    )

    with Image.open(BytesIO(adapted)) as image:
        assert image.size == (300, 300)
        assert image.getpixel((150, 5)) == (255, 0, 0)

from io import BytesIO

import pytest
from PIL import Image

from src.services.qqcc_video_frame_adapter import (
    QqccVideoFrameAdaptationError,
    adapt_qqcc_video_frame_bytes,
    adapt_qqcc_video_frame_file,
)


def _image_bytes(size: tuple[int, int], *, image_format: str = "PNG") -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color=(200, 100, 50)).save(output, format=image_format)
    return output.getvalue()


@pytest.mark.parametrize(
    ("source_size", "aspect_ratio", "expected_size"),
    [
        ((400, 300), "9:16", (162, 288)),
        ((300, 400), "16:9", (288, 162)),
        ((401, 300), "1:1", (300, 300)),
    ],
)
def test_adapt_bytes_center_crops_to_exact_ratio_without_upscaling(
    source_size: tuple[int, int],
    aspect_ratio: str,
    expected_size: tuple[int, int],
):
    adapted = adapt_qqcc_video_frame_bytes(
        _image_bytes(source_size),
        aspect_ratio=aspect_ratio,
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
    )

    assert result != str(source)
    assert result.endswith(".png")
    with Image.open(result) as image:
        assert image.size == (300, 300)


def test_center_crop_uses_the_middle_of_the_source_image():
    source = Image.new("RGB", (10, 4))
    for x in range(10):
        for y in range(4):
            source.putpixel((x, y), (x * 20, 0, 0))
    content = BytesIO()
    source.save(content, format="PNG")

    adapted = adapt_qqcc_video_frame_bytes(content.getvalue(), aspect_ratio="1:1")

    with Image.open(BytesIO(adapted)) as image:
        assert image.getpixel((0, 0)) == (60, 0, 0)
        assert image.getpixel((3, 0)) == (120, 0, 0)


def test_exif_orientation_is_applied_before_cropping():
    source = Image.new("RGB", (40, 20), "blue")
    exif = source.getexif()
    exif[274] = 6
    content = BytesIO()
    source.save(content, format="JPEG", exif=exif)

    adapted = adapt_qqcc_video_frame_bytes(
        content.getvalue(),
        aspect_ratio="9:16",
    )

    with Image.open(BytesIO(adapted)) as image:
        assert image.size == (18, 32)


def test_reapplying_the_same_ratio_is_content_idempotent():
    first = adapt_qqcc_video_frame_bytes(
        _image_bytes((400, 300)),
        aspect_ratio="16:9",
    )

    second = adapt_qqcc_video_frame_bytes(first, aspect_ratio="16:9")

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

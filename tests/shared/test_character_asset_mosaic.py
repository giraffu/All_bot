import io

from PIL import Image

from shared.character_reference_sheet import compose_character_asset_mosaic


def _image_bytes(size: tuple[int, int], color: str) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return output.getvalue()


def test_character_asset_mosaic_accepts_a_single_arbitrary_view_without_padding():
    result = compose_character_asset_mosaic([(4, _image_bytes((400, 800), "red"))])

    with Image.open(io.BytesIO(result)) as mosaic:
        assert mosaic.size == (768, 1536)
        assert mosaic.getpixel((384, 768)) == (255, 0, 0)


def test_character_asset_mosaic_packs_ten_mixed_views_into_a_bounded_dense_canvas():
    payloads = [
        (
            index,
            _image_bytes(
                (360, 900) if index in {1, 2} else ((360, 640) if index % 2 else (640, 360)),
                "blue",
            ),
        )
        for index in range(10)
    ]

    result = compose_character_asset_mosaic(payloads)

    with Image.open(io.BytesIO(result)) as mosaic:
        assert max(mosaic.size) <= 1536
        assert min(mosaic.size) >= 400
        # Thin separators are allowed, but most pixels must carry reference content.
        colors = mosaic.getcolors(maxcolors=mosaic.width * mosaic.height)
        white_pixels = next((count for count, color in colors or [] if color == (255, 255, 255)), 0)
        assert white_pixels / (mosaic.width * mosaic.height) < 0.05


def test_character_asset_mosaic_places_full_body_strips_at_left_and_stacks_others():
    result = compose_character_asset_mosaic([
        (0, _image_bytes((500, 500), "blue")),
        (1, _image_bytes((240, 960), "red")),
        (2, _image_bytes((240, 960), "green")),
        (3, _image_bytes((500, 500), "yellow")),
        (4, _image_bytes((500, 500), "purple")),
    ])

    with Image.open(io.BytesIO(result)) as mosaic:
        left_top = mosaic.getpixel((mosaic.width // 16, mosaic.height // 4))
        second_strip = mosaic.getpixel((mosaic.width * 3 // 16, mosaic.height // 4))
        right_top = mosaic.getpixel((mosaic.width * 2 // 5, mosaic.height // 4))
        right_bottom = mosaic.getpixel((mosaic.width * 2 // 5, mosaic.height * 3 // 4))
        assert left_top == (255, 0, 0)
        assert second_strip == (0, 128, 0)
        assert right_top in {(0, 0, 255), (255, 255, 0), (128, 0, 128)}
        assert right_bottom in {(0, 0, 255), (255, 255, 0), (128, 0, 128)}
        assert right_top != right_bottom


def test_character_asset_mosaic_rejects_duplicate_slots_and_more_than_ten_views():
    payload = _image_bytes((64, 64), "green")

    try:
        compose_character_asset_mosaic([(0, payload), (0, payload)])
    except RuntimeError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("duplicate slots must be rejected")

    try:
        compose_character_asset_mosaic([(index, payload) for index in range(11)])
    except RuntimeError as exc:
        assert "at most 10" in str(exc)
    else:
        raise AssertionError("more than ten views must be rejected")

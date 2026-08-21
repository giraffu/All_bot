from __future__ import annotations

import io
from collections.abc import Iterable

from PIL import Image, ImageOps

INGREDIENTS_CHARACTER_PANEL_SIZE = (1536, 896)
INGREDIENTS_CHARACTER_PANEL_VERSION = "ingredients-character-panel-v3"
CHARACTER_ASSET_MOSAIC_VERSION = "character-asset-mosaic-v1"
CHARACTER_ASSET_MOSAIC_MAX_VIEWS = 10
CHARACTER_ASSET_MOSAIC_MAX_EDGE = 1536
CHARACTER_ASSET_MOSAIC_GUTTER = 8

_FACE_SLOT_PRIORITY = (0, 2, 1)
_BODY_SLOT_PRIORITY = (3, 4, 5)


def _decode_view(slot: int, payload: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(payload)) as source:
            source.load()
            return ImageOps.exif_transpose(source).convert("RGB")
    except Exception as exc:
        raise RuntimeError(f"corrupt character view in slot {slot + 1}") from exc


def _contain_on_white(
    source: Image.Image,
    *,
    size: tuple[int, int],
) -> Image.Image:
    source_aspect = source.width / source.height
    target_aspect = size[0] / size[1]
    if source_aspect >= target_aspect:
        return ImageOps.fit(
            source,
            size,
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
    contained = ImageOps.contain(source, size, Image.Resampling.LANCZOS)
    tile = Image.new("RGB", size, "white")
    tile.paste(
        contained,
        ((size[0] - contained.width) // 2, (size[1] - contained.height) // 2),
    )
    return tile


def compose_ingredients_character_panel(
    payloads: Iterable[tuple[int, bytes]],
) -> bytes:
    """Build the single character panel used by LTX Ingredients.

    The official Ingredients example treats the character turnaround as one
    visual ingredient: one dominant face crop followed by front/side/back
    full-body views. It must not be represented as six equal scene panels,
    because those panels can be interpreted as multiple requested subjects.
    """

    decoded: dict[int, Image.Image] = {}
    for slot, payload in payloads:
        if slot in decoded:
            raise RuntimeError(f"duplicate character view in slot {slot + 1}")
        decoded[slot] = _decode_view(slot, payload)
    if len(decoded) < 2:
        raise RuntimeError("Ingredients character panel requires at least two views")

    primary_slot = next(
        (slot for slot in _FACE_SLOT_PRIORITY if slot in decoded),
        min(decoded),
    )
    secondary_slots = [
        slot for slot in _BODY_SLOT_PRIORITY if slot in decoded and slot != primary_slot
    ]
    secondary_slots.extend(
        slot
        for slot in (*_FACE_SLOT_PRIORITY, *sorted(decoded))
        if slot in decoded
        and slot != primary_slot
        and slot not in secondary_slots
    )
    secondary_slots = secondary_slots[:3]

    canvas_width, canvas_height = INGREDIENTS_CHARACTER_PANEL_SIZE
    primary_width = 576
    canvas = Image.new("RGB", INGREDIENTS_CHARACTER_PANEL_SIZE, "white")
    primary = ImageOps.fit(
        decoded[primary_slot],
        (primary_width, canvas_height),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.42),
    )
    canvas.paste(primary, (0, 0))

    remaining_width = canvas_width - primary_width
    column_width = remaining_width // len(secondary_slots)
    body_height = 640
    body_top = (canvas_height - body_height) // 2
    for index, slot in enumerate(secondary_slots):
        width = (
            remaining_width - column_width * index
            if index == len(secondary_slots) - 1
            else column_width
        )
        tile = _contain_on_white(
            decoded[slot],
            size=(width, body_height),
        )
        canvas.paste(tile, (primary_width + column_width * index, body_top))

    output = io.BytesIO()
    canvas.save(
        output,
        format="PNG",
        optimize=True,
        pnginfo=None,
    )
    return output.getvalue()


def compose_character_asset_mosaic(
    payloads: Iterable[tuple[int, bytes]],
) -> bytes:
    """Compose one dense H3 character reference from 1-10 optional sub-images.

    Nude and clothed full-body slots become narrow left columns. Every other
    present slot flows into two-row columns; missing slots do not reserve holes
    and an odd final detail expands to the full height of its last column.
    """

    decoded: dict[int, Image.Image] = {}
    for slot, payload in payloads:
        if slot in decoded:
            raise RuntimeError(f"duplicate character view in slot {slot + 1}")
        decoded[slot] = _decode_view(slot, payload)
    if not decoded:
        raise RuntimeError("character mosaic requires at least one view")
    if len(decoded) > CHARACTER_ASSET_MOSAIC_MAX_VIEWS:
        raise RuntimeError("character mosaic accepts at most 10 views")

    ordered_slots = sorted(decoded)
    images = [decoded[slot] for slot in ordered_slots]
    if len(images) == 1:
        source = images[0]
        scale = CHARACTER_ASSET_MOSAIC_MAX_EDGE / max(source.size)
        size = (
            max(1, round(source.width * scale)),
            max(1, round(source.height * scale)),
        )
        canvas = source.resize(size, Image.Resampling.LANCZOS)
    else:
        gutter = CHARACTER_ASSET_MOSAIC_GUTTER
        raw_height = CHARACTER_ASSET_MOSAIC_MAX_EDGE
        body_slots = [slot for slot in (1, 2) if slot in decoded]
        detail_slots = [slot for slot in ordered_slots if slot not in body_slots]

        columns: list[tuple[list[int], int]] = []
        for slot in body_slots:
            image = decoded[slot]
            natural_width = round(raw_height * image.width / image.height)
            columns.append(([slot], max(220, min(420, natural_width))))
        for index in range(0, len(detail_slots), 2):
            slots = detail_slots[index : index + 2]
            if len(slots) == 1:
                image = decoded[slots[0]]
                natural_width = round(raw_height * image.width / image.height)
                width = max(360, min(1024, natural_width))
            else:
                row_height = (raw_height - gutter) // 2
                natural_width = max(
                    round(row_height * decoded[slot].width / decoded[slot].height)
                    for slot in slots
                )
                width = max(360, min(1024, natural_width))
            columns.append((slots, width))

        raw_width = sum(width for _, width in columns) + gutter * (len(columns) - 1)
        scale = min(1.0, CHARACTER_ASSET_MOSAIC_MAX_EDGE / max(raw_width, raw_height))
        canvas_width = max(1, round(raw_width * scale))
        canvas_height = max(1, round(raw_height * scale))
        scaled_gutter = max(1, round(gutter * scale))
        canvas = Image.new("RGB", (canvas_width, canvas_height), "white")

        x = 0
        for column_index, (slots, raw_column_width) in enumerate(columns):
            column_width = (
                canvas_width - x
                if column_index == len(columns) - 1
                else max(1, round(raw_column_width * scale))
            )
            if len(slots) == 1:
                if slots[0] in body_slots:
                    tile = _contain_on_white(
                        decoded[slots[0]],
                        size=(column_width, canvas_height),
                    )
                else:
                    tile = ImageOps.fit(
                        decoded[slots[0]],
                        (column_width, canvas_height),
                        method=Image.Resampling.LANCZOS,
                        centering=(0.5, 0.5),
                    )
                canvas.paste(tile, (x, 0))
            else:
                top_height = (canvas_height - scaled_gutter) // 2
                bottom_height = canvas_height - scaled_gutter - top_height
                for row_index, (slot, height) in enumerate(
                    zip(slots, (top_height, bottom_height))
                ):
                    tile = ImageOps.fit(
                        decoded[slot],
                        (column_width, height),
                        method=Image.Resampling.LANCZOS,
                        centering=(0.5, 0.5),
                    )
                    canvas.paste(tile, (x, 0 if row_index == 0 else top_height + scaled_gutter))
            x += column_width + scaled_gutter

    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=True, pnginfo=None)
    return output.getvalue()

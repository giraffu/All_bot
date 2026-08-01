from __future__ import annotations

import io
from collections.abc import Iterable

from PIL import Image, ImageOps

INGREDIENTS_CHARACTER_PANEL_SIZE = (1536, 896)
INGREDIENTS_CHARACTER_PANEL_VERSION = "ingredients-character-panel-v3"

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

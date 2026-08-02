from __future__ import annotations

import base64
import io

from PIL import Image


def image_bytes_to_data_url(payload: bytes, *, max_long_edge: int = 1536) -> str:
    with Image.open(io.BytesIO(payload)) as image:
        image.load()
        if image.format not in {"PNG", "JPEG", "WEBP"}:
            raise ValueError("unsupported image format")
        image = image.convert("RGB")
        if max(image.size) > max_long_edge:
            image.thumbnail((max_long_edge, max_long_edge), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=90, optimize=True)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


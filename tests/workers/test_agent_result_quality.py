import io
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
WORKER_DIR = ROOT / "workers" / "comfy_agent"
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

from agent_result_quality import assess_i2i_pro_output_quality  # noqa: E402


def _png_bytes(color: tuple[int, int, int], *, size: tuple[int, int] = (32, 32)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_i2i_pro_quality_flags_black_image():
    issue = assess_i2i_pro_output_quality(primary_bytes=_png_bytes((0, 0, 0)))

    assert issue is not None
    assert issue.reason == "black_image"


def test_i2i_pro_quality_flags_output_too_similar_to_reference():
    reference = _png_bytes((120, 130, 140))
    output = _png_bytes((125, 135, 145))

    issue = assess_i2i_pro_output_quality(
        primary_bytes=output,
        reference_bytes=reference,
    )

    assert issue is not None
    assert issue.reason == "too_similar_to_input"


def test_i2i_pro_quality_accepts_changed_image():
    reference = _png_bytes((20, 30, 40))
    output = _png_bytes((220, 210, 200))

    assert (
        assess_i2i_pro_output_quality(
            primary_bytes=output,
            reference_bytes=reference,
        )
        is None
    )

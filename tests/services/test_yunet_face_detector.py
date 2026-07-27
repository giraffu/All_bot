from pathlib import Path

import pytest
from PIL import Image

from src.services.smart_image_aspect_service import FocusDetectionUnavailable
from src.services.yunet_face_detector import YuNetFaceDetector


def test_missing_model_fails_as_an_unavailable_optional_detector(tmp_path: Path):
    detector = YuNetFaceDetector(model_path=tmp_path / "missing.onnx")

    with pytest.raises(FocusDetectionUnavailable, match="model"):
        detector(Image.new("RGB", (320, 240), "white"))

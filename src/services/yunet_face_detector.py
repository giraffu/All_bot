from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Final

from PIL import Image

from src.services.smart_image_aspect_service import (
    FocusDetectionUnavailable,
    FocusRegion,
)

DEFAULT_YUNET_MODEL_PATH: Final = Path(
    os.getenv(
        "ALLBOT_YUNET_MODEL_PATH",
        "/opt/allbot/models/face_detection_yunet_2023mar.onnx",
    )
)
DEFAULT_DETECTION_LONG_EDGE: Final = 1280


@dataclass(frozen=True, slots=True)
class YuNetFaceDetector:
    model_path: Path = DEFAULT_YUNET_MODEL_PATH
    score_threshold: float = 0.75
    nms_threshold: float = 0.3
    top_k: int = 50
    detection_long_edge: int = DEFAULT_DETECTION_LONG_EDGE

    def __call__(self, image: Image.Image) -> list[FocusRegion]:
        if not self.model_path.is_file():
            raise FocusDetectionUnavailable(
                f"YuNet face detector model is unavailable: {self.model_path}"
            )
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            raise FocusDetectionUnavailable(
                "YuNet face detector runtime is unavailable"
            ) from exc

        try:
            source = image.convert("RGB")
            scale = min(
                1.0,
                self.detection_long_edge / max(source.width, source.height),
            )
            detection_size = (
                max(1, round(source.width * scale)),
                max(1, round(source.height * scale)),
            )
            if detection_size != source.size:
                detection_image = source.resize(
                    detection_size,
                    Image.Resampling.LANCZOS,
                )
            else:
                detection_image = source
            rgb = np.asarray(detection_image)
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            detector = cv2.FaceDetectorYN.create(
                str(self.model_path),
                "",
                detection_size,
                self.score_threshold,
                self.nms_threshold,
                self.top_k,
            )
            _, faces = detector.detect(bgr)
        except Exception as exc:
            raise FocusDetectionUnavailable(
                "YuNet face detection failed"
            ) from exc

        if faces is None:
            return []
        inverse_scale = 1 / scale
        regions: list[FocusRegion] = []
        for face in faces:
            left, top, width, height = map(float, face[:4])
            confidence = float(face[-1])
            regions.append(
                FocusRegion(
                    left=round(left * inverse_scale),
                    top=round(top * inverse_scale),
                    right=round((left + width) * inverse_scale),
                    bottom=round((top + height) * inverse_scale),
                    confidence=confidence,
                )
            )
        return regions


_default_detector = YuNetFaceDetector()


def detect_yunet_focus_regions(image: Image.Image) -> list[FocusRegion]:
    return _default_detector(image)

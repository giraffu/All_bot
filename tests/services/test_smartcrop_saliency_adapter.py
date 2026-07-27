from PIL import Image

from src.services.smartcrop_saliency_adapter import smartcrop_saliency_crop


def test_saliency_analysis_is_bounded_and_returns_an_exact_crop_box():
    calls = []

    class FakeSmartCrop:
        def crop(self, image, width, height, **kwargs):
            calls.append((image.size, width, height, kwargs))
            return {
                "top_crop": {
                    "x": 64,
                    "y": 0,
                    "width": 192,
                    "height": 192,
                }
            }

    box = smartcrop_saliency_crop(
        Image.new("RGB", (4000, 3000), "white"),
        (3000, 3000),
        smartcrop_factory=FakeSmartCrop,
    )

    assert calls[0][:3] == ((256, 192), 192, 192)
    assert calls[0][3]["min_scale"] == 1
    assert box == (1000, 0, 4000, 3000)

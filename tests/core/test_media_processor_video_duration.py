import json
from types import SimpleNamespace

from src import media_processor


def test_extract_video_duration_seconds_keeps_fractional_precision(monkeypatch):
    def run(command, **kwargs):
        assert command[-1] == "https://storage.example/source.mp4"
        assert kwargs["timeout"] == 30
        return SimpleNamespace(
            stdout=json.dumps({"format": {"duration": "10.125000"}}),
        )

    monkeypatch.setattr(media_processor.subprocess, "run", run)

    assert (
        media_processor._extract_video_duration_seconds_with_ffprobe(
            "https://storage.example/source.mp4"
        )
        == 10.125
    )

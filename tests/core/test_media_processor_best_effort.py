
from src import media_processor


def test_extract_media_metadata_from_bytes_best_effort_returns_fallback_on_probe_error(
    monkeypatch,
):
    def raise_probe_error(_input_source: str):
        raise RuntimeError("ffprobe boom")

    monkeypatch.setattr(
        media_processor, "_extract_video_metadata_with_ffprobe", raise_probe_error
    )

    fallback = (720, 720, 8)
    result = media_processor.extract_media_metadata_from_bytes_best_effort(
        b"fake-video-bytes",
        "video",
        "mp4",
        fallback,
    )

    assert result == fallback

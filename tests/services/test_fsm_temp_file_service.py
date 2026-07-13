from src.services import fsm_temp_file_service


def test_cleanup_fsm_user_data_removes_fsm_state_and_temp_files(tmp_path, monkeypatch):
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    image_path = temp_root / "image.png"
    end_image_path = temp_root / "end.png"
    video_path = temp_root / "video.mp4"
    list_image_path = temp_root / "list.png"
    last_face_image_path = temp_root / "last-face.png"
    external_path = tmp_path / "outside.png"
    sibling_prefix_path = tmp_path / "tmp-sibling.png"
    for path in (
        image_path,
        end_image_path,
        video_path,
        list_image_path,
        last_face_image_path,
        external_path,
        sibling_prefix_path,
    ):
        path.write_text("x")

    monkeypatch.setattr(fsm_temp_file_service, "TMP_DIR", str(temp_root))

    user_data = {
        "language_code": "zh",
        "in_conversation": "LTX_VIDEO",
        "ltx_video_data": {
            "image_path": str(image_path),
            "end_image_path": str(end_image_path),
            "nested": {"video_path": str(video_path)},
        },
        "quick_image_data": {
            "images": [str(list_image_path), str(external_path), str(sibling_prefix_path)],
        },
        "last_face_image": str(last_face_image_path),
        "mode": "none",
    }

    collected = fsm_temp_file_service.cleanup_fsm_user_data(user_data)

    assert str(image_path) in collected
    assert str(end_image_path) in collected
    assert str(video_path) in collected
    assert str(list_image_path) in collected
    assert str(last_face_image_path) in collected
    assert not image_path.exists()
    assert not end_image_path.exists()
    assert not video_path.exists()
    assert not list_image_path.exists()
    assert not last_face_image_path.exists()
    assert external_path.exists()
    assert sibling_prefix_path.exists()
    assert user_data == {"language_code": "zh", "mode": "none"}


def test_cleanup_fsm_user_data_handles_empty_user_data():
    assert fsm_temp_file_service.cleanup_fsm_user_data(None) == []

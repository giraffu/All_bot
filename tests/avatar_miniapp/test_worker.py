from src.avatar_miniapp.worker import ffmpeg_command, safe_error_code


def test_ffmpeg_command_is_fixed_and_bounded():
    command = ffmpeg_command(
        input_pattern="/tmp/frames/frame_%04d.png",
        output_path="/tmp/output.mp4",
        fps=24,
    )

    assert command == [
        "ffmpeg",
        "-y",
        "-framerate",
        "24",
        "-i",
        "/tmp/frames/frame_%04d.png",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "/tmp/output.mp4",
    ]


def test_worker_error_code_does_not_expose_exception_text():
    assert safe_error_code(RuntimeError("token=secret path=/private")) == "RUNTIMEERROR"

parsed = {"status": "done", "result_path": "foo/bar.mp4", "progress": 1.0}
task_type = parsed.get("task_type", "edit")
is_video = task_type in ["face_video", "txt2video", "video_lora", "custom_video", "perfect_video_insert", "doggy_style", "blowjob", "undress_tongue", "closeup_blowjob", "ltx_video"]
ext = "mp4" if is_video else "png"
print(f"Parsed task_type: {task_type}")
print(f"is_video: {is_video}")
print(f"ext: {ext}")

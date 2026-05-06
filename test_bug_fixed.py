VIDEO_TASK_TYPES = [
    "doggy_style", "perfect_video_insert", "blowjob", "undress_tongue", 
    "closeup_blowjob", "custom_video", "face_video", "face_video_step1", 
    "face_video_step2", "video_lora", "ltx_video", 
    "video_edit", "perfect_video_edit"
]
parsed = {"status": "done", "result_path": "foo/bar.mp4", "progress": 1.0}
task_type = parsed.get("task_type", "edit")
is_video = task_type in VIDEO_TASK_TYPES
ext = "mp4" if is_video else "png"
print(f"Parsed task_type: {task_type}")
print(f"is_video: {is_video}")
print(f"ext: {ext}")

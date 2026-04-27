import re

with open("src/core/task_core.py", "r", encoding="utf-8") as f:
    content = f.read()

# Remove core_submit_face_video and core_submit_generation_task
content = re.sub(r'async def core_submit_face_video.*?return False, user_msg, None, None, None, registry_task_id\n\n', '', content, flags=re.DOTALL)
content = re.sub(r'async def core_submit_generation_task.*?return False, user_msg, None, \[\], registry_task_id\n\n', '', content, flags=re.DOTALL)

# Refactor process_and_submit_task
# Find the start of the `if task_type == "face_swap":`
start_marker = '            if task_type == "face_swap":'
end_marker = '                )'

start_idx = content.find(start_marker)
if start_idx != -1:
    end_idx = content.find('            if not success or not backend_task_id:', start_idx)
    
    new_logic = """
            # 1. 统一处理输入图片/视频上传
            paths_to_upload = strategy.get_file_paths_to_upload(inputs)
            saved_inputs = []
            from src.logger import UserLogger
            user_logger = UserLogger(user_id, username)
            for path in paths_to_upload:
                processed_img = await _process_input_path(user_logger, path)
                if processed_img:
                    saved_inputs.append(processed_img)
            
            inputs["saved_input_images"] = saved_inputs
            inputs["prompt"] = prompt  # Ensure updated prompt is in inputs
            metadata = strategy.get_metadata(inputs)
            
            # 2. 统一落库 TaskRegistry
            registry_task_id = await TaskRegistry.add_task(
                task_id=task_id,
                user_id=user_id,
                username=username,
                cost=cost,
                task_type=task_type,
                prompt=log_prompt,
                saved_input_images=metadata.get("saved_inputs", saved_inputs),
                is_video=is_video_task,
                priority=final_priority,
                allow_contribute=allow_contribute
            )
            
            # 3. 统一分发到后端 worker
            try:
                backend_task_id = await dispatch_to_worker(task_id, task_type, inputs, final_priority)
                if registry_task_id and backend_task_id:
                    await TaskRegistry.update_backend_task_id(registry_task_id, backend_task_id)
                if not backend_task_id:
                    raise Exception("Failed to submit task to backend API.")
                success = True
                msg = "Task submitted successfully"
            except Exception as e:
                logger.error(f"Dispatch to worker failed: {e}", exc_info=True)
                if registry_task_id:
                    try:
                        await TaskRegistry.mark_task_status(registry_task_id, "failed")
                    except Exception:
                        pass
                success = False
                backend_task_id = None
                error_msg = str(e)
                if any(kw in error_msg for kw in ["Circuit is open", "All connection attempts failed", "Connection refused", "timeout", "ConnectError"]):
                    msg = "当前服务器繁忙，请稍后再试"
                else:
                    msg = f"System error: {error_msg}"
"""
    content = content[:start_idx] + new_logic + content[end_idx:]

with open("src/core/task_core.py", "w", encoding="utf-8") as f:
    f.write(content)


from abc import ABC, abstractmethod
from typing import Dict, Any

from src.constants import TASK_COSTS, RESOLUTION_COST, DURATION_MULTIPLIER, MODE_I2I_PRO, MODE_FACESWAP_STEP1, LTX_RESOLUTION_COST, LTX_DURATION_MULTIPLIER
from src.services.image_service import image_service

class BaseTaskStrategy(ABC):
    @abstractmethod
    def get_cost(self, inputs: Dict[str, Any]) -> int:
        pass
        
    @abstractmethod
    def build_payload(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        pass
        
    @abstractmethod
    def get_metadata(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        pass
        
    @abstractmethod
    def get_file_paths_to_upload(self, inputs: Dict[str, Any]) -> list[str]:
        """返回需要上传到 MinIO 的文件路径列表"""
        pass
        
    @abstractmethod
    async def submit_task(self, task_id: str, inputs: Dict[str, Any], priority: int) -> str:
        """Responsible for sending the task to backend via image_service"""
        pass

class DefaultImageStrategy(BaseTaskStrategy):
    def __init__(self, mode: str):
        self.mode = mode
        
    def get_cost(self, inputs: Dict[str, Any]) -> int:
        from src.constants import MODE_EDIT, MODE_IMG2IMG_LORA
        if self.mode in [MODE_EDIT, "edit", MODE_IMG2IMG_LORA, "img2img_lora"]:
            return 6 if len(inputs.get("images", [])) >= 2 else 2
        return TASK_COSTS.get(self.mode, 2)
        
    def build_payload(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return inputs
        
    def get_metadata(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"saved_inputs": inputs.get("saved_input_images", [])}
        
    def get_file_paths_to_upload(self, inputs: Dict[str, Any]) -> list[str]:
        return inputs.get("images", [])
        
    async def submit_task(self, task_id: str, inputs: Dict[str, Any], priority: int) -> str:
        if self.mode in ["i2i_pro", MODE_I2I_PRO]:
            import random
            seed = random.randint(1, 9007199254740991)
            return await image_service.submit_i2i_pro_task(
                task_id,
                prompt=inputs.get("prompt"),
                image_path=inputs.get("saved_input_images", [])[0] if inputs.get("saved_input_images") else "",
                seed=seed,
                priority=priority
            )
        elif self.mode in ["img2img_lora", "MODE_IMG2IMG_LORA"]:
            return await image_service.submit_img2img_lora_task(
                task_id,
                prompt=inputs.get("prompt"),
                image_paths=inputs.get("saved_input_images", []),
                lora_name=inputs.get("lora_name", ""),
                negative_prompt=inputs.get("negative_prompt", " "),
                priority=priority,
                lora_strength=inputs.get("lora_strength", 1.0)
            )
        else:
            return await image_service.submit_task(
                task_id,
                prompt=inputs.get("prompt"),
                image_paths=inputs.get("saved_input_images", []),
                negative_prompt=inputs.get("negative_prompt", " "),
                priority=priority
            )

class FaceSwapStrategy(BaseTaskStrategy):
    def get_cost(self, inputs: Dict[str, Any]) -> int:
        return TASK_COSTS.get(MODE_FACESWAP_STEP1, 6)
        
    def build_payload(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return inputs
        
    def get_metadata(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        saved_images = inputs.get("saved_input_images", [])
        return {"saved_inputs": saved_images}
        
    def get_file_paths_to_upload(self, inputs: Dict[str, Any]) -> list[str]:
        # 按照原来的逻辑：先是 body_img (target_image)，再是 face_img (face_image)
        if "images" in inputs and len(inputs.get("images", [])) >= 2:
            return inputs["images"]
        return [inputs.get("target_image"), inputs.get("face_image")]
        
    async def submit_task(self, task_id: str, inputs: Dict[str, Any], priority: int) -> str:
        saved_images = inputs.get("saved_input_images", [])
        return await image_service.submit_face_swap_task(
            task_id,
            face_image_path=saved_images[1] if len(saved_images) > 1 else "",
            body_image_path=saved_images[0] if len(saved_images) > 0 else "",
            priority=priority
        )

class BaseVideoStrategy(BaseTaskStrategy):
    def __init__(self, mode: str):
        self.mode = mode

    def get_cost(self, inputs: Dict[str, Any]) -> int:
        resolution = inputs.get("resolution", 512)
        duration = inputs.get("duration", 5)
        
        res_str = f"{resolution}p" if isinstance(resolution, int) else str(resolution)
        if not res_str.endswith('p'):
            res_str += 'p'
        dur_str = f"{duration}s" if isinstance(duration, int) else str(duration)
        if not dur_str.endswith('s'):
            dur_str += 's'
            
        base_cost = RESOLUTION_COST.get(res_str, TASK_COSTS.get(self.mode, 6))
        multiplier = DURATION_MULTIPLIER.get(dur_str, 1.0)
        return int(base_cost * multiplier)
        
    def build_payload(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return inputs
        
    def get_metadata(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"saved_inputs": inputs.get("saved_input_images", [])}
        
    def get_file_paths_to_upload(self, inputs: Dict[str, Any]) -> list[str]:
        if self.mode == "face_video":
            if "images" in inputs and len(inputs.get("images", [])) >= 2:
                return inputs["images"]
            return [inputs.get("face_image"), inputs.get("target_video")]
        elif "images" in inputs:
            return inputs.get("images", [])
        return []
        
    async def submit_task(self, task_id: str, inputs: Dict[str, Any], priority: int) -> str:
        duration = inputs.get("duration", 5)
        if isinstance(duration, str):
            duration = int(duration.replace("s", ""))
            
        if duration >= 10:
            frame_length = 161
        elif duration >= 8:
            frame_length = 129
        else:
            frame_length = 81
            
        resolution = inputs.get("resolution", 512)
        if isinstance(resolution, str):
            resolution = int(resolution.replace("p", ""))
            
        prompt = inputs.get("prompt", "video")
        saved_images = inputs.get("saved_input_images", [])
        image_path = saved_images[0] if saved_images else ""
        
        if self.mode == "doggy_style":
            return await image_service.submit_perfect_video_insert_task(
                task_id, prompt=prompt, image_path=image_path, width=resolution, height=resolution, length=frame_length, priority=priority
            )
        elif self.mode == "video_lora" and inputs.get("lora_name"):
            return await image_service.submit_perfect_video_lora(
                task_id, prompt=prompt, image_path=image_path, lora_name=inputs.get("lora_name"), priority=priority,
                width=resolution, height=resolution, length=frame_length
            )
        elif self.mode == "face_video":
            face_img = saved_images[0] if len(saved_images) > 0 else ""
            video_path = saved_images[1] if len(saved_images) > 1 else ""
            dur_frames = 161 if duration >= 10 else 121
            return await image_service.submit_face_video(
                task_id, face_image_path=face_img, video_path=video_path,
                resolution=resolution, duration=dur_frames, priority=priority
            )
        else:
            return await image_service.submit_perfect_video_edit(
                task_id, prompt=prompt, image_path=image_path, priority=priority,
                width=resolution, height=resolution, length=frame_length
            )

class LtxVideoStrategy(BaseTaskStrategy):
    def get_cost(self, inputs: Dict[str, Any]) -> int:
        resolution = inputs.get("resolution", 512)
        duration = inputs.get("duration", 5)
        
        res_str = str(resolution)
        dur_str = f"{duration}s" if isinstance(duration, int) else str(duration)
        if not dur_str.endswith('s'):
            dur_str += 's'
        base_cost = LTX_RESOLUTION_COST.get(res_str, 10)
        multiplier = LTX_DURATION_MULTIPLIER.get(dur_str, 1.0)
        return int(base_cost * multiplier)
        
    def build_payload(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return inputs
        
    def get_metadata(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"saved_inputs": inputs.get("saved_input_images", [])}
        
    def get_file_paths_to_upload(self, inputs: Dict[str, Any]) -> list[str]:
        return inputs.get("images", [])
        
    async def submit_task(self, task_id: str, inputs: Dict[str, Any], priority: int) -> str:
        resolution = inputs.get("resolution", 512)
        duration = inputs.get("duration", 5)
        res_str = str(resolution)
        try:
            width, height = map(int, res_str.split('x'))
        except:
            width, height = 1280, 704
            
        saved_images = inputs.get("saved_input_images", [])
        image_path = saved_images[0] if saved_images else ""
        return await image_service.submit_ltx_video_task(
            task_id, 
            prompt=inputs.get("prompt", "ltx video"), 
            image_path=image_path, 
            width=width, 
            height=height, 
            length=duration, 
            priority=priority
        )

class StrategyFactory:
    @staticmethod
    def get_strategy(task_type: str) -> BaseTaskStrategy:
        video_types = ["doggy_style", "perfect_video_insert", "blowjob", "undress_tongue", "closeup_blowjob", "custom_video", "face_video", "video_lora"]
        if task_type == "face_swap":
            return FaceSwapStrategy()
        elif task_type == "ltx_video":
            return LtxVideoStrategy()
        elif task_type in video_types:
            return BaseVideoStrategy(task_type)
        elif task_type in ["i2i_pro", "MODE_I2I_PRO"]:
            return DefaultImageStrategy(task_type)
        else:
            return DefaultImageStrategy(task_type)

async def dispatch_to_worker(task_id: str, task_type: str, inputs: Dict[str, Any], priority: int) -> str:
    """统一的请求发送口"""
    strategy = StrategyFactory.get_strategy(task_type)
    return await strategy.submit_task(task_id, inputs, priority)

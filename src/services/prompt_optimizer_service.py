import os
import asyncio
import httpx
import base64
from io import BytesIO
from PIL import Image

class PromptOptimizerService:
    # 限制同时调用大模型的并发数为 2
    _semaphore = asyncio.Semaphore(2)

    @staticmethod
    def _resize_image_if_needed(image_path: str, max_size: int = 1024, max_mb: float = 5.0) -> str:
        """
        读取本地图片，如果尺寸过大则等比例缩小，返回 Base64 编码字符串。
        """
        # 检查文件大小
        file_size_mb = os.path.getsize(image_path) / (1024 * 1024)
        
        with Image.open(image_path) as img:
            # 如果分辨率大于 max_size，或者体积大于 max_mb，则进行缩放
            if img.width > max_size or img.height > max_size or file_size_mb > max_mb:
                # 计算等比例缩放
                img.thumbnail((max_size, max_size))
                
            # 转为 Base64
            buffered = BytesIO()
            # 统一转为 RGB 以支持 JPEG
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(buffered, format="JPEG", quality=85)
            img_bytes = buffered.getvalue()
            
            return base64.b64encode(img_bytes).decode('utf-8')

    @staticmethod
    async def optimize_video_prompt(user_prompt: str, image_base64: str) -> str:
        api_base = os.getenv("LLM_API_BASE", "http://127.0.0.1:1234/v1")
        model_name = os.getenv("LLM_MODEL_NAME", "qwen3.5-35b-a3b-uncensored-hauhaucs-aggressive")
        
        system_prompt = """You are an expert AI video generation prompt engineer.
Your task is to recognize the user's intent based on the provided initial image and their partial prompt, and generate a highly detailed, optimized prompt following excellent writing styles and conventions.

Key Requirements:
1. The output MUST be entirely in English.
2. DO NOT use dynamic prompt syntax with curly braces (e.g., {a|b}). Generate a single, concrete, regular prompt by choosing specific descriptors that best fit the image and intent.
3. Trigger Words Requirement:
   If the user's intent matches one of the following specific actions, you MUST start your prompt with exactly two trigger words separated by a comma:
   - Style Trigger (Pick one): "3D", "Real Video", or "Amateur"
   - Action Trigger (Pick the matching one):
     * "m15510n4ry" for Missionary
     * "bl0wj0b" for Blowjob
     * "d0ubl3_bj" for Double Blowjob
     * "c0wg1rl" for Reverse Cowgirl
     * "d0gg1e" for Doggy style / rear entry
   Format: "[Style Trigger], [Action Trigger], [Rest of the prompt]"
   If the intent DOES NOT match any of these 5 actions, DO NOT include any trigger words at all.
4. Systematically describe the following elements in extreme detail:
   - Visual format and perspective (e.g., 4k UHD footage, vintage 1970s, side-shot, close-up view, POV).
   - Character features exactly matching the initial image (skin tone, hair color/style, body type, clothing/accessories, expressions).
   - Specific actions, poses, and physical interactions clearly conveying the user's intent. Be explicit and anatomical if required by the intent. Note: for missionary, specify the woman is on her back.
   - Background environment and cinematic lighting (e.g., even highlighting natural skin tones, cinematic yet voyeuristic).
5. Do NOT include any conversational filler, explanations, or greetings. Output ONLY the optimized prompt.

Style Reference (Follow this highly descriptive, specific format):
- "Real Video, bl0wj0b, A close-up view of a single petite woman performing a blowjob on a man's erect penis. The girl is nearly naked except for a slutty belt barely covering her fair skin and small breasts and pink hair. Her nails are manicured with a glittery design as she grasps the base of the penis... The lighting is cinematic yet voyeuristic."
- "Amateur, c0wg1rl, A 4k UHD footage side-shot of a pale goth girl with her arms behind her back and legs spread apart in the reverse cowgirl position. She has olive skin, huge breasts and wet black hair. Her eyes are closed and she has a slight smile of lust on her face... At the bottom of the frame a man's erect penis is thrusting into her vagina."
- "3D, m15510n4ry, A shot of missionary sex and a detailed view of a woman's vagina and a man's erect penis which is penetrating her. The woman's skin is light... The background is a fancy bedroom where she is at the edge of the white bed laying on her back and he is between her spread legs. The lighting is even highlighting the natural skin tones and textures."

Extract visual cues from the image and combine them with the user's text to form a cohesive, rich, and highly detailed prompt."""

        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Original idea: {user_prompt}\nPlease optimize this prompt based on the provided image."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 1024,
            "temperature": 0.7
        }

        async with PromptOptimizerService._semaphore:
            async with httpx.AsyncClient(timeout=120.0) as client:
                try:
                    response = await client.post(f"{api_base}/chat/completions", json=payload)
                    response.raise_for_status()
                    data = response.json()
                    optimized_prompt = data["choices"][0]["message"]["content"].strip()
                    return optimized_prompt
                except httpx.TimeoutException:
                    raise TimeoutError("大模型服务响应超时")
                except httpx.RequestError as e:
                    raise ConnectionError(f"请求大模型服务失败: {str(e)}")
                except Exception as e:
                    raise RuntimeError(f"优化提示词时发生未知错误: {str(e)}")

import asyncio
import httpx
import os

async def main():
    with open("test.jpg", "wb") as f:
        f.write(b"test")
        
    async with httpx.AsyncClient(trust_env=False) as client:
        files = {"image": ("test.jpg", open("test.jpg", "rb"), "image/jpeg")}
        data = {
            "prompt": "hello",
            "width": 720,
            "height": 720
        }
        r = await client.post("http://127.0.0.1:8004/perfect_video_edit", files=files, data=data)
        print("Status:", r.status_code)
        print("Response:", r.text)

asyncio.run(main())

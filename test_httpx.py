import httpx
import asyncio

async def main():
    try:
        data = {"width": 720, "height": 720, "prompt": "hello"}
        files = {"image": ("test.jpg", b"fake", "image/jpeg")}
        req = httpx.Request("POST", "http://127.0.0.1:8000", data=data, files=files)
        content = req.read()
        print(content)
    except Exception as e:
        print("Error:", e)

asyncio.run(main())

import asyncio
import httpx

async def main():
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://192.168.1.226:8003/openapi.json")
            print("Status:", resp.status_code)
            if resp.status_code == 200:
                with open("openapi.json", "w") as f:
                    f.write(resp.text)
    except Exception as e:
        print("Error:", e)

asyncio.run(main())

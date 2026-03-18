import asyncio
from dashboard.backend.main import app
from httpx import AsyncClient, ASGITransport

async def test():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/users")
        print(response.status_code)
        if response.status_code == 200:
            print(response.json()[:2])

asyncio.run(test())

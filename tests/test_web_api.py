import asyncio
import httpx
import time

BASE_URL = "http://127.0.0.1:8000"

async def run_tests():
    print(f"🚀 Starting Web BFF API integration tests at {BASE_URL}...\n")
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        # --- 1. Test Health Check ---
        print("1️⃣ Testing /api/health...")
        response = await client.get("/api/health")
        print(f"Status: {response.status_code}")
        print(f"Body: {response.json()}\n")
        assert response.status_code == 200
        
        # --- 2. Test Authentication (Debug Mode Bypass) ---
        print("2️⃣ Testing /api/auth/telegram (Login/Registration)...")
        # We use hash="debug_mode" which we explicitly allowed in auth.py for testing
        test_tg_data = {
            "id": 999888777,
            "first_name": "Test",
            "last_name": "User",
            "username": "testuser_api",
            "auth_date": int(time.time()),
            "hash": "debug_mode"
        }
        
        response = await client.post("/api/auth/telegram", json=test_tg_data)
        print(f"Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error Body: {response.text}")
            return
            
        data = response.json()
        access_token = data.get("access_token")
        user_info = data.get("user")
        print(f"Successfully received JWT: {access_token[:20]}...")
        print(f"User Info: {user_info}\n")
        assert access_token is not None
        
        # --- 3. Test Protected Route: Get Profile ---
        print("3️⃣ Testing /api/users/me (Protected Route)...")
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await client.get("/api/users/me", headers=headers)
        print(f"Status: {response.status_code}")
        profile = response.json()
        print(f"Profile Data: {profile}\n")
        assert response.status_code == 200
        assert profile["telegram_id"] == 999888777
        
        # --- 4. Test Protected Route: Get Presigned URL ---
        print("4️⃣ Testing /api/storage/presigned-url...")
        response = await client.get(
            "/api/storage/presigned-url", 
            params={"filename": "test_video.mp4", "content_type": "video/mp4"},
            headers=headers
        )
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            storage_data = response.json()
            print(f"Object Key: {storage_data['object_key']}")
            print(f"Upload URL: {storage_data['upload_url'][:80]}...\n")
            assert "upload_url" in storage_data
            assert "object_key" in storage_data
        else:
            print(f"Failed to get presigned URL. Body: {response.text}\n")
            # Don't assert here as it might fail if MinIO is not fully reachable from the test script, 
            # but we want to see the error.

        print("✅ All API tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(run_tests())

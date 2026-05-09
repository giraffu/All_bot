import asyncio
import contextlib

async def get_db():
    print("DB Session started")
    try:
        yield "db_session"
    finally:
        print("DB Session closed")

async def test():
    async with contextlib.AsyncExitStack() as stack:
        db = await stack.enter_async_context(contextlib.asynccontextmanager(get_db)())
        print("In route handler, returning stream")
        
        async def stream():
            for i in range(3):
                print(f"Streaming {i}")
                await asyncio.sleep(0.1)
                yield f"data: {i}\n\n"
        
        # In real FastAPI, the response stream is consumed, THEN the stack exits.
        stream_gen = stream()
        async for chunk in stream_gen:
            pass
        print("Stream finished")
    print("Stack exited")

asyncio.run(test())

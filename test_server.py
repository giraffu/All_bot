from fastapi import FastAPI, Form, UploadFile, File
import uvicorn

app = FastAPI()

@app.post("/perfect_video_edit")
async def perfect_video_edit(
    image: UploadFile = File(...),
    prompt: str = Form(...),
    width: int = Form(512),
    height: int = Form(512)
):
    print(f"Received: prompt={prompt}, width={width}, height={height}")
    return {"task_id": "123"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004)

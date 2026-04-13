from pydantic import BaseModel

class req(BaseModel):
    prompt: str = ""

r = req()
r.prompt = "hello"
print(r.prompt)

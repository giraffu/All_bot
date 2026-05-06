from pydantic import BaseModel
class A(BaseModel):
    status: str

a = A(status="done", task_type="video")
print(a.dict())

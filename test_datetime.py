from datetime import datetime
from pydantic import BaseModel

class M(BaseModel):
    created_at: datetime

print(M(created_at=datetime.now()).model_dump_json())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def maintenance_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        print("OPTIONS seen in maintenance_middleware")
    return JSONResponse(status_code=503, content={"msg": "maintenance"})

@app.get("/")
def root():
    return {"msg": "ok"}

client = TestClient(app)
res = client.options("/", headers={"Origin": "http://localhost", "Access-Control-Request-Method": "GET"})
print("OPTIONS Response headers:", res.headers)
res = client.get("/", headers={"Origin": "http://localhost"})
print("GET Response headers:", res.headers)

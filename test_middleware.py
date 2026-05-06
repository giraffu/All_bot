from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

app = FastAPI()

@app.middleware("http")
async def maintenance_middleware(request: Request, call_next):
    return JSONResponse(status_code=503, content={"msg": "maintenance"})

# Add CORS AFTER @app.middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"Hello": "World"}

client = TestClient(app)
response = client.options("/", headers={"Origin": "http://example.com", "Access-Control-Request-Method": "GET"})
print("OPTIONS status:", response.status_code)
print("OPTIONS headers:", response.headers)

response = client.get("/", headers={"Origin": "http://example.com"})
print("GET status:", response.status_code)
print("GET headers:", response.headers)

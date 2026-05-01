import logging
from contextlib import asynccontextmanager

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from src.core.exceptions import DomainException, InsufficientCreditsError, AccessDeniedError

from src.database.core import engine
from src.web_api.routers import auth, gallery, storage, tasks, users, utils

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    # Startup: setup resources if needed
    logger.info("Web BFF API is starting up...")
    yield
    # Shutdown: cleanup resources
    logger.info("Web BFF API is shutting down...")
    await engine.dispose()

app = FastAPI(
    title="All_bot Web BFF API",
    description="Backend for Frontend serving the Vue3 App",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://web.aivison.it.com",
        "http://localhost:8085",
        "http://localhost:5173"
    ], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(CorrelationIdMiddleware, header_name="X-Trace-ID")

# --- Exception Handlers for i18n ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """
    Catch Pydantic validation errors and return a unified error code.
    This allows the Vue frontend to translate "Invalid field" messages via vue-i18n.
    """
    errors = exc.errors()
    error_details = [{"loc": err["loc"], "msg": err["msg"], "type": err["type"]} for err in errors]
    return JSONResponse(
        status_code=422,
        content={"code": 4220, "message": "Validation Error", "details": error_details}
    )

@app.exception_handler(InsufficientCreditsError)
async def insufficient_credits_exception_handler(request, exc: InsufficientCreditsError):
    return JSONResponse(
        status_code=402,
        content={
            "code": 4021, 
            "message": "Insufficient credits", 
            "intent": exc.intent,
            "data": {"current": exc.current, "cost": exc.cost}
        }
    )

@app.exception_handler(AccessDeniedError)
async def access_denied_exception_handler(request, exc: AccessDeniedError):
    return JSONResponse(
        status_code=403,
        content={
            "code": 4031, 
            "message": "Access Denied. Please join the required channel.", 
            "intent": exc.intent
        }
    )

@app.exception_handler(DomainException)
async def domain_exception_handler(request, exc: DomainException):
    return JSONResponse(
        status_code=400,
        content={
            "code": 4001, 
            "message": exc.message, 
            "intent": exc.intent
        }
    )

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(storage.router, prefix="/api/storage", tags=["Storage"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(gallery.router, prefix="/api/gallery", tags=["Gallery"])
app.include_router(utils.router, prefix="/api/utils", tags=["Utils"])

@app.get("/api/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "message": "Web BFF is running"}

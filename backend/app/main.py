"""
IMPACTMAP — FastAPI Application Entry Point.

Configures the application, mounts routers, and initializes
the database on startup.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.core.logging import logger
from app.api.repositories import router as repositories_router
from app.api.analysis import router as analysis_router
from app.api.benchmarks import router as benchmarks_router
from app.api.dashboard import router as dashboard_router
from app.api.copilot import router as copilot_router
from app.schemas.schemas import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: initialize DB on startup."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "AI-Assisted Code Impact Analysis & Intelligent Test Selection Platform. "
        "Analyze code dependencies, detect change impact, and select the right tests."
    ),
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow frontend dev server and production origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(repositories_router)
app.include_router(analysis_router)
app.include_router(benchmarks_router)
app.include_router(dashboard_router)
app.include_router(copilot_router)


@app.get("/api/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
        app_name=settings.APP_NAME,
    )

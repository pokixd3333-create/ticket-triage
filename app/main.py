import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.core.config import get_settings

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"

ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def configure_logging() -> None:
    """Configure root application logging using configured log level."""
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    configure_logging()

    application = FastAPI(
        title="Ticket Triage Assistant",
        description=(
            "REST API and web interface for classifying and structuring "
            "customer support messages using an LLM."
        ),
        version="0.1.0",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    application.include_router(api_router)

    application.mount(
        "/",
        StaticFiles(directory=FRONTEND_DIR, html=True, check_dir=False),
        name="frontend",
    )

    return application


app = create_app()

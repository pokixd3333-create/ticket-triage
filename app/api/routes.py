from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.llm import LLMClient, LLMServiceError
from app.core.models import (
    TicketCategory,
    TicketPriority,
    TriageRequest,
    TriageResult,
)
from app.core.triage import TriageProcessingError, triage

router = APIRouter(prefix="/api/v1", tags=["triage"])


class HealthResponse(BaseModel):
    """Health check response schema (FR-11)."""

    status: str = Field(default="ok", examples=["ok"])


class OptionsResponse(BaseModel):
    """Allowed categories and priorities schema (FR-11)."""

    categories: list[str] = Field(
        examples=[[c.value for c in TicketCategory]],
    )
    priorities: list[str] = Field(
        examples=[[p.value for p in TicketPriority]],
    )


class ErrorResponse(BaseModel):
    """Standard error payload returned on upstream failures (FR-10)."""

    error: str = Field(
        examples=["Upstream LLM service unavailable. Please try again later."],
    )


def get_llm_client() -> LLMClient | None:
    """Provide the LLM client dependency (overridden in API tests)."""
    return None


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
)
async def health_check() -> HealthResponse:
    """Return service health status (FR-11)."""
    return HealthResponse(status="ok")


@router.get(
    "/options",
    response_model=OptionsResponse,
    summary="List allowed triage categories and priorities",
)
async def get_options() -> OptionsResponse:
    """Return valid enum values for category and priority (FR-11)."""
    return OptionsResponse(
        categories=[category.value for category in TicketCategory],
        priorities=[priority.value for priority in TicketPriority],
    )


@router.post(
    "/triage",
    response_model=TriageResult,
    responses={
        200: {
            "description": "Structured triage record generated successfully.",
            "content": {
                "application/json": {
                    "example": {
                        "category": "billing",
                        "priority": "high",
                        "summary": "Customer charged twice for the November invoice.",
                        "reply_draft": (
                            "Hi Maria, thanks for flagging this duplicate charge. "
                            "We are reviewing your November billing statement now "
                            "and will follow up shortly."
                        ),
                        "confidence": 0.86,
                        "needs_review": False,
                        "prompt_version": "v1",
                        "warning": None,
                    }
                }
            },
        },
        422: {
            "description": "Validation error (empty or >10,000 char message).",
        },
        502: {
            "model": ErrorResponse,
            "description": "LLM provider or output validation failure after retries.",
        },
    },
    summary="Triage a raw customer support message",
)
async def triage_message(
    payload: TriageRequest,
    client: LLMClient | None = Depends(get_llm_client),
) -> TriageResult | JSONResponse:
    """Validate incoming message and run core triage pipeline (FR-8 to FR-10)."""
    try:
        return await triage(payload.message, client=client)
    except (LLMServiceError, TriageProcessingError):
        return JSONResponse(
            status_code=502,
            content={
                "error": "Upstream LLM service unavailable. Please try again later."
            },
        )

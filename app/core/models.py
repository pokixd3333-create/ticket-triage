import re
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

MAX_API_MESSAGE_LENGTH = 10_000
MAX_CORE_MESSAGE_LENGTH = 4_000


class TicketCategory(StrEnum):
    """Allowed support ticket categories (FR-1)."""

    BILLING = "billing"
    TECHNICAL = "technical"
    ACCOUNT = "account"
    FEATURE_REQUEST = "feature_request"
    OTHER = "other"


class TicketPriority(StrEnum):
    """Allowed support ticket priorities (FR-2)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


def _count_sentences(text: str) -> int:
    """Count sentences in a text block while ignoring decimal numbers."""
    cleaned = re.sub(r"\b\d+\.\d+\b", "0", text.strip())
    if not cleaned:
        return 0
    parts = [p.strip() for p in re.split(r"[.!?]+(?:\s+|$)", cleaned) if p.strip()]
    return len(parts)


class TriageRequest(BaseModel):
    """API request schema enforcing non-empty and max 10k char limits (FR-9)."""

    message: str = Field(..., description="Raw customer support message to triage.")

    @field_validator("message")
    @classmethod
    def validate_message_bounds(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Message cannot be empty or whitespace only.")
        if len(value) > MAX_API_MESSAGE_LENGTH:
            raise ValueError(
                f"Message exceeds maximum allowed length of "
                f"{MAX_API_MESSAGE_LENGTH} characters."
            )
        return value


class LLMResponseSchema(BaseModel):
    """Strict contract enforced on raw JSON output from the LLM (FR-1 to FR-5)."""

    category: TicketCategory
    priority: TicketPriority
    summary: str
    reply_draft: str
    confidence: float = Field(..., ge=0.0, le=1.0)

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Summary cannot be empty.")
        word_count = len(cleaned.split())
        if word_count > 20:
            raise ValueError(
                f"Summary must be 20 words or fewer (got {word_count} words)."
            )
        sentence_count = _count_sentences(cleaned)
        if sentence_count != 1:
            raise ValueError(
                f"Summary must be exactly one sentence (got {sentence_count})."
            )
        return cleaned

    @field_validator("reply_draft")
    @classmethod
    def validate_reply_draft(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Reply draft cannot be empty.")
        sentence_count = _count_sentences(cleaned)
        if not (2 <= sentence_count <= 4):
            raise ValueError(
                f"Reply draft must be 2 to 4 sentences long (got {sentence_count})."
            )
        return cleaned


class TriageResult(BaseModel):
    """Final validated triage record shared across API and CLI."""

    category: TicketCategory
    priority: TicketPriority
    summary: str
    reply_draft: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    needs_review: bool
    prompt_version: str
    warning: str | None = None

    @classmethod
    def from_llm_output(
        cls,
        llm_output: LLMResponseSchema,
        prompt_version: str,
        warning: str | None = None,
    ) -> "TriageResult":
        """Build final record and deterministically compute needs_review (FR-5)."""
        return cls(
            category=llm_output.category,
            priority=llm_output.priority,
            summary=llm_output.summary,
            reply_draft=llm_output.reply_draft,
            confidence=llm_output.confidence,
            needs_review=llm_output.confidence < 0.5,
            prompt_version=prompt_version,
            warning=warning,
        )

import asyncio
import csv
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.cli import _process_batch_async, compute_evaluation_metrics
from app.core.models import (
    MAX_CORE_MESSAGE_LENGTH,
    LLMResponseSchema,
    TicketCategory,
    TicketPriority,
)
from app.core.prompts import get_prompt_version
from app.core.triage import TriageProcessingError, triage


class FakeLLMClient:
    """Deterministic in-memory LLM stub returning queued responses."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if not self._responses:
            raise AssertionError("FakeLLMClient ran out of queued responses.")
        return self._responses.pop(0)


def _valid_payload(
    category: str = "billing",
    priority: str = "high",
    confidence: float = 0.88,
) -> str:
    return json.dumps(
        {
            "category": category,
            "priority": priority,
            "summary": "Customer was charged twice for the November subscription.",
            "reply_draft": (
                "Thank you for reaching out about the duplicate charge. "
                "We are reviewing your billing records and will update you shortly."
            ),
            "confidence": confidence,
        }
    )


def test_valid_triage_result_parsing() -> None:
    client = FakeLLMClient([_valid_payload(confidence=0.91)])
    result = asyncio.run(triage("Charged twice on my invoice.", client=client))

    assert result.category == TicketCategory.BILLING
    assert result.priority == TicketPriority.HIGH
    assert result.confidence == 0.91
    assert result.needs_review is False
    assert result.warning is None
    assert len(client.calls) == 1


def test_low_confidence_sets_needs_review_true() -> None:
    client = FakeLLMClient([_valid_payload(confidence=0.49)])
    result = asyncio.run(triage("Ambiguous message.", client=client))

    assert result.confidence == 0.49
    assert result.needs_review is True


def test_boundary_confidence_half_sets_needs_review_false() -> None:
    client = FakeLLMClient([_valid_payload(confidence=0.50)])
    result = asyncio.run(triage("Borderline confidence message.", client=client))

    assert result.confidence == 0.50
    assert result.needs_review is False


def test_invalid_category_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        LLMResponseSchema(
            category="unknown_department",  # type: ignore[arg-type]
            priority="low",
            summary="Short valid summary.",
            reply_draft="First sentence here. Second sentence here.",
            confidence=0.8,
        )


def test_invalid_priority_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        LLMResponseSchema(
            category="technical",
            priority="critical",  # type: ignore[arg-type]
            summary="Short valid summary.",
            reply_draft="First sentence here. Second sentence here.",
            confidence=0.8,
        )


def test_summary_word_and_sentence_constraints() -> None:
    too_many_words = " ".join(["word"] * 21) + "."
    with pytest.raises(ValidationError):
        LLMResponseSchema(
            category="other",
            priority="low",
            summary=too_many_words,
            reply_draft="First sentence here. Second sentence here.",
            confidence=0.8,
        )

    with pytest.raises(ValidationError):
        LLMResponseSchema(
            category="other",
            priority="low",
            summary="First sentence. Second sentence.",
            reply_draft="First sentence here. Second sentence here.",
            confidence=0.8,
        )


def test_reply_draft_sentence_count_constraints() -> None:
    with pytest.raises(ValidationError):
        LLMResponseSchema(
            category="other",
            priority="low",
            summary="Valid one sentence summary.",
            reply_draft="Only one sentence here.",
            confidence=0.8,
        )

    with pytest.raises(ValidationError):
        LLMResponseSchema(
            category="other",
            priority="low",
            summary="Valid one sentence summary.",
            reply_draft="One. Two. Three. Four. Five.",
            confidence=0.8,
        )


def test_confidence_bounds_enforced() -> None:
    with pytest.raises(ValidationError):
        LLMResponseSchema(
            category="other",
            priority="low",
            summary="Valid summary.",
            reply_draft="First sentence here. Second sentence here.",
            confidence=1.25,
        )


def test_repair_retry_recovers_from_invalid_json() -> None:
    client = FakeLLMClient(["{broken_json:", _valid_payload(category="technical")])
    result = asyncio.run(triage("API returns 500 error.", client=client))

    assert len(client.calls) == 2
    assert "failed JSON or schema validation" in client.calls[1][1]
    assert result.category == TicketCategory.TECHNICAL


def test_repair_retry_recovers_from_schema_violation() -> None:
    bad_schema_json = json.dumps(
        {
            "category": "not_allowed",
            "priority": "high",
            "summary": "Valid summary.",
            "reply_draft": "First sentence. Second sentence.",
            "confidence": 0.9,
        }
    )
    client = FakeLLMClient([bad_schema_json, _valid_payload(category="account")])
    result = asyncio.run(triage("Cannot log into account.", client=client))

    assert len(client.calls) == 2
    assert result.category == TicketCategory.ACCOUNT


def test_raises_triage_processing_error_when_repair_also_fails() -> None:
    client = FakeLLMClient(["not json 1", "still not json 2"])

    with pytest.raises(TriageProcessingError):
        asyncio.run(triage("Help me with my account.", client=client))

    assert len(client.calls) == 2


def test_long_message_truncated_at_4000_chars_with_warning() -> None:
    client = FakeLLMClient([_valid_payload()])
    oversized_message = "B" * 4500

    result = asyncio.run(triage(oversized_message, client=client))

    assert result.warning is not None
    assert "4000" in result.warning
    sent_prompt = client.calls[0][1]
    assert "B" * MAX_CORE_MESSAGE_LENGTH in sent_prompt
    assert "B" * (MAX_CORE_MESSAGE_LENGTH + 1) not in sent_prompt


def test_prompt_version_loaded_from_system_md() -> None:
    version = get_prompt_version()
    assert version == "v2"


def test_cli_batch_and_evaluate_offline(tmp_path: Path) -> None:
    tickets_dir = tmp_path / "tickets"
    tickets_dir.mkdir()
    (tickets_dir / "t1.txt").write_text("Double billed on invoice.", encoding="utf-8")
    (tickets_dir / "t2.txt").write_text("   ", encoding="utf-8")  # Should fail & skip
    (tickets_dir / "t3.txt").write_text("Need dark mode feature.", encoding="utf-8")

    labels_csv = tmp_path / "labels.csv"
    with labels_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "category", "priority"])
        writer.writerow(["t1.txt", "billing", "high"])
        writer.writerow(["t3.txt", "feature_request", "low"])

    results_csv = tmp_path / "results.csv"
    fake_client = FakeLLMClient(
        [
            _valid_payload(category="billing", priority="high"),
            _valid_payload(category="feature_request", priority="low"),
        ]
    )

    succeeded, failed = asyncio.run(
        _process_batch_async(tickets_dir, results_csv, client=fake_client)
    )
    assert succeeded == 2
    assert failed == 1

    metrics = compute_evaluation_metrics(results_csv, labels_csv)
    assert metrics["total"] == 2
    assert metrics["category_accuracy"] == 100.0
    assert metrics["priority_accuracy"] == 100.0

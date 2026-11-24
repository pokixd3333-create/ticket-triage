import json
import logging

from pydantic import ValidationError

from app.core.llm import LLMClient, OpenAILLMClient
from app.core.models import (
    MAX_CORE_MESSAGE_LENGTH,
    LLMResponseSchema,
    TriageResult,
)
from app.core.prompts import (
    get_prompt_version,
    get_system_prompt,
    render_classify_prompt,
    render_repair_prompt,
)

logger = logging.getLogger(__name__)


class TriageProcessingError(Exception):
    """Raised when LLM output fails schema validation even after repair."""


def _parse_and_validate(raw_output: str) -> LLMResponseSchema:
    """Parse raw JSON string and enforce LLMResponseSchema constraints."""
    parsed = json.loads(raw_output)
    return LLMResponseSchema.model_validate(parsed)


async def triage(
    message: str,
    client: LLMClient | None = None,
) -> TriageResult:
    """Classify and structure a raw support message into a TriageResult."""
    llm = client or OpenAILLMClient()
    warning: str | None = None

    processed_message = message
    if len(message) > MAX_CORE_MESSAGE_LENGTH:
        processed_message = message[:MAX_CORE_MESSAGE_LENGTH]
        warning = (
            f"Message exceeded {MAX_CORE_MESSAGE_LENGTH} characters and was truncated."
        )

    system_prompt = get_system_prompt()
    prompt_version = get_prompt_version()
    classify_prompt = render_classify_prompt(processed_message)

    raw_output = await llm.generate(system_prompt, classify_prompt)

    try:
        validated = _parse_and_validate(raw_output)
        return TriageResult.from_llm_output(
            llm_output=validated,
            prompt_version=prompt_version,
            warning=warning,
        )
    except (json.JSONDecodeError, ValidationError) as first_err:
        logger.warning(
            "Initial LLM output failed validation; triggering repair retry. Error: %s",
            first_err,
        )
        repair_prompt = render_repair_prompt(
            raw_output=raw_output,
            validation_error=str(first_err),
        )
        repaired_output = await llm.generate(system_prompt, repair_prompt)

        try:
            validated = _parse_and_validate(repaired_output)
            return TriageResult.from_llm_output(
                llm_output=validated,
                prompt_version=prompt_version,
                warning=warning,
            )
        except (json.JSONDecodeError, ValidationError) as second_err:
            logger.error(
                "LLM output failed validation after repair attempt. Error: %s",
                second_err,
            )
            raise TriageProcessingError(
                "Model output failed validation after repair attempt."
            ) from second_err

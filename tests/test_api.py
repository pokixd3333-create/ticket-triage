import json

from fastapi.testclient import TestClient

from app.api.routes import get_llm_client
from app.core.llm import LLMServiceError
from app.core.triage import TriageProcessingError
from app.main import app


class StaticSuccessLLM:
    """Stub LLM client returning a fixed valid triage payload."""

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        return json.dumps(
            {
                "category": "billing",
                "priority": "high",
                "summary": "Customer was charged twice for the November invoice.",
                "reply_draft": (
                    "Hi Maria, thanks for flagging this duplicate charge. "
                    "We are checking your November billing statement now."
                ),
                "confidence": 0.86,
            }
        )


class ErrorServiceLLM:
    """Stub LLM client simulating an upstream provider outage."""

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise LLMServiceError("Simulated API timeout with secret sk-proj-hidden123")


class InvalidOutputLLM:
    """Stub LLM client simulating persistent invalid JSON outputs."""

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        return "invalid-non-json-response"


client = TestClient(app)


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_options_endpoint_returns_allowed_enums() -> None:
    response = client.get("/api/v1/options")
    assert response.status_code == 200
    body = response.json()
    assert body["categories"] == [
        "billing",
        "technical",
        "account",
        "feature_request",
        "other",
    ]
    assert body["priorities"] == ["low", "medium", "high", "urgent"]


def test_swagger_docs_and_openapi_list_all_endpoints() -> None:
    docs_res = client.get("/docs")
    assert docs_res.status_code == 200

    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/v1/triage" in paths
    assert "/api/v1/health" in paths
    assert "/api/v1/options" in paths


def test_triage_endpoint_success_200() -> None:
    app.dependency_overrides[get_llm_client] = lambda: StaticSuccessLLM()
    try:
        response = client.post(
            "/api/v1/triage",
            json={"message": "Hi, I was charged twice for my November invoice."},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "billing"
        assert data["priority"] == "high"
        assert data["needs_review"] is False
        assert data["confidence"] == 0.86
    finally:
        app.dependency_overrides.clear()


def test_triage_endpoint_rejects_empty_message_422() -> None:
    for invalid_msg in ["", "    \n\t  "]:
        response = client.post("/api/v1/triage", json={"message": invalid_msg})
        assert response.status_code == 422


def test_triage_endpoint_rejects_message_over_10000_chars_422() -> None:
    oversized = "x" * 10_001
    response = client.post("/api/v1/triage", json={"message": oversized})
    assert response.status_code == 422


def test_triage_endpoint_returns_502_on_llm_service_error_without_leaks() -> None:
    app.dependency_overrides[get_llm_client] = lambda: ErrorServiceLLM()
    try:
        response = client.post(
            "/api/v1/triage",
            json={"message": "Need help with my subscription."},
        )
        assert response.status_code == 502
        body = response.json()
        assert set(body.keys()) == {"error"}
        assert "sk-proj" not in json.dumps(body)
        assert "Traceback" not in json.dumps(body)
    finally:
        app.dependency_overrides.clear()


def test_triage_endpoint_returns_502_on_triage_processing_error() -> None:
    app.dependency_overrides[get_llm_client] = lambda: InvalidOutputLLM()
    try:
        response = client.post(
            "/api/v1/triage",
            json={"message": "My dashboard crashes on load."},
        )
        assert response.status_code == 502
        body = response.json()
        assert set(body.keys()) == {"error"}
    finally:
        app.dependency_overrides.clear()


def test_cors_allows_local_frontend_origin() -> None:
    allowed = client.options(
        "/api/v1/triage",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"

    blocked = client.options(
        "/api/v1/triage",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in blocked.headers


def test_llm_processing_error_class_exported() -> None:
    assert issubclass(TriageProcessingError, Exception)

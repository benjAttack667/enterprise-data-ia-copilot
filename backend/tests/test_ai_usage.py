"""Pricing and bounded SQLite retention for content-free AI telemetry."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import openai
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.src.ai_usage import (
    AIUsageRepository,
    not_attempted_usage,
    unavailable_usage,
    usage_from_response,
)
from backend.src.config import Settings


def test_usage_from_mapping_prices_only_uncached_input() -> None:
    response = {
        "usage": {
            "input_tokens": 1_000,
            "input_tokens_details": {"cached_tokens": 800},
            "output_tokens": 100,
            "total_tokens": 1_100,
        }
    }

    usage = usage_from_response(response, "gpt-4.1-mini")

    # (200 * $0.40 + 800 * $0.10 + 100 * $1.60) / 1M
    assert usage["estimated_cost_usd"] == 0.00032
    assert usage["cached_input_tokens"] == 800


def test_missing_response_usage_is_explicitly_unavailable() -> None:
    usage = usage_from_response(object(), "gpt-4.1-mini")

    assert usage["status"] == "unavailable"
    assert usage["openai_request_attempted"] is True
    assert usage["model"] is None
    assert usage["estimated_cost_usd"] is None
    assert usage["fallback_reason"] == "usage_unavailable"


def test_repository_aggregates_measured_and_unpriced_attempts(tmp_path: Path) -> None:
    repository = AIUsageRepository(tmp_path / "history.db", max_entries=10)
    measured = usage_from_response(
        {
            "usage": {
                "input_tokens": 100,
                "input_tokens_details": {"cached_tokens": 20},
                "output_tokens": 10,
                "total_tokens": 110,
            }
        },
        "gpt-4.1-mini",
    )
    repository.record(operation="ask", provider="openai", usage=measured)
    repository.record(
        operation="summary",
        provider="local-fallback",
        usage=not_attempted_usage(),
    )
    repository.record(
        operation="ask",
        provider="local-fallback",
        usage=unavailable_usage("provider_error"),
    )

    payload = repository.summary()

    assert payload["totals"] == {
        "requests": 3,
        "openai_attempts": 2,
        "fallback_responses": 2,
        "input_tokens": 100,
        "cached_input_tokens": 20,
        "output_tokens": 10,
        "total_tokens": 110,
        "estimated_cost_usd": 5e-05,
        "unpriced_attempts": 1,
    }
    assert payload["retention"] == {"entries": 3, "max_entries": 10}
    assert payload["recent"][0]["fallback_reason"] == "provider_error"
    assert payload["recent"][0]["estimated_cost_usd"] is None
    assert "prompt" not in payload["recent"][0]
    assert "response" not in payload["recent"][0]


def test_repository_retention_is_bounded(tmp_path: Path) -> None:
    repository = AIUsageRepository(tmp_path / "history.db", max_entries=2)

    for operation in ("first", "second", "third"):
        repository.record(
            operation=operation,
            provider="local-fallback",
            usage=not_attempted_usage(),
        )

    payload = repository.summary()
    assert payload["totals"]["requests"] == 2
    assert [event["operation"] for event in payload["recent"]] == [
        "third",
        "second",
    ]


def test_no_key_api_exposes_quota_and_content_free_usage(
    client: TestClient, settings: Settings
) -> None:
    secret_question = "Question-CONFIDENTIELLE-9f7c2b"

    response = client.post("/api/ask", json={"question": secret_question})

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "local-fallback"
    assert payload["usage"]["status"] == "not_applicable"
    assert payload["usage"]["openai_request_attempted"] is False
    assert payload["usage"]["input_tokens"] is None
    assert payload["usage"]["estimated_cost_usd"] is None
    assert payload["quota"] == {
        "limit": settings.ai_rate_limit_requests,
        "remaining": settings.ai_rate_limit_requests - 1,
        "window_seconds": settings.ai_rate_limit_window_seconds,
        "next_slot_after_seconds": 0,
        "scope": "process",
    }

    telemetry = client.get("/api/ai-usage")
    assert telemetry.status_code == 200
    body = telemetry.json()
    assert body["provider"] == {
        "configured": False,
        "model": "gpt-4.1-mini",
    }
    assert body["totals"]["requests"] == 1
    assert body["totals"]["openai_attempts"] == 0
    assert body["recent"][0]["operation"] == "ask"
    assert body["recent"][0]["provider"] == "local-fallback"
    assert secret_question not in telemetry.text

    persisted_bytes = b"".join(
        path.read_bytes()
        for path in (
            settings.database_path,
            Path(f"{settings.database_path}-wal"),
            Path(f"{settings.database_path}-shm"),
        )
        if path.is_file()
    )
    assert secret_question.encode() not in persisted_bytes


def test_ai_usage_survives_application_restart(settings: Settings) -> None:
    with TestClient(create_app(settings)) as first_client:
        response = first_client.post(
            "/api/ai-summary",
            json={"focus": "qualité"},
        )
        assert response.status_code == 200

    with TestClient(create_app(settings)) as restarted_client:
        telemetry = restarted_client.get("/api/ai-usage")

    assert telemetry.status_code == 200
    payload = telemetry.json()
    assert payload["totals"]["requests"] == 1
    assert payload["recent"][0]["operation"] == "summary"
    # The quota is deliberately process-local and therefore starts fresh.
    assert payload["quota"]["remaining"] == settings.ai_rate_limit_requests


def test_measured_openai_usage_flows_through_api_and_sqlite(
    monkeypatch, settings: Settings
) -> None:
    class FakeResponses:
        def create(self, **kwargs):
            return SimpleNamespace(
                output_text="Synthèse mesurée",
                usage=SimpleNamespace(
                    input_tokens=100,
                    input_tokens_details=SimpleNamespace(cached_tokens=20),
                    output_tokens=10,
                    total_tokens=110,
                ),
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = FakeResponses()

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    configured = replace(settings, openai_api_key="test-key")

    with TestClient(create_app(configured)) as client:
        response = client.post("/api/ai-summary", json={})
        telemetry = client.get("/api/ai-usage")

    assert response.status_code == 200
    assert response.json()["summary"] == "Synthèse mesurée"
    assert response.json()["usage"]["status"] == "measured"
    assert response.json()["usage"]["estimated_cost_usd"] == 5e-05
    assert telemetry.status_code == 200
    assert telemetry.json()["provider"] == {
        "configured": True,
        "model": "gpt-4.1-mini",
    }
    assert telemetry.json()["totals"]["input_tokens"] == 100
    assert telemetry.json()["totals"]["cached_input_tokens"] == 20
    assert telemetry.json()["totals"]["estimated_cost_usd"] == 5e-05


def test_provider_initialization_failure_is_not_counted_as_an_openai_attempt(
    monkeypatch, settings: Settings
) -> None:
    class BrokenOpenAI:
        def __init__(self, **kwargs):
            raise RuntimeError("SDK unavailable before HTTP")

    monkeypatch.setattr(openai, "OpenAI", BrokenOpenAI)
    configured = replace(settings, openai_api_key="test-key")

    with TestClient(create_app(configured)) as client:
        response = client.post("/api/ai-summary", json={})
        telemetry = client.get("/api/ai-usage")

    assert response.status_code == 200
    assert response.json()["provider"] == "local-fallback"
    assert response.json()["usage"]["openai_request_attempted"] is False
    assert (
        response.json()["usage"]["fallback_reason"]
        == "provider_initialization_error"
    )
    assert telemetry.status_code == 200
    assert telemetry.json()["totals"]["requests"] == 1
    assert telemetry.json()["totals"]["openai_attempts"] == 0
    assert telemetry.json()["totals"]["unpriced_attempts"] == 0


def test_usage_retention_does_not_leak_into_unbounded_business_history(
    settings: Settings,
) -> None:
    bounded = replace(settings, max_ai_usage_entries=1)

    with TestClient(create_app(bounded)) as client:
        assert client.post("/api/ai-summary", json={}).status_code == 200
        assert client.post(
            "/api/ask", json={"question": "Question privée éphémère"}
        ).status_code == 200
        telemetry = client.get("/api/ai-usage").json()
        history = client.get("/api/history").json()["items"]

    ai_history = [
        item
        for item in history
        if item["action"]
        in {"ai_summary_generated", "assistant_question_answered"}
    ]
    assert telemetry["retention"]["entries"] == 1
    assert len(ai_history) == 2
    assert all(set(item["details"]) == {"mode", "provider"} for item in ai_history)
    assert "Question privée éphémère" not in str(history)
    assert "usage" not in str([item["details"] for item in ai_history])


def test_ai_usage_endpoint_requires_service_authentication_in_production(
    settings: Settings,
) -> None:
    protected = replace(
        settings,
        environment="production",
        backend_service_token="s" * 32,
    )
    with TestClient(create_app(protected)) as protected_client:
        unauthorized = protected_client.get("/api/ai-usage")
        authorized = protected_client.get(
            "/api/ai-usage",
            headers={"authorization": f"Bearer {protected.backend_service_token}"},
        )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200

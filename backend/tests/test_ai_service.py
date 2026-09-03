"""Privacy, output-bound and usage guarantees of the OpenAI integration."""

from __future__ import annotations

from types import SimpleNamespace

import openai
import pytest

from backend.src.ai_service import AIService


def _response(
    text: str | None = "Synthèse vérifiée",
    *,
    input_tokens: int = 1_000,
    cached_tokens: int = 400,
    output_tokens: int = 250,
):
    return SimpleNamespace(
        output_text=text,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            input_tokens_details=SimpleNamespace(cached_tokens=cached_tokens),
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        ),
    )


def test_openai_responses_disables_storage_bounds_output_and_measures_usage(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return _response()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.responses = FakeResponses()

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    service = AIService(
        api_key="test-key",
        model="gpt-4.1-mini",
        max_output_tokens=321,
    )
    result = service._openai_result("Résume", {"rows": 12})

    assert result.text == "Synthèse vérifiée"
    assert captured["client"] == {
        "api_key": "test-key",
        "timeout": 20.0,
        "max_retries": 1,
    }
    request = captured["request"]
    assert request["model"] == "gpt-4.1-mini"
    assert request["store"] is False
    assert request["max_output_tokens"] == 321
    assert result.usage == {
        "status": "measured",
        "provider": "openai",
        "openai_request_attempted": True,
        "model": "gpt-4.1-mini",
        "input_tokens": 1_000,
        "cached_input_tokens": 400,
        "output_tokens": 250,
        "total_tokens": 1_250,
        "estimated_cost_usd": 0.00068,
        "pricing_status": "estimated",
        "pricing_source": (
            "https://developers.openai.com/api/docs/models/gpt-4.1-mini"
        ),
        "fallback_reason": None,
    }


def test_unknown_model_keeps_tokens_but_never_invents_a_price(monkeypatch) -> None:
    class FakeResponses:
        def create(self, **kwargs):
            return _response(input_tokens=12, cached_tokens=3, output_tokens=4)

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = FakeResponses()

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    result = AIService("test-key", "future-model")._openai_result("Analyse", {})

    assert result.text == "Synthèse vérifiée"
    assert result.usage["status"] == "measured"
    assert result.usage["model"] == "future-model"
    assert result.usage["total_tokens"] == 16
    assert result.usage["estimated_cost_usd"] is None
    assert result.usage["pricing_status"] == "unavailable"
    assert result.usage["pricing_source"] is None


def test_missing_key_fallback_does_not_claim_tokens_or_cost() -> None:
    result = AIService(None, "gpt-4.1-mini")._openai_result("Analyse", {})

    assert result.text is None
    assert result.usage["status"] == "not_applicable"
    assert result.usage["provider"] is None
    assert result.usage["openai_request_attempted"] is False
    assert result.usage["model"] is None
    assert result.usage["input_tokens"] is None
    assert result.usage["estimated_cost_usd"] is None
    assert result.usage["fallback_reason"] == "missing_api_key"


def test_provider_initialization_error_does_not_claim_an_http_attempt(
    monkeypatch,
) -> None:
    class FakeOpenAI:
        def __init__(self, **kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    result = AIService("test-key", "gpt-4.1-mini")._openai_result("Analyse", {})

    assert result.text is None
    assert result.usage["status"] == "unavailable"
    assert result.usage["provider"] == "openai"
    assert result.usage["openai_request_attempted"] is False
    assert result.usage["model"] is None
    assert result.usage["total_tokens"] is None
    assert result.usage["estimated_cost_usd"] is None
    assert result.usage["fallback_reason"] == "provider_initialization_error"


def test_provider_request_error_marks_attempt_without_fake_usage(monkeypatch) -> None:
    class FakeResponses:
        def create(self, **kwargs):
            raise RuntimeError("provider unavailable")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = FakeResponses()

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    result = AIService("test-key", "gpt-4.1-mini")._openai_result("Analyse", {})

    assert result.text is None
    assert result.usage["status"] == "unavailable"
    assert result.usage["provider"] == "openai"
    assert result.usage["openai_request_attempted"] is True
    assert result.usage["model"] is None
    assert result.usage["total_tokens"] is None
    assert result.usage["estimated_cost_usd"] is None
    assert result.usage["fallback_reason"] == "provider_error"


def test_empty_provider_output_retains_measured_cost_and_explains_fallback(
    monkeypatch,
) -> None:
    class FakeResponses:
        def create(self, **kwargs):
            return _response(text="  ", input_tokens=10, cached_tokens=0, output_tokens=2)

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.responses = FakeResponses()

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    result = AIService("test-key", "gpt-4.1-mini")._openai_result("Analyse", {})

    assert result.text is None
    assert result.usage["status"] == "measured"
    assert result.usage["total_tokens"] == 12
    assert result.usage["estimated_cost_usd"] == 0.0000072
    assert result.usage["fallback_reason"] == "empty_response"


@pytest.mark.parametrize("invalid", [True, 0, -1, 4_097])
def test_max_output_tokens_must_remain_in_safe_configured_bounds(invalid) -> None:
    with pytest.raises(ValueError, match="1 et 4096"):
        AIService(None, "gpt-4.1-mini", max_output_tokens=invalid)

"""Garanties de confidentialité de l'intégration OpenAI."""

from __future__ import annotations

import openai

from backend.src.ai_service import AIService


def test_openai_responses_disables_storage_and_sets_timeout(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return type("Response", (), {"output_text": "Synthèse vérifiée"})()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.responses = FakeResponses()

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    service = AIService(api_key="test-key", model="test-model")
    result = service._openai_text("Résume", {"rows": 12})

    assert result == "Synthèse vérifiée"
    assert captured["client"] == {
        "api_key": "test-key",
        "timeout": 20.0,
        "max_retries": 1,
    }
    request = captured["request"]
    assert request["model"] == "test-model"
    assert request["store"] is False

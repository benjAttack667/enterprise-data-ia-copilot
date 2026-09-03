"""The two AI routes share one body-before-service process quota."""

from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.src.config import Settings
from backend.src.rate_limit import SlidingWindowRateLimiter
from backend.src.request_limits import BusinessRequestGuardMiddleware


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        samples_dir=tmp_path / "samples",
        uploads_dir=tmp_path / "uploads",
        reports_dir=tmp_path / "reports",
        database_path=tmp_path / "history.db",
        ai_rate_limit_requests=1,
        ai_rate_limit_window_seconds=60,
    )


def test_ai_quota_is_shared_and_rejects_before_json_parsing(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = FastAPI()
    calls: list[str] = []

    @app.post("/api/ask")
    async def ask() -> dict[str, bool]:
        calls.append("ask")
        return {"ok": True}

    @app.post("/api/ai-summary")
    async def summary() -> dict[str, bool]:
        calls.append("summary")
        return {"ok": True}

    app.add_middleware(
        BusinessRequestGuardMiddleware,
        settings=settings,
        rate_limiter=SlidingWindowRateLimiter(10, 60),
        ai_rate_limiter=SlidingWindowRateLimiter(1, 60),
        workload_gate=threading.BoundedSemaphore(value=1),
    )

    with TestClient(app) as client:
        first = client.post("/api/ask", json={"question": "Qualité ?"})
        # Invalid JSON would normally be parsed by FastAPI. The exhausted
        # quota must stop this second AI route before that work starts.
        second = client.post(
            "/api/ai-summary",
            content="{",
            headers={"content-type": "application/json"},
        )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json() == {
        "detail": {
            "code": "ai_quota_exceeded",
            "message": "Quota global de requêtes IA temporairement atteint.",
        }
    }
    assert int(second.headers["retry-after"]) >= 1
    assert calls == ["ask"]


def test_quota_status_is_non_consuming() -> None:
    limiter = SlidingWindowRateLimiter(1, 60)

    assert limiter.status() == {
        "limit": 1,
        "remaining": 1,
        "window_seconds": 60,
        "next_slot_after_seconds": 0,
    }
    assert limiter.status()["remaining"] == 1
    assert limiter.consume().allowed is True
    exhausted = limiter.status()
    assert exhausted["remaining"] == 0
    assert exhausted["next_slot_after_seconds"] >= 1


@pytest.mark.parametrize(
    ("field", "value", "name"),
    [
        ("ai_rate_limit_requests", 1_001, "AI_RATE_LIMIT_REQUESTS"),
        ("ai_rate_limit_window_seconds", 86_401, "AI_RATE_LIMIT_WINDOW_SECONDS"),
        ("openai_max_output_tokens", 4_097, "OPENAI_MAX_OUTPUT_TOKENS"),
        ("max_ai_usage_entries", 10_001, "MAX_AI_USAGE_ENTRIES"),
        ("analysis_cache_max_entries", 129, "ANALYSIS_CACHE_MAX_ENTRIES"),
        ("analysis_cache_max_bytes", 32 * 1024 * 1024 + 1, "ANALYSIS_CACHE_MAX_BYTES"),
    ],
)
def test_ai_resource_settings_have_hard_upper_bounds(
    tmp_path: Path, field: str, value: int, name: str
) -> None:
    with pytest.raises(ValueError, match=name):
        replace(_settings(tmp_path), **{field: value})

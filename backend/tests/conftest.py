"""Fixtures isolées pour les tests d'intégration FastAPI."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.src.config import BACKEND_DIR, Settings


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    samples = tmp_path / "data" / "samples"
    samples.mkdir(parents=True)
    shutil.copy2(BACKEND_DIR / "data" / "samples" / "marketing_leads.csv", samples)
    return Settings(
        samples_dir=samples,
        uploads_dir=tmp_path / "data" / "uploads",
        reports_dir=tmp_path / "reports",
        database_path=tmp_path / "data" / "history.db",
        max_upload_bytes=16_384,
        openai_api_key=None,
        openai_model="gpt-4.1-mini",
        allowed_origins=("http://localhost:3000",),
    )


@pytest.fixture()
def client(settings: Settings) -> TestClient:
    with TestClient(create_app(settings)) as test_client:
        yield test_client

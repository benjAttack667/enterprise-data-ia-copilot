"""Security contract for the public backend boundary."""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.src.config import Settings


SERVICE_TOKEN = "backend-test-service-token-3f9c83c1"
AUTHORIZATION = {"Authorization": f"Bearer {SERVICE_TOKEN}"}


def _production_settings(settings: Settings, **overrides: object) -> Settings:
    return replace(
        settings,
        environment="production",
        backend_service_token=SERVICE_TOKEN,
        **overrides,
    )


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/upload"),
        ("GET", "/api/overview"),
        ("GET", "/api/data-quality"),
        ("GET", "/api/dashboard"),
        ("POST", "/api/ai-summary"),
        ("POST", "/api/ask"),
        ("GET", "/api/anomalies"),
        ("POST", "/api/report"),
        ("GET", "/api/history"),
    ],
)
def test_every_business_route_requires_service_token(
    settings: Settings, method: str, path: str
) -> None:
    with TestClient(create_app(_production_settings(settings))) as client:
        response = client.request(method, path)

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentification du service requise."}
    assert response.headers["www-authenticate"] == "Bearer"


def test_health_stays_public_and_does_not_disclose_dataset(settings: Settings) -> None:
    with TestClient(create_app(_production_settings(settings))) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.0.0"}


@pytest.mark.parametrize(
    "authorization",
    [
        "Bearer wrong-token",
        "Basic YmFja2VuZDpzZWNyZXQ=",
        "Bearer wrong-token-with-a-different-length",
    ],
)
def test_invalid_credentials_are_rejected_without_detail(
    settings: Settings, authorization: str
) -> None:
    with TestClient(create_app(_production_settings(settings))) as client:
        response = client.get(
            "/api/overview", headers={"Authorization": authorization}
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentification du service requise."}


def test_valid_bearer_token_unlocks_business_routes(settings: Settings) -> None:
    with TestClient(create_app(_production_settings(settings))) as client:
        response = client.get("/api/overview", headers=AUTHORIZATION)

    assert response.status_code == 200
    assert response.json()["dataset"]["id"] == "marketing-leads"


def test_production_refuses_to_start_without_service_token(settings: Settings) -> None:
    with pytest.raises(ValueError, match="obligatoire en production"):
        replace(
            settings,
            environment="production",
            backend_service_token=None,
        )


def test_production_refuses_a_short_service_token(settings: Settings) -> None:
    with pytest.raises(ValueError, match="au moins 32 octets"):
        replace(
            settings,
            environment="production",
            backend_service_token="too-short",
        )


def test_blank_service_token_is_always_rejected(settings: Settings) -> None:
    with pytest.raises(ValueError, match="ne peut pas être vide"):
        replace(settings, backend_service_token="   ")


def test_local_mode_is_open_only_when_no_token_is_configured(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings)) as open_client:
        assert open_client.get("/api/overview").status_code == 200

    protected_local = replace(settings, backend_service_token=SERVICE_TOKEN)
    with TestClient(create_app(protected_local)) as protected_client:
        assert protected_client.get("/api/overview").status_code == 401
        assert (
            protected_client.get(
                "/api/overview", headers=AUTHORIZATION
            ).status_code
            == 200
        )


def test_documentation_is_disabled_by_default_in_production(
    settings: Settings,
) -> None:
    production = _production_settings(settings, api_docs_enabled=None)
    assert production.api_docs_enabled is False

    with TestClient(create_app(production)) as client:
        assert client.get("/docs", headers=AUTHORIZATION).status_code == 404
        assert client.get("/redoc", headers=AUTHORIZATION).status_code == 404
        assert client.get("/openapi.json", headers=AUTHORIZATION).status_code == 404


def test_enabled_documentation_and_openapi_are_protected(
    settings: Settings,
) -> None:
    production = _production_settings(settings, api_docs_enabled=True)
    with TestClient(create_app(production)) as client:
        assert client.get("/docs").status_code == 401
        assert client.get("/redoc").status_code == 401
        assert client.get("/openapi.json").status_code == 401

        docs = client.get("/docs", headers=AUTHORIZATION)
        schema_response = client.get("/openapi.json", headers=AUTHORIZATION)

    assert docs.status_code == 200
    assert "Swagger UI" in docs.text
    assert schema_response.status_code == 200
    schema = schema_response.json()
    assert schema["paths"]["/api/overview"]["get"]["security"] == [
        {"BackendServiceToken": []}
    ]
    assert "security" not in schema["paths"]["/api/health"]["get"]


def test_environment_defaults_keep_docs_off_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COPILOT_ENVIRONMENT", "production")
    monkeypatch.setenv("BACKEND_SERVICE_TOKEN", SERVICE_TOKEN)
    monkeypatch.delenv("API_DOCS_ENABLED", raising=False)

    settings = Settings.from_env()

    assert settings.environment == "production"
    assert settings.service_auth_enabled is True
    assert settings.api_docs_enabled is False


def test_railway_environment_is_fail_closed_without_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COPILOT_ENVIRONMENT", raising=False)
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "railway-project-test")
    monkeypatch.delenv("BACKEND_SERVICE_TOKEN", raising=False)

    with pytest.raises(ValueError, match="obligatoire en production"):
        Settings.from_env()


def test_invalid_environment_and_docs_flag_fail_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COPILOT_ENVIRONMENT", "staging")
    with pytest.raises(ValueError, match="local, test ou production"):
        Settings.from_env()

    monkeypatch.setenv("COPILOT_ENVIRONMENT", "local")
    monkeypatch.setenv("API_DOCS_ENABLED", "perhaps")
    with pytest.raises(ValueError, match="API_DOCS_ENABLED"):
        Settings.from_env()

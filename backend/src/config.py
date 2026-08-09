"""Configuration centralisée du backend.

Les chemins sont absolus afin que l'API puisse être lancée depuis n'importe quel
répertoire de travail (par exemple avec ``uvicorn backend.main:app``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
MIN_PRODUCTION_TOKEN_BYTES = 32
load_dotenv(BACKEND_DIR / ".env")


def _default_environment() -> Literal["local", "production"]:
    """Treat Railway as production even if the explicit flag was forgotten."""

    return "production" if os.getenv("RAILWAY_PROJECT_ID") else "local"


def _path_from_env(name: str, default: Path) -> Path:
    """Resolve an optional runtime path without coupling tests to production data."""

    value = os.getenv(name)
    return Path(value).expanduser().resolve() if value else default.resolve()


def _boolean_from_env(name: str, default: bool) -> bool:
    """Parse a strict boolean so a typo cannot silently weaken production."""

    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        f"{name} doit valoir true/false, yes/no, on/off ou 1/0."
    )


@dataclass(frozen=True)
class Settings:
    """Paramètres injectables, ce qui garde l'application facile à tester."""

    samples_dir: Path
    uploads_dir: Path
    reports_dir: Path
    database_path: Path
    max_upload_bytes: int = 50 * 1024 * 1024
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    environment: Literal["local", "test", "production"] = "local"
    backend_service_token: str | None = None
    api_docs_enabled: bool | None = None
    allowed_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )

    def __post_init__(self) -> None:
        """Reject unsafe or ambiguous security settings at startup."""

        if self.api_docs_enabled is None:
            object.__setattr__(
                self, "api_docs_enabled", self.environment != "production"
            )
        if self.environment not in {"local", "test", "production"}:
            raise ValueError(
                "COPILOT_ENVIRONMENT doit valoir local, test ou production."
            )
        if (
            self.backend_service_token is not None
            and not self.backend_service_token.strip()
        ):
            raise ValueError("BACKEND_SERVICE_TOKEN ne peut pas être vide.")
        if self.environment == "production" and self.backend_service_token is None:
            raise ValueError(
                "BACKEND_SERVICE_TOKEN est obligatoire en production. "
                "Générez un secret robuste avant de démarrer l'API."
            )
        token_byte_length = len((self.backend_service_token or "").encode("utf-8"))
        if (
            self.environment == "production"
            and self.backend_service_token is not None
            and token_byte_length < MIN_PRODUCTION_TOKEN_BYTES
        ):
            raise ValueError(
                "BACKEND_SERVICE_TOKEN doit contenir au moins 32 octets "
                "en production."
            )

    @property
    def service_auth_enabled(self) -> bool:
        """Whether business routes must validate a bearer service token."""

        return self.backend_service_token is not None

    @classmethod
    def from_env(cls) -> "Settings":
        """Construit la configuration depuis l'environnement et ``backend/.env``."""

        environment = os.getenv(
            "COPILOT_ENVIRONMENT", _default_environment()
        ).strip().lower()
        if environment not in {"local", "test", "production"}:
            raise ValueError(
                "COPILOT_ENVIRONMENT doit valoir local, test ou production."
            )
        origins = tuple(
            origin.strip()
            for origin in os.getenv(
                "FRONTEND_ORIGINS",
                "http://localhost:3000,http://127.0.0.1:3000",
            ).split(",")
            if origin.strip()
        )
        return cls(
            samples_dir=_path_from_env(
                "COPILOT_SAMPLES_DIR", BACKEND_DIR / "data" / "samples"
            ),
            uploads_dir=_path_from_env(
                "COPILOT_UPLOADS_DIR", BACKEND_DIR / "data" / "uploads"
            ),
            reports_dir=_path_from_env(
                "COPILOT_REPORTS_DIR", BACKEND_DIR / "reports"
            ),
            database_path=_path_from_env(
                "COPILOT_DATABASE_PATH", BACKEND_DIR / "data" / "history.db"
            ),
            max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))),
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            environment=environment,
            backend_service_token=os.getenv("BACKEND_SERVICE_TOKEN") or None,
            api_docs_enabled=_boolean_from_env(
                "API_DOCS_ENABLED", default=environment != "production"
            ),
            allowed_origins=origins,
        )

    def ensure_directories(self) -> None:
        """Crée uniquement les répertoires d'écriture nécessaires à l'exécution."""

        self.samples_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

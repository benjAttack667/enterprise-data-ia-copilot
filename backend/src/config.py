"""Configuration centralisée du backend.

Les chemins sont absolus afin que l'API puisse être lancée depuis n'importe quel
répertoire de travail (par exemple avec ``uvicorn backend.main:app``).
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
MIN_PRODUCTION_TOKEN_BYTES = 32
RESOURCE_INTEGER_UPPER_BOUNDS = {
    "MAX_UPLOAD_BYTES": 10 * 1024 * 1024,
    "MAX_DATASET_ROWS": 100_000,
    "MAX_DATASET_COLUMNS": 200,
    "MAX_DATASET_CELLS": 2_000_000,
    "MAX_XLSX_UNCOMPRESSED_BYTES": 50 * 1024 * 1024,
    "MAX_XLSX_ENTRIES": 1_000,
    "UPLOAD_RATE_LIMIT_REQUESTS": 100,
    "UPLOAD_RATE_LIMIT_WINDOW_SECONDS": 86_400,
    "MAX_REPORT_FILES": 200,
    "MAX_HISTORY_ENTRIES": 10_000,
}
MAX_XLSX_COMPRESSION_RATIO_LIMIT = 100.0
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
    max_upload_bytes: int = 10 * 1024 * 1024
    max_dataset_rows: int = 100_000
    max_dataset_columns: int = 200
    max_dataset_cells: int = 2_000_000
    max_xlsx_uncompressed_bytes: int = 50 * 1024 * 1024
    max_xlsx_compression_ratio: float = 100.0
    max_xlsx_entries: int = 1_000
    upload_rate_limit_requests: int = 10
    upload_rate_limit_window_seconds: int = 600
    max_report_files: int = 20
    max_history_entries: int = 500
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
        positive_integer_settings = {
            "MAX_UPLOAD_BYTES": self.max_upload_bytes,
            "MAX_DATASET_ROWS": self.max_dataset_rows,
            "MAX_DATASET_COLUMNS": self.max_dataset_columns,
            "MAX_DATASET_CELLS": self.max_dataset_cells,
            "MAX_XLSX_UNCOMPRESSED_BYTES": self.max_xlsx_uncompressed_bytes,
            "MAX_XLSX_ENTRIES": self.max_xlsx_entries,
            "UPLOAD_RATE_LIMIT_REQUESTS": self.upload_rate_limit_requests,
            "UPLOAD_RATE_LIMIT_WINDOW_SECONDS": self.upload_rate_limit_window_seconds,
            "MAX_REPORT_FILES": self.max_report_files,
            "MAX_HISTORY_ENTRIES": self.max_history_entries,
        }
        invalid_setting = next(
            (
                name
                for name, value in positive_integer_settings.items()
                if not isinstance(value, int) or isinstance(value, bool) or value <= 0
            ),
            None,
        )
        if invalid_setting is not None:
            raise ValueError(f"{invalid_setting} doit être un entier strictement positif.")
        excessive_setting = next(
            (
                name
                for name, value in positive_integer_settings.items()
                if value > RESOURCE_INTEGER_UPPER_BOUNDS[name]
            ),
            None,
        )
        if excessive_setting is not None:
            raise ValueError(
                f"{excessive_setting} ne peut pas dépasser "
                f"{RESOURCE_INTEGER_UPPER_BOUNDS[excessive_setting]}."
            )
        if (
            isinstance(self.max_xlsx_compression_ratio, bool)
            or not isinstance(self.max_xlsx_compression_ratio, (int, float))
            or not math.isfinite(self.max_xlsx_compression_ratio)
            or self.max_xlsx_compression_ratio < 1
        ):
            raise ValueError("MAX_XLSX_COMPRESSION_RATIO doit être supérieur ou égal à 1.")
        if self.max_xlsx_compression_ratio > MAX_XLSX_COMPRESSION_RATIO_LIMIT:
            raise ValueError(
                "MAX_XLSX_COMPRESSION_RATIO ne peut pas dépasser "
                f"{MAX_XLSX_COMPRESSION_RATIO_LIMIT:g}."
            )
        if self.max_dataset_cells < self.max_dataset_columns:
            raise ValueError(
                "MAX_DATASET_CELLS doit permettre au moins une ligne complète."
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
            max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
            max_dataset_rows=int(os.getenv("MAX_DATASET_ROWS", "100000")),
            max_dataset_columns=int(os.getenv("MAX_DATASET_COLUMNS", "200")),
            max_dataset_cells=int(os.getenv("MAX_DATASET_CELLS", "2000000")),
            max_xlsx_uncompressed_bytes=int(
                os.getenv("MAX_XLSX_UNCOMPRESSED_BYTES", str(50 * 1024 * 1024))
            ),
            max_xlsx_compression_ratio=float(
                os.getenv("MAX_XLSX_COMPRESSION_RATIO", "100")
            ),
            max_xlsx_entries=int(os.getenv("MAX_XLSX_ENTRIES", "1000")),
            upload_rate_limit_requests=int(
                os.getenv("UPLOAD_RATE_LIMIT_REQUESTS", "10")
            ),
            upload_rate_limit_window_seconds=int(
                os.getenv("UPLOAD_RATE_LIMIT_WINDOW_SECONDS", "600")
            ),
            max_report_files=int(os.getenv("MAX_REPORT_FILES", "20")),
            max_history_entries=int(os.getenv("MAX_HISTORY_ENTRIES", "500")),
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

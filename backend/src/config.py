"""Configuration centralisée du backend.

Les chemins sont absolus afin que l'API puisse être lancée depuis n'importe quel
répertoire de travail (par exemple avec ``uvicorn backend.main:app``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


def _path_from_env(name: str, default: Path) -> Path:
    """Resolve an optional runtime path without coupling tests to production data."""

    value = os.getenv(name)
    return Path(value).expanduser().resolve() if value else default.resolve()


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
    allowed_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )

    @classmethod
    def from_env(cls) -> "Settings":
        """Construit la configuration depuis l'environnement et ``backend/.env``."""

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
            allowed_origins=origins,
        )

    def ensure_directories(self) -> None:
        """Crée uniquement les répertoires d'écriture nécessaires à l'exécution."""

        self.samples_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

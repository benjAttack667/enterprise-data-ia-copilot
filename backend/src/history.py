"""Historique SQLite des analyses réellement exécutées."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class HistoryRepository:
    """Petit dépôt SQLite sans état partagé entre threads."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    dataset_name TEXT NOT NULL,
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_history_created_at "
                "ON analysis_history(created_at DESC)"
            )

    def record(
        self,
        action: str,
        dataset_id: str,
        dataset_name: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Ajoute un événement abouti à l'historique."""

        created_at = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(details or {}, ensure_ascii=False, default=str)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_history
                    (action, dataset_id, dataset_name, details, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (action, dataset_id, dataset_name, payload, created_at),
            )

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        """Liste les événements du plus récent au plus ancien."""

        safe_limit = max(1, min(int(limit), 200))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, action, dataset_id, dataset_name, details, created_at
                FROM analysis_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "action": row["action"],
                "dataset_id": row["dataset_id"],
                "dataset_name": row["dataset_name"],
                "status": "completed",
                "details": json.loads(row["details"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

"""Télémétrie OpenAI minimale, tarifée et persistée sans contenu utilisateur.

Le dépôt ne conserve jamais les instructions, questions, agrégats ou réponses.
Seules des métriques opérationnelles bornées sont écrites dans SQLite.
"""

from __future__ import annotations

import math
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping


OPENAI_PRICING_SOURCE = "https://developers.openai.com/api/docs/models/gpt-4.1-mini"


@dataclass(frozen=True)
class ModelPricing:
    """Prix publics en USD par million de tokens."""

    input_per_million: Decimal
    cached_input_per_million: Decimal
    output_per_million: Decimal


KNOWN_MODEL_PRICING = {
    "gpt-4.1-mini": ModelPricing(
        input_per_million=Decimal("0.40"),
        cached_input_per_million=Decimal("0.10"),
        output_per_million=Decimal("1.60"),
    )
}


def _member(value: object, name: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _token_count(value: object) -> int | None:
    """Accept SDK integers while rejecting booleans, fractions and negatives."""

    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value >= 0 and value.is_integer() else None
    return None


def _estimated_cost(
    model: str,
    *,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
) -> float | None:
    pricing = KNOWN_MODEL_PRICING.get(model)
    if pricing is None:
        return None
    cached = min(cached_input_tokens, input_tokens)
    uncached = input_tokens - cached
    cost = (
        Decimal(uncached) * pricing.input_per_million
        + Decimal(cached) * pricing.cached_input_per_million
        + Decimal(output_tokens) * pricing.output_per_million
    ) / Decimal(1_000_000)
    # Ten decimals keep sub-cent demo requests visible without implying that
    # this application-side estimate is an invoice.
    return float(cost.quantize(Decimal("0.0000000001")))


def not_attempted_usage() -> dict[str, Any]:
    """Telemetry for the deterministic fallback when no API call was made."""

    return {
        "status": "not_applicable",
        "provider": None,
        "openai_request_attempted": False,
        "model": None,
        "input_tokens": None,
        "cached_input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "estimated_cost_usd": None,
        "pricing_status": "not_applicable",
        "pricing_source": None,
        "fallback_reason": "missing_api_key",
    }


def unavailable_usage(
    fallback_reason: str,
    *,
    request_attempted: bool = True,
) -> dict[str, Any]:
    """Telemetry when provider usage is unavailable, without inventing a call."""

    return {
        "status": "unavailable",
        "provider": "openai",
        "openai_request_attempted": request_attempted,
        "model": None,
        "input_tokens": None,
        "cached_input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "estimated_cost_usd": None,
        "pricing_status": "unavailable",
        "pricing_source": None,
        "fallback_reason": fallback_reason,
    }


def usage_from_response(response: object, model: str) -> dict[str, Any]:
    """Read the Responses API usage object without depending on SDK internals."""

    usage = _member(response, "usage")
    input_tokens = _token_count(_member(usage, "input_tokens"))
    output_tokens = _token_count(_member(usage, "output_tokens"))
    details = _member(usage, "input_tokens_details")
    cached_tokens = _token_count(_member(details, "cached_tokens"))
    total_tokens = _token_count(_member(usage, "total_tokens"))
    if input_tokens is None or output_tokens is None:
        return unavailable_usage("usage_unavailable")

    cached_tokens = min(cached_tokens or 0, input_tokens)
    if total_tokens is None:
        total_tokens = input_tokens + output_tokens
    estimated_cost = _estimated_cost(
        model,
        input_tokens=input_tokens,
        cached_input_tokens=cached_tokens,
        output_tokens=output_tokens,
    )
    return {
        "status": "measured",
        "provider": "openai",
        "openai_request_attempted": True,
        "model": model,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": estimated_cost,
        "pricing_status": "estimated" if estimated_cost is not None else "unavailable",
        "pricing_source": OPENAI_PRICING_SOURCE if estimated_cost is not None else None,
        "fallback_reason": None,
    }


class AIUsageRepository:
    """SQLite repository retaining bounded, content-free AI usage events."""

    def __init__(self, database_path: Path, max_entries: int = 1_000) -> None:
        if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries <= 0:
            raise ValueError("max_entries doit être un entier strictement positif.")
        self.database_path = database_path
        self.max_entries = max_entries
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ai_usage (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        operation TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        openai_request_attempted INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        model TEXT,
                        input_tokens INTEGER,
                        cached_input_tokens INTEGER,
                        output_tokens INTEGER,
                        total_tokens INTEGER,
                        estimated_cost_usd REAL,
                        pricing_status TEXT NOT NULL,
                        fallback_reason TEXT,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_ai_usage_created_at "
                    "ON ai_usage(created_at DESC)"
                )
                self._prune(connection)

    def _prune(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            DELETE FROM ai_usage
            WHERE id NOT IN (
                SELECT id FROM ai_usage ORDER BY id DESC LIMIT ?
            )
            """,
            (self.max_entries,),
        )

    @staticmethod
    def _nullable_token(usage: Mapping[str, Any], name: str) -> int | None:
        value = usage.get(name)
        parsed = _token_count(value)
        if value is not None and parsed is None:
            raise ValueError(f"{name} doit être un entier positif ou null.")
        return parsed

    def record(
        self,
        *,
        operation: str,
        provider: str,
        usage: Mapping[str, Any],
    ) -> None:
        """Persist one operation's counters, never its prompt or output."""

        safe_operation = operation.strip()
        safe_provider = provider.strip()
        if not safe_operation or len(safe_operation) > 80:
            raise ValueError("operation doit contenir entre 1 et 80 caractères.")
        if not safe_provider or len(safe_provider) > 80:
            raise ValueError("provider doit contenir entre 1 et 80 caractères.")

        attempted = usage.get("openai_request_attempted")
        if not isinstance(attempted, bool):
            raise ValueError("openai_request_attempted doit être un booléen.")
        model_value = usage.get("model")
        if model_value is not None and (
            not isinstance(model_value, str)
            or not model_value.strip()
            or len(model_value) > 120
        ):
            raise ValueError("model doit être null ou une chaîne non vide.")
        model = model_value.strip() if isinstance(model_value, str) else None
        input_tokens = self._nullable_token(usage, "input_tokens")
        cached_tokens = self._nullable_token(usage, "cached_input_tokens")
        output_tokens = self._nullable_token(usage, "output_tokens")
        total_tokens = self._nullable_token(usage, "total_tokens")
        cost_value = usage.get("estimated_cost_usd")
        if cost_value is None:
            estimated_cost = None
        elif (
            isinstance(cost_value, bool)
            or not isinstance(cost_value, (int, float))
            or not math.isfinite(float(cost_value))
            or float(cost_value) < 0
        ):
            raise ValueError("estimated_cost_usd doit être positif ou null.")
        else:
            estimated_cost = float(cost_value)
        status = usage.get("status")
        if status not in {"measured", "unavailable", "not_applicable"}:
            raise ValueError("status invalide.")
        pricing_status = usage.get("pricing_status")
        if pricing_status not in {"estimated", "unavailable", "not_applicable"}:
            raise ValueError("pricing_status invalide.")
        fallback_value = usage.get("fallback_reason")
        if fallback_value is not None and (
            not isinstance(fallback_value, str)
            or not fallback_value.strip()
            or len(fallback_value) > 80
        ):
            raise ValueError("fallback_reason doit être null ou une chaîne non vide.")
        fallback_reason = (
            fallback_value.strip() if isinstance(fallback_value, str) else None
        )

        created_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO ai_usage (
                        operation, provider, openai_request_attempted, status, model,
                        input_tokens, cached_input_tokens, output_tokens,
                        total_tokens, estimated_cost_usd, pricing_status,
                        fallback_reason, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        safe_operation,
                        safe_provider,
                        int(attempted),
                        status,
                        model,
                        input_tokens,
                        cached_tokens,
                        output_tokens,
                        total_tokens,
                        estimated_cost,
                        pricing_status,
                        fallback_reason,
                        created_at,
                    ),
                )
                self._prune(connection)

    def summary(self, recent_limit: int = 20) -> dict[str, Any]:
        """Return safe aggregate totals and a bounded recent event list."""

        safe_limit = max(1, min(int(recent_limit), 100))
        with self._lock:
            with self._connect() as connection:
                totals = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS requests,
                        COALESCE(SUM(openai_request_attempted), 0) AS openai_attempts,
                        COALESCE(SUM(CASE WHEN provider != 'openai' THEN 1 ELSE 0 END), 0)
                            AS fallback_responses,
                        COALESCE(SUM(input_tokens), 0) AS input_tokens,
                        COALESCE(SUM(cached_input_tokens), 0) AS cached_input_tokens,
                        COALESCE(SUM(output_tokens), 0) AS output_tokens,
                        COALESCE(SUM(total_tokens), 0) AS total_tokens,
                        COALESCE(SUM(estimated_cost_usd), 0.0) AS estimated_cost_usd,
                        COALESCE(SUM(CASE
                            WHEN openai_request_attempted = 1
                                 AND estimated_cost_usd IS NULL THEN 1 ELSE 0 END), 0)
                            AS unpriced_attempts
                    FROM ai_usage
                    """
                ).fetchone()
                rows = connection.execute(
                    """
                    SELECT id, operation, provider, openai_request_attempted,
                           status, model, input_tokens, cached_input_tokens,
                           output_tokens, total_tokens, estimated_cost_usd,
                           pricing_status, fallback_reason, created_at
                    FROM ai_usage
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()

        total_payload = dict(totals)
        total_payload["estimated_cost_usd"] = round(
            float(total_payload["estimated_cost_usd"]), 10
        )
        return {
            "totals": total_payload,
            "recent": [
                {
                    **dict(row),
                    "openai_request_attempted": bool(row["openai_request_attempted"]),
                }
                for row in rows
            ],
            "retention": {
                "entries": int(total_payload["requests"]),
                "max_entries": self.max_entries,
            },
        }

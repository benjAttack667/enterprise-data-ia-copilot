"""Schémas d'entrée de l'API FastAPI."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AISummaryRequest(BaseModel):
    """Contexte facultatif demandé pour orienter la synthèse."""

    model_config = ConfigDict(str_strip_whitespace=True)
    focus: str | None = Field(default=None, max_length=500)


class AskRequest(BaseModel):
    """Question en langage naturel adressée à l'assistant."""

    model_config = ConfigDict(str_strip_whitespace=True)
    question: str = Field(min_length=2, max_length=1_000)


class ReportRequest(BaseModel):
    """Format de rapport réellement pris en charge par le générateur."""

    format: Literal["markdown", "html"] = "markdown"


Aggregation = Literal["sum", "mean", "median", "min", "max", "count"]

"""Conversions sûres entre les objets Pandas/Numpy et JSON."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd


def json_value(value: Any) -> Any:
    """Retourne une valeur JSON native et remplace NaN/infini par ``None``."""

    if value is None or value is pd.NA:
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if pd.isna(value):
        return None
    return value


def finite_number(value: Any, digits: int = 2) -> float:
    """Normalise un agrégat numérique pour éviter les réponses JSON non valides."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return round(number, digits)

"""Conversions sûres entre les objets Pandas/Numpy et JSON."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd


def json_value(value: Any) -> Any:
    """Return recursively JSON-native values with explicit missing semantics."""

    if value is None or value is pd.NA:
        return None
    missing = pd.isna(value)
    if isinstance(missing, (bool, np.bool_)) and bool(missing):
        return None
    if isinstance(value, np.generic):
        return json_value(value.item())
    if isinstance(value, pd.Timedelta):
        return value.isoformat()
    if isinstance(value, timedelta):
        return pd.Timedelta(value).isoformat()
    if isinstance(value, pd.Period):
        return str(value)
    if isinstance(value, pd.Interval):
        return str(value)
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.ndarray):
        return [json_value(item) for item in value.tolist()]
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_value(item) for item in value]
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        converted = float(value)
        return converted if math.isfinite(converted) else str(value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, complex):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def finite_number(value: Any, digits: int = 2) -> float | None:
    """Normalize a finite aggregate and preserve absence as JSON ``null``."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits)

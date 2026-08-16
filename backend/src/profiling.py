"""Central semantic profiling shared by quality, charts and anomaly detection.

The profiler never mutates the supplied dataframe. It deliberately separates
physical Pandas dtypes from business roles so numeric identifiers are not used
as measures and high-confidence numeric text remains analysable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

import numpy as np
import pandas as pd


SemanticType = Literal["identifier", "number", "datetime", "boolean", "categorical"]
NUMERIC_TEXT_CONFIDENCE = 0.90
AUTOMATIC_DATE_CONFIDENCE = 0.90
MISSING_LABEL = "Valeur manquante"

_STRONG_DATE_TOKENS = {
    "date",
    "datetime",
    "timestamp",
    "month",
    "time",
    "year",
}
_CONTEXTUAL_DATE_TOKENS = {"created", "modified", "update", "updated"}
_IDENTIFIER_TOKENS = {"id", "identifier", "uuid", "guid"}
_DAY_MONTH_YEAR = re.compile(
    r"^(?P<first>\d{1,2})/(?P<second>\d{1,2})/(?P<year>\d{4})$"
)
_YEAR_FIRST_DATE = re.compile(
    r"^\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?(?:[T\s].*)?$"
)


@dataclass(frozen=True)
class ColumnProfile:
    """Immutable semantic view of one source column."""

    name: str
    semantic_type: SemanticType
    normalized: pd.Series
    numeric: pd.Series | None
    temporal: pd.Series | None
    parse_rate: float
    invalid_count: int
    ambiguous_count: int
    blank_count: int
    date_hint: bool = False
    date_parse_rate: float = 0.0
    invalid_date_count: int = 0

    @property
    def is_identifier(self) -> bool:
        return self.semantic_type == "identifier"


def _name_tokens(name: str) -> tuple[str, ...]:
    expanded = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return tuple(token for token in re.split(r"[^a-z0-9]+", expanded.lower()) if token)


def is_identifier_name(name: str) -> bool:
    """Recognise explicit identifier names without guessing from cardinality."""

    tokens = _name_tokens(name)
    if not tokens:
        return False
    if any(token in _IDENTIFIER_TOKENS for token in tokens):
        return True
    return len(tokens) > 1 and tokens[-1] in {"number", "code", "key"}


def has_datetime_name_hint(name: str) -> bool:
    """Use whole tokens so ``candidate`` and ``lifetime`` are not dates."""

    tokens = _name_tokens(name)
    if set(tokens) & _STRONG_DATE_TOKENS:
        return True
    for position, token in enumerate(tokens):
        if token not in _CONTEXTUAL_DATE_TOKENS:
            continue
        if position == len(tokens) - 1:
            return True
        neighbours = tokens[max(0, position - 1) : position + 2]
        if set(neighbours) & {"at", "date", "time", "timestamp"}:
            return True
    return False


def normalize_blanks(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Return a deep copy where only nulls and blank strings are missing.

    Business labels such as ``NA``, ``N/A`` and ``NULL`` are intentionally not
    interpreted here; ingestion preserves them as ordinary text.
    """

    normalized = dataframe.copy(deep=True)
    for column in normalized.select_dtypes(include=["object", "string"]).columns:
        series = normalized[column]
        blank_mask = _blank_string_mask(series)
        normalized.loc[blank_mask.fillna(False), column] = pd.NA
    return normalized


def _blank_string_mask(series: pd.Series) -> pd.Series:
    if not (
        pd.api.types.is_object_dtype(series.dtype)
        or pd.api.types.is_string_dtype(series.dtype)
    ):
        return pd.Series(False, index=series.index)
    return series.notna() & series.astype("string").str.strip().eq("")


def _empty_temporal(index: pd.Index) -> pd.Series:
    return pd.Series(pd.NaT, index=index, dtype="datetime64[ns, UTC]")


def _parse_years(series: pd.Series) -> pd.Series:
    parsed = _empty_temporal(series.index)
    numeric = pd.to_numeric(series, errors="coerce")
    valid = (
        numeric.notna()
        & np.isfinite(numeric)
        & numeric.between(1000, 9999)
        & numeric.mod(1).eq(0)
    )
    if valid.any():
        year_text = numeric.loc[valid].astype("int64").astype(str)
        parsed.loc[valid] = pd.to_datetime(
            year_text,
            format="%Y",
            errors="coerce",
            utc=True,
        )
    return parsed


def _parse_temporal_values(
    name: str, series: pd.Series
) -> tuple[pd.Series, int]:
    """Parse deterministic dates to UTC and report ambiguous slash dates."""

    parsed = _empty_temporal(series.index)
    non_missing = series.notna()
    if not non_missing.any():
        return parsed, 0

    if isinstance(series.dtype, pd.PeriodDtype):
        converted = series.dt.to_timestamp()
        return pd.to_datetime(converted, errors="coerce", utc=True), 0
    if pd.api.types.is_datetime64_any_dtype(series.dtype):
        return pd.to_datetime(series, errors="coerce", utc=True), 0

    tokens = set(_name_tokens(name))
    if "year" in tokens and pd.api.types.is_numeric_dtype(series.dtype):
        return _parse_years(series), 0

    # Python date/datetime objects are deterministic even in an object series.
    object_dates = series.map(
        lambda value: isinstance(value, (date, datetime, pd.Timestamp))
        and value is not pd.NaT
    )
    if object_dates.any():
        parsed.loc[object_dates] = pd.to_datetime(
            series.loc[object_dates], errors="coerce", utc=True
        )

    text = series.astype("string").str.strip()
    slash_parts = text.str.extract(_DAY_MONTH_YEAR)
    slash_mask = slash_parts["year"].notna() & non_missing
    ambiguous_count = 0
    if slash_mask.any():
        first = pd.to_numeric(slash_parts["first"], errors="coerce")
        second = pd.to_numeric(slash_parts["second"], errors="coerce")
        day_first_evidence = slash_mask & first.gt(12) & second.le(12)
        month_first_evidence = slash_mask & second.gt(12) & first.le(12)
        if day_first_evidence.any() and not month_first_evidence.any():
            parsed.loc[slash_mask] = pd.to_datetime(
                text.loc[slash_mask],
                format="%d/%m/%Y",
                errors="coerce",
                utc=True,
            )
        elif month_first_evidence.any() and not day_first_evidence.any():
            parsed.loc[slash_mask] = pd.to_datetime(
                text.loc[slash_mask],
                format="%m/%d/%Y",
                errors="coerce",
                utc=True,
            )
        else:
            # Conflicting or wholly ambiguous conventions must not be guessed.
            deterministic_day = day_first_evidence
            deterministic_month = month_first_evidence
            if deterministic_day.any():
                parsed.loc[deterministic_day] = pd.to_datetime(
                    text.loc[deterministic_day],
                    format="%d/%m/%Y",
                    errors="coerce",
                    utc=True,
                )
            if deterministic_month.any():
                parsed.loc[deterministic_month] = pd.to_datetime(
                    text.loc[deterministic_month],
                    format="%m/%d/%Y",
                    errors="coerce",
                    utc=True,
                )
            ambiguous_count = int(
                (slash_mask & ~deterministic_day & ~deterministic_month).sum()
            )

    remaining = non_missing & parsed.isna() & ~slash_mask
    # Never pass arbitrary numeric values to ``to_datetime``: Pandas interprets
    # them as Unix nanoseconds, producing the classic false 1970 trend.
    if "year" in tokens:
        year_values = _parse_years(series.loc[remaining])
        parsed.loc[year_values.index] = year_values

    remaining = remaining & parsed.isna()
    if remaining.any():
        candidate_text = text.loc[remaining]
        deterministic_text = candidate_text.str.match(_YEAR_FIRST_DATE, na=False)
        deterministic_text |= candidate_text.str.contains(
            r"[A-Za-z]", regex=True, na=False
        ) & candidate_text.str.contains(r"\d{4}", regex=True, na=False)
        deterministic_indexes = candidate_text.index[deterministic_text]
        if len(deterministic_indexes):
            parsed.loc[deterministic_indexes] = pd.to_datetime(
                text.loc[deterministic_indexes],
                errors="coerce",
                format="mixed",
                utc=True,
            )
    return parsed, ambiguous_count


def profile_column(name: str, series: pd.Series) -> ColumnProfile:
    """Infer one semantic role while retaining normalized conversion series."""

    source_blank_mask = _blank_string_mask(series).fillna(False)
    normalized_frame = normalize_blanks(pd.DataFrame({name: series}))
    normalized = normalized_frame[name]
    blank_count = int(source_blank_mask.sum())
    non_missing_count = int(normalized.notna().sum())

    if is_identifier_name(name):
        return ColumnProfile(
            name=name,
            semantic_type="identifier",
            normalized=normalized,
            numeric=None,
            temporal=None,
            parse_rate=100.0,
            invalid_count=0,
            ambiguous_count=0,
            blank_count=blank_count,
        )
    if pd.api.types.is_bool_dtype(normalized.dtype):
        return ColumnProfile(
            name=name,
            semantic_type="boolean",
            normalized=normalized,
            numeric=None,
            temporal=None,
            parse_rate=100.0,
            invalid_count=0,
            ambiguous_count=0,
            blank_count=blank_count,
        )
    if pd.api.types.is_timedelta64_dtype(normalized.dtype):
        numeric_duration = normalized.dt.total_seconds()
        return ColumnProfile(
            name=name,
            semantic_type="number",
            normalized=normalized,
            numeric=numeric_duration,
            temporal=None,
            parse_rate=100.0,
            invalid_count=0,
            ambiguous_count=0,
            blank_count=blank_count,
        )

    temporal, ambiguous_count = _parse_temporal_values(name, normalized)
    temporal_valid = int(temporal.notna().sum())
    temporal_rate = (
        temporal_valid / non_missing_count * 100 if non_missing_count else 100.0
    )
    datetime_dtype = pd.api.types.is_datetime64_any_dtype(normalized.dtype)
    hinted_datetime = has_datetime_name_hint(name)
    invalid_date_count = max(non_missing_count - temporal_valid, 0)
    inferred_datetime = (
        datetime_dtype
        or (hinted_datetime and temporal_valid > 0)
        or (
            non_missing_count > 0
            and temporal_rate >= AUTOMATIC_DATE_CONFIDENCE * 100
        )
    )
    if inferred_datetime:
        return ColumnProfile(
            name=name,
            semantic_type="datetime",
            normalized=normalized,
            numeric=None,
            temporal=temporal,
            parse_rate=round(temporal_rate, 2),
            invalid_count=max(non_missing_count - temporal_valid, 0),
            ambiguous_count=ambiguous_count,
            blank_count=blank_count,
            date_hint=hinted_datetime,
            date_parse_rate=round(temporal_rate, 2),
            invalid_date_count=invalid_date_count,
        )

    numeric = pd.to_numeric(normalized, errors="coerce")
    numeric_valid = int(numeric.notna().sum())
    numeric_rate = numeric_valid / non_missing_count if non_missing_count else 1.0
    inferred_numeric = pd.api.types.is_numeric_dtype(normalized.dtype) or (
        non_missing_count > 0 and numeric_rate >= NUMERIC_TEXT_CONFIDENCE
    )
    if inferred_numeric:
        return ColumnProfile(
            name=name,
            semantic_type="number",
            normalized=normalized,
            numeric=numeric,
            temporal=None,
            parse_rate=round(numeric_rate * 100, 2),
            invalid_count=max(non_missing_count - numeric_valid, 0),
            ambiguous_count=0,
            blank_count=blank_count,
            date_hint=hinted_datetime,
            date_parse_rate=round(temporal_rate, 2),
            invalid_date_count=(invalid_date_count if hinted_datetime else 0),
        )

    return ColumnProfile(
        name=name,
        semantic_type="categorical",
        normalized=normalized,
        numeric=None,
        temporal=None,
        parse_rate=(round(temporal_rate, 2) if hinted_datetime else 100.0),
        invalid_count=(invalid_date_count if hinted_datetime else 0),
        ambiguous_count=(ambiguous_count if hinted_datetime else 0),
        blank_count=blank_count,
        date_hint=hinted_datetime,
        date_parse_rate=round(temporal_rate, 2),
        invalid_date_count=(invalid_date_count if hinted_datetime else 0),
    )


def profile_dataframe(dataframe: pd.DataFrame) -> dict[str, ColumnProfile]:
    """Return profiles keyed by the project's normalized string column names."""

    return {
        str(column): profile_column(str(column), dataframe[column])
        for column in dataframe.columns
    }


def category_values(series: pd.Series) -> tuple[pd.Series, str | None]:
    """Return collision-safe labels for categorical grouping."""

    normalized = normalize_blanks(pd.DataFrame({"value": series}))["value"]
    text = normalized.astype("string")
    if not normalized.isna().any():
        return text.astype(str), None

    existing = set(text.dropna().astype(str))
    missing_label = MISSING_LABEL
    suffix = 1
    while missing_label in existing:
        suffix += 1
        missing_label = f"{MISSING_LABEL} (absence {suffix})"
    return text.fillna(missing_label).astype(str), missing_label

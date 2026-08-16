"""Détection d'anomalies multivariées avec Isolation Forest."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from .profiling import profile_dataframe
from .serialization import finite_number, json_value


MAX_RETURNED_ANOMALIES = 100


def detect_anomalies(dataframe: pd.DataFrame) -> dict[str, Any]:
    """Détecte et explique sommairement les lignes atypiques.

    Les colonnes numériques constantes sont retirées, les valeurs manquantes
    sont imputées par médiane, puis les variables sont standardisées. Les
    colonnes contributrices correspondent aux plus grands écarts standardisés ;
    il s'agit d'une aide à l'investigation, pas d'une causalité métier.
    """

    profiles = profile_dataframe(dataframe)
    excluded_identifiers = [
        str(column)
        for column in dataframe.columns
        if profiles[str(column)].is_identifier
    ]
    numeric = pd.DataFrame(index=dataframe.index)
    for column in dataframe.columns:
        column_name = str(column)
        profile = profiles[column_name]
        if profile.semantic_type != "number" or profile.numeric is None:
            continue
        values = profile.numeric.to_numpy(dtype=np.float64, na_value=np.nan)
        numeric[column_name] = pd.Series(values, index=dataframe.index)
    numeric = numeric.replace([np.inf, -np.inf], np.nan)
    usable_columns = [
        str(column)
        for column in numeric.columns
        if numeric[column].notna().sum() >= 3 and numeric[column].nunique(dropna=True) > 1
    ]
    if len(dataframe) < 5 or not usable_columns:
        return {
            "applicable": False,
            "count": 0,
            "total_count": 0,
            "returned_count": 0,
            "truncated": False,
            "rate": 0.0,
            "rows": [],
            "numeric_columns": usable_columns,
            "excluded_identifier_columns": excluded_identifiers,
            "method": "IsolationForest",
            "parameters": {"n_estimators": 200, "contamination": None, "random_state": 42},
            "message": "Au moins 5 lignes et une variable numérique non constante sont nécessaires.",
        }

    matrix = numeric[usable_columns].copy()
    missing_indicators = matrix.isna()
    values = matrix.to_numpy(dtype=np.float64)
    # Divide first by each maximum magnitude so variance calculations never
    # square values near ±1e308 and overflow.
    with np.errstate(invalid="ignore", over="ignore"):
        maximum_magnitudes = np.nanmax(np.abs(values), axis=0)
    safe_denominators = np.where(
        np.isfinite(maximum_magnitudes) & (maximum_magnitudes > 0),
        maximum_magnitudes,
        1.0,
    )
    bounded_values = values / safe_denominators
    for column_position in range(bounded_values.shape[1]):
        column_values = bounded_values[:, column_position]
        finite_values = column_values[np.isfinite(column_values)]
        median = float(np.median(finite_values)) if finite_values.size else 0.0
        column_values[~np.isfinite(column_values)] = median
        bounded_values[:, column_position] = column_values
    scaled_numeric = StandardScaler().fit_transform(bounded_values)
    scaled_numeric = np.nan_to_num(
        scaled_numeric,
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )

    indicator_columns = [
        column
        for column in usable_columns
        if missing_indicators[column].any()
        and not missing_indicators[column].all()
    ]
    feature_names = list(usable_columns)
    scaled = scaled_numeric
    if indicator_columns:
        indicator_values = missing_indicators[indicator_columns].to_numpy(
            dtype=np.float64
        )
        scaled_indicators = StandardScaler().fit_transform(indicator_values)
        scaled = np.column_stack([scaled_numeric, scaled_indicators])
        feature_names.extend(
            f"{column} (valeur manquante)" for column in indicator_columns
        )
    contamination = min(0.10, max(0.01, 1 / len(dataframe)))
    model = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        random_state=42,
        n_jobs=1,
    )
    predictions = model.fit_predict(scaled)
    raw_scores = -model.score_samples(scaled)
    score_min, score_max = float(raw_scores.min()), float(raw_scores.max())
    if score_max > score_min:
        normalised_scores = (raw_scores - score_min) / (score_max - score_min)
    else:
        normalised_scores = np.zeros_like(raw_scores)

    anomaly_positions = np.flatnonzero(predictions == -1)
    ranked_positions = sorted(
        (int(position) for position in anomaly_positions),
        key=lambda position: float(normalised_scores[position]),
        reverse=True,
    )
    total_count = len(ranked_positions)
    returned_positions = ranked_positions[:MAX_RETURNED_ANOMALIES]
    rows: list[dict[str, Any]] = []
    for position in returned_positions:
        contributions = np.abs(scaled[position])
        top_positions = np.argsort(contributions)[::-1][
            : min(3, len(feature_names))
        ]
        original_index = dataframe.index[position]
        row_index = json_value(original_index)
        if isinstance(original_index, (int, np.integer)):
            row_index = int(original_index) + 1
        values = {
            str(column): json_value(
                profiles[str(column)].normalized.iloc[position]
            )
            for column in dataframe.columns
        }
        rows.append(
            {
                "row_index": row_index,
                "anomaly_score": finite_number(normalised_scores[position], 4),
                "contributing_columns": [
                    feature_names[index] for index in top_positions
                ],
                "values": values,
            }
        )
    returned_count = len(rows)
    return {
        "applicable": True,
        "count": total_count,
        "total_count": total_count,
        "returned_count": returned_count,
        "truncated": total_count > returned_count,
        "rate": finite_number(total_count / len(dataframe) * 100),
        "rows": rows,
        "numeric_columns": usable_columns,
        "excluded_identifier_columns": excluded_identifiers,
        "method": "IsolationForest",
        "parameters": {
            "n_estimators": 200,
            "contamination": finite_number(contamination, 4),
            "random_state": 42,
        },
        "message": (
            "Les anomalies sont des observations à examiner ; elles ne sont pas automatiquement des erreurs."
        ),
    }

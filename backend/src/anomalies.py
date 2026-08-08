"""Détection d'anomalies multivariées avec Isolation Forest."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from .serialization import finite_number, json_value


def detect_anomalies(dataframe: pd.DataFrame) -> dict[str, Any]:
    """Détecte et explique sommairement les lignes atypiques.

    Les colonnes numériques constantes sont retirées, les valeurs manquantes
    sont imputées par médiane, puis les variables sont standardisées. Les
    colonnes contributrices correspondent aux plus grands écarts standardisés ;
    il s'agit d'une aide à l'investigation, pas d'une causalité métier.
    """

    numeric = dataframe.select_dtypes(include="number").copy()
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
            "rate": 0.0,
            "rows": [],
            "numeric_columns": usable_columns,
            "method": "IsolationForest",
            "parameters": {"n_estimators": 200, "contamination": None, "random_state": 42},
            "message": "Au moins 5 lignes et une variable numérique non constante sont nécessaires.",
        }

    matrix = numeric[usable_columns].copy()
    for column in usable_columns:
        median = matrix[column].median()
        matrix[column] = matrix[column].fillna(0.0 if pd.isna(median) else median)
    scaled = StandardScaler().fit_transform(matrix)
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
    rows: list[dict[str, Any]] = []
    for position in anomaly_positions:
        contributions = np.abs(scaled[position])
        top_positions = np.argsort(contributions)[::-1][: min(3, len(usable_columns))]
        original_index = dataframe.index[position]
        row_index = json_value(original_index)
        if isinstance(original_index, (int, np.integer)):
            row_index = int(original_index) + 1
        values = {
            str(column): json_value(dataframe.iloc[position][column])
            for column in dataframe.columns
        }
        rows.append(
            {
                "row_index": row_index,
                "anomaly_score": finite_number(normalised_scores[position], 4),
                "contributing_columns": [usable_columns[index] for index in top_positions],
                "values": values,
            }
        )
    rows.sort(key=lambda row: row["anomaly_score"], reverse=True)
    count = len(rows)
    return {
        "applicable": True,
        "count": count,
        "rate": finite_number(count / len(dataframe) * 100),
        "rows": rows,
        "numeric_columns": usable_columns,
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

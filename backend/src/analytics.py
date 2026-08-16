"""Agrégations génériques utilisées par les dashboards Recharts."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .dataset_store import DatasetSnapshot
from .anomalies import detect_anomalies
from .profiling import (
    ColumnProfile,
    category_values,
    profile_column,
    profile_dataframe,
)
from .quality import audit_data_quality
from .serialization import finite_number


AGGREGATIONS = ("sum", "mean", "median", "min", "max", "count")
# Valeur réservée au comptage des lignes. Une sentinelle explicite évite de
# masquer une vraie colonne métier nommée ``count``.
ROW_COUNT_METRIC = "__row_count__"


def _numeric_columns(
    df: pd.DataFrame,
    profiles: dict[str, ColumnProfile] | None = None,
) -> list[str]:
    profiles = profiles or profile_dataframe(df)
    return [
        str(column)
        for column in df.columns
        if profiles[str(column)].semantic_type == "number"
    ]


def _dimension_columns(
    df: pd.DataFrame,
    profiles: dict[str, ColumnProfile] | None = None,
) -> list[str]:
    profiles = profiles or profile_dataframe(df)
    dimensions = [
        str(column)
        for column in df.columns
        if profiles[str(column)].semantic_type != "number"
    ]
    if dimensions:
        return dimensions
    # Un dataset entièrement numérique doit rester visualisable. Le backend
    # limite déjà la série finale aux 20 groupes principaux.
    return [str(column) for column in df.columns]


def _pick_dimension(df: pd.DataFrame, options: list[str]) -> str:
    priorities = ("status", "category", "source", "country", "business_unit", "month")
    lowered = {option.lower(): option for option in options}
    for priority in priorities:
        if priority in lowered:
            return lowered[priority]
    return options[0]


def _pick_metric(options: list[str]) -> str:
    priorities = ("revenue", "sales", "amount", "margin", "score", "budget", "actual")
    lowered = {option.lower(): option for option in options}
    for priority in priorities:
        if priority in lowered:
            return lowered[priority]
    return options[0] if options else ROW_COUNT_METRIC


def _looks_temporal(name: str, series: pd.Series) -> bool:
    return profile_column(name, series).semantic_type == "datetime"


def _aggregate(
    df: pd.DataFrame,
    dimension: str,
    metric: str,
    aggregation: str,
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    dimension_profile = profile_column(dimension, df[dimension])
    working = pd.DataFrame(index=df.index)
    temporal = dimension_profile.semantic_type == "datetime"
    missing_label: str | None = None
    if temporal:
        parsed = dimension_profile.temporal
        assert parsed is not None
        valid_dates = parsed.notna()
        working = working.loc[valid_dates].copy()
        parsed = parsed.loc[valid_dates]
        # Le mois donne une tendance stable et lisible pour les dates journalières.
        working["__dimension"] = (
            parsed.dt.tz_convert("UTC")
            .dt.tz_localize(None)
            .dt.to_period("M")
            .astype(str)
        )
    else:
        labels, missing_label = category_values(df[dimension])
        working["__dimension"] = labels

    metric_key = "__metric_value"
    if metric != ROW_COUNT_METRIC:
        metric_profile = profile_column(metric, df[metric])
        numeric_metric = metric_profile.numeric
        if numeric_metric is None:
            numeric_metric = pd.to_numeric(df[metric], errors="coerce")
        working[metric_key] = numeric_metric.reindex(working.index).replace(
            [np.inf, -np.inf], np.nan
        )

    if metric == ROW_COUNT_METRIC:
        grouped = working.groupby("__dimension", dropna=False).size()
    elif aggregation == "count":
        grouped = working.groupby("__dimension", dropna=False)[metric_key].count()
    else:
        grouped_object = working.groupby("__dimension", dropna=False)[metric_key]
        grouped = (
            grouped_object.sum(min_count=1)
            if aggregation == "sum"
            else getattr(grouped_object, aggregation)()
        )

    if temporal:
        grouped = grouped.sort_index()
    else:
        grouped = grouped.sort_values(ascending=False).head(20)
    data = [
        {"label": str(label), "value": finite_number(value)}
        for label, value in grouped.items()
        if pd.notna(label)
    ]
    series_kind = "temporal" if temporal else "categorical"
    metadata = {
        "series_kind": series_kind,
        "missing_dimension_count": int(dimension_profile.normalized.isna().sum()),
        "invalid_dimension_count": dimension_profile.invalid_count,
        "dimension_parse_rate": dimension_profile.parse_rate,
        "missing_label": missing_label,
    }
    return data, "line" if temporal else "bar", metadata


def _contextual_kpis(
    df: pd.DataFrame,
    quality_score: float,
    profiles: dict[str, ColumnProfile] | None = None,
) -> list[dict[str, Any]]:
    """Produit des KPI vrais en privilégiant les colonnes métier reconnues."""

    kpis: list[dict[str, Any]] = [
        {
            "id": "rows",
            "label": "Lignes analysées",
            "value": int(len(df)),
            "hint": "Volume du dataset actif",
            "tone": "neutral",
        }
    ]
    profiles = profiles or profile_dataframe(df)
    lowered = {str(column).lower(): str(column) for column in df.columns}
    if "revenue" in lowered:
        revenue_profile = profiles[lowered["revenue"]]
        revenue = revenue_profile.numeric
        if revenue is None:
            revenue = pd.to_numeric(df[lowered["revenue"]], errors="coerce")
        revenue = revenue.replace([np.inf, -np.inf], np.nan)
        kpis.append(
            {
                "id": "revenue",
                "label": "Revenu total",
                "value": finite_number(revenue.sum(min_count=1)),
                "hint": "Somme de la colonne revenue",
                "tone": "success",
            }
        )
    if "conversion" in lowered:
        conversion_profile = profiles[lowered["conversion"]]
        conversion = conversion_profile.numeric
        if conversion is None:
            conversion = pd.to_numeric(df[lowered["conversion"]], errors="coerce")
        conversion = conversion.replace([np.inf, -np.inf], np.nan)
        conversion_mean = conversion.mean()
        # Les colonnes de conversion sont couramment encodées soit entre 0 et
        # 1, soit directement entre 0 et 100. On ne multiplie que le premier cas.
        conversion_percent = (
            conversion_mean * 100
            if pd.notna(conversion_mean)
            and conversion.dropna().abs().max() <= 1
            else conversion_mean
        )
        kpis.append(
            {
                "id": "conversion_rate",
                "label": "Taux de conversion",
                "value": finite_number(conversion_percent),
                "hint": "Pourcentage moyen de conversion",
                "tone": "success",
                "unit": "%",
            }
        )
    elif "margin" in lowered:
        margin_profile = profiles[lowered["margin"]]
        margin = margin_profile.numeric
        if margin is None:
            margin = pd.to_numeric(df[lowered["margin"]], errors="coerce")
        margin = margin.replace([np.inf, -np.inf], np.nan)
        kpis.append(
            {
                "id": "margin",
                "label": "Marge totale",
                "value": finite_number(margin.sum(min_count=1)),
                "hint": "Somme de la colonne margin",
                "tone": "success",
            }
        )
    if "score" in lowered:
        score_profile = profiles[lowered["score"]]
        score = score_profile.numeric
        if score is None:
            score = pd.to_numeric(df[lowered["score"]], errors="coerce")
        kpis.append(
            {
                "id": "average_score",
                "label": "Score moyen",
                "value": finite_number(score.mean()),
                "hint": "Moyenne des valeurs disponibles",
                "tone": "neutral",
            }
        )
    elif "progress" in lowered:
        progress_profile = profiles[lowered["progress"]]
        progress = progress_profile.numeric
        if progress is None:
            progress = pd.to_numeric(df[lowered["progress"]], errors="coerce")
        kpis.append(
            {
                "id": "average_progress",
                "label": "Progression moyenne",
                "value": finite_number(progress.mean()),
                "hint": "Moyenne de la colonne progress",
                "tone": "neutral",
                "unit": "%",
            }
        )
    kpis.append(
        {
            "id": "quality",
            "label": "Score qualité",
            "value": finite_number(quality_score, 1),
            "hint": "Score automatique sur 100",
            "tone": "success" if quality_score >= 90 else "warning" if quality_score >= 70 else "danger",
            "unit": "/100",
        }
    )
    return kpis[:4]


def _overview_kpis(
    df: pd.DataFrame,
    quality: dict[str, Any],
    anomalies: dict[str, Any],
) -> list[dict[str, Any]]:
    """Expose les contrôles structurants avant les éventuels KPI métier."""

    summary = quality["summary"]
    score = quality["score"]
    anomaly_applicable = anomalies.get("applicable", True)
    core = [
        {
            "id": "rows",
            "label": "Lignes analysées",
            "value": int(len(df)),
            "hint": "Volume du dataset actif",
            "tone": "neutral",
        },
        {
            "id": "columns",
            "label": "Colonnes",
            "value": int(df.shape[1]),
            "hint": "Largeur du schéma actif",
            "tone": "neutral",
        },
        {
            "id": "quality",
            "label": "Score qualité",
            "value": finite_number(score, 1),
            "hint": "Score automatique et explicable",
            "tone": "success" if score >= 90 else "warning" if score >= 70 else "danger",
            "unit": "/100",
        },
        {
            "id": "anomalies",
            "label": "Anomalies",
            "value": int(anomalies["count"]) if anomaly_applicable else "—",
            "hint": (
                "Lignes signalées par Isolation Forest"
                if anomaly_applicable
                else "Détection non applicable à ce dataset"
            ),
            "tone": (
                "warning"
                if anomaly_applicable and anomalies["count"]
                else "success" if anomaly_applicable else "neutral"
            ),
        },
        {
            "id": "missing_values",
            "label": "Valeurs manquantes",
            "value": int(summary["missing_count"]),
            "hint": f"{summary['missing_rate']} % des cellules",
            "tone": "warning" if summary["missing_count"] else "success",
        },
        {
            "id": "duplicates",
            "label": "Alertes doublons",
            "value": int(summary["duplicate_count"]),
            "hint": (
                f"{summary['strict_duplicate_count']} strict(s), identifiants et indicateurs inclus"
            ),
            "tone": "warning" if summary["duplicate_count"] else "success",
        },
    ]
    contextual = [
        kpi
        for kpi in _contextual_kpis(df, score)
        if kpi["id"] not in {item["id"] for item in core}
    ]
    return [*core, *contextual]


def build_dashboard(
    dataframe: pd.DataFrame,
    dimension: str | None = None,
    metric: str | None = None,
    aggregation: str | None = None,
) -> dict[str, Any]:
    """Construit une série agrégée contrôlée par trois paramètres explicites."""

    profiles = profile_dataframe(dataframe)
    dimensions = _dimension_columns(dataframe, profiles)
    numeric = _numeric_columns(dataframe, profiles)
    metric_options = [ROW_COUNT_METRIC, *numeric]
    if not dimensions:
        raise ValueError("Aucune colonne ne peut être utilisée comme dimension.")
    selected_dimension = dimension or _pick_dimension(dataframe, dimensions)
    default_metrics = [column for column in numeric if column != selected_dimension]
    selected_metric = metric or _pick_metric(default_metrics)
    selected_aggregation = (
        "count" if selected_metric == ROW_COUNT_METRIC else aggregation or "sum"
    )
    if selected_dimension not in dimensions:
        raise ValueError(f"Dimension inconnue : {selected_dimension}")
    if selected_metric not in metric_options:
        raise ValueError(f"Métrique inconnue : {selected_metric}")
    if selected_aggregation not in AGGREGATIONS:
        raise ValueError(f"Agrégation inconnue : {selected_aggregation}")
    data, chart_type, series_metadata = _aggregate(
        dataframe, selected_dimension, selected_metric, selected_aggregation
    )
    quality_score = audit_data_quality(dataframe)["score"]
    return {
        "dimension": selected_dimension,
        "metric": selected_metric,
        "aggregation": selected_aggregation,
        "dimension_options": dimensions,
        "metric_options": metric_options,
        "aggregation_options": list(AGGREGATIONS),
        "chart_type": chart_type,
        "data": data,
        "kpis": _contextual_kpis(dataframe, quality_score, profiles),
        **series_metadata,
    }


def build_overview(
    snapshot: DatasetSnapshot,
    quality: dict[str, Any] | None = None,
    anomalies: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble le contrat complet de la page Overview."""

    df = snapshot.dataframe
    profiles = profile_dataframe(df)
    quality = quality or audit_data_quality(df)
    anomalies = anomalies or detect_anomalies(df)
    columns = quality["columns"]
    dimensions = _dimension_columns(df, profiles)
    dimension = _pick_dimension(df, dimensions) if dimensions else None
    category_breakdown: list[dict[str, Any]] = []
    category_missing_label: str | None = None
    if dimension:
        category_labels, category_missing_label = category_values(df[dimension])
        counts = category_labels.value_counts().head(8)
        category_breakdown = [
            {"name": str(name), "value": int(value)} for name, value in counts.items()
        ]

    temporal_options = [
        column
        for column in dimensions
        if profiles[column].semantic_type == "datetime"
    ]
    metric = _pick_metric(_numeric_columns(df, profiles))
    trend_metadata: dict[str, Any] = {
        "series_kind": "categorical",
        "missing_dimension_count": 0,
        "invalid_dimension_count": 0,
        "dimension_parse_rate": 100.0,
        "missing_label": None,
    }
    if temporal_options:
        trend, _, trend_metadata = _aggregate(
            df,
            temporal_options[0],
            metric,
            "count" if metric == ROW_COUNT_METRIC else "sum",
        )
    elif dimension:
        trend, _, trend_metadata = _aggregate(
            df, dimension, ROW_COUNT_METRIC, "count"
        )
    else:
        trend = []

    issue_count = len([problem for problem in quality["problems"] if not problem.startswith("Aucun")])
    formatted_rows = f"{len(df):,}".replace(",", " ")
    summary = (
        f"{snapshot.name} contient {formatted_rows} lignes et {df.shape[1]} colonnes. "
        f"Le score qualité est de {quality['score']}/100 avec {issue_count} type(s) "
        "de problème détecté(s)."
    )
    return {
        "dataset": snapshot.metadata(),
        "kpis": _overview_kpis(df, quality, anomalies),
        "quality_score": quality["score"],
        "summary": summary,
        "recommendations": quality["recommendations"][:4],
        "quality_by_column": [
            {
                "column": column["column"],
                "score": column["score"],
                "missing_rate": column["missing_rate"],
            }
            for column in columns
        ],
        "missing_distribution": [
            {"column": column["column"], "missing_rate": column["missing_rate"]}
            for column in columns
            if column["missing_count"] > 0
        ],
        "category_breakdown": category_breakdown,
        "category_missing_label": category_missing_label,
        "trend": trend,
        "series_kind": trend_metadata["series_kind"],
        "trend_series_kind": trend_metadata["series_kind"],
        "trend_meta": trend_metadata,
    }

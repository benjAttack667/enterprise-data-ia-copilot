"""Agrégations génériques utilisées par les dashboards Recharts."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .dataset_store import DatasetSnapshot
from .anomalies import detect_anomalies
from .quality import audit_data_quality
from .serialization import finite_number


AGGREGATIONS = ("sum", "mean", "median", "min", "max", "count")
# Valeur réservée au comptage des lignes. Une sentinelle explicite évite de
# masquer une vraie colonne métier nommée ``count``.
ROW_COUNT_METRIC = "__row_count__"


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    return [str(column) for column in df.select_dtypes(include="number").columns]


def _dimension_columns(df: pd.DataFrame) -> list[str]:
    numeric = set(df.select_dtypes(include="number").columns)
    dimensions = [str(column) for column in df.columns if column not in numeric]
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
    lowered = name.lower()
    if any(token in lowered for token in ("date", "month", "year", "time", "created", "updated")):
        return True
    if not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
        return False
    parsed = pd.to_datetime(series, errors="coerce", format="mixed")
    return bool(parsed.notna().mean() >= 0.8)


def _aggregate(
    df: pd.DataFrame,
    dimension: str,
    metric: str,
    aggregation: str,
) -> tuple[list[dict[str, Any]], str]:
    source_columns = [dimension] if metric == ROW_COUNT_METRIC else list(
        dict.fromkeys([dimension, metric])
    )
    working = df[source_columns].copy()
    metric_key = metric
    # Dimension et métrique peuvent légitimement être la même colonne dans un
    # dataset numérique. Une colonne technique empêche Pandas de renvoyer un
    # DataFrame lors de la sélection de la métrique.
    if metric != ROW_COUNT_METRIC and metric == dimension:
        metric_key = "__metric_value"
        working[metric_key] = df[metric]
    temporal = _looks_temporal(dimension, working[dimension])
    dimension_key = dimension
    if temporal:
        parsed = pd.to_datetime(working[dimension], errors="coerce", format="mixed")
        working = working.loc[parsed.notna()].copy()
        parsed = parsed.loc[parsed.notna()]
        # Le mois donne une tendance stable et lisible pour les dates journalières.
        working["__dimension"] = parsed.dt.to_period("M").astype(str)
        dimension_key = "__dimension"
    else:
        working[dimension] = working[dimension].fillna("Valeur manquante").astype(str)

    if metric == ROW_COUNT_METRIC:
        grouped = working.groupby(dimension_key, dropna=False).size()
    elif aggregation == "count":
        grouped = working.groupby(dimension_key, dropna=False)[metric_key].count()
    else:
        working[metric_key] = pd.to_numeric(
            working[metric_key], errors="coerce"
        ).replace(
            [np.inf, -np.inf], np.nan
        )
        grouped_object = working.groupby(dimension_key, dropna=False)[metric_key]
        grouped = getattr(grouped_object, aggregation)()

    if temporal:
        grouped = grouped.sort_index()
    else:
        grouped = grouped.sort_values(ascending=False).head(20)
    data = [
        {"label": str(label), "value": finite_number(value)}
        for label, value in grouped.items()
        if pd.notna(label)
    ]
    return data, "line" if temporal else "bar"


def _contextual_kpis(df: pd.DataFrame, quality_score: float) -> list[dict[str, Any]]:
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
    lowered = {str(column).lower(): str(column) for column in df.columns}
    if "revenue" in lowered:
        revenue = pd.to_numeric(df[lowered["revenue"]], errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        )
        kpis.append(
            {
                "id": "revenue",
                "label": "Revenu total",
                "value": finite_number(revenue.sum()),
                "hint": "Somme de la colonne revenue",
                "tone": "success",
            }
        )
    if "conversion" in lowered:
        conversion = pd.to_numeric(df[lowered["conversion"]], errors="coerce")
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
        margin = pd.to_numeric(df[lowered["margin"]], errors="coerce")
        kpis.append(
            {
                "id": "margin",
                "label": "Marge totale",
                "value": finite_number(margin.sum()),
                "hint": "Somme de la colonne margin",
                "tone": "success",
            }
        )
    if "score" in lowered:
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

    dimensions = _dimension_columns(dataframe)
    numeric = _numeric_columns(dataframe)
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
    data, chart_type = _aggregate(
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
        "kpis": _contextual_kpis(dataframe, quality_score),
    }


def build_overview(
    snapshot: DatasetSnapshot,
    quality: dict[str, Any] | None = None,
    anomalies: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble le contrat complet de la page Overview."""

    df = snapshot.dataframe
    quality = quality or audit_data_quality(df)
    anomalies = anomalies or detect_anomalies(df)
    columns = quality["columns"]
    dimensions = _dimension_columns(df)
    dimension = _pick_dimension(df, dimensions) if dimensions else None
    category_breakdown: list[dict[str, Any]] = []
    if dimension:
        counts = df[dimension].fillna("Valeur manquante").astype(str).value_counts().head(8)
        category_breakdown = [
            {"name": str(name), "value": int(value)} for name, value in counts.items()
        ]

    temporal_options = [
        column for column in dimensions if _looks_temporal(column, df[column])
    ]
    metric = _pick_metric(_numeric_columns(df))
    if temporal_options:
        trend, _ = _aggregate(
            df,
            temporal_options[0],
            metric,
            "count" if metric == ROW_COUNT_METRIC else "sum",
        )
    elif dimension:
        trend, _ = _aggregate(df, dimension, ROW_COUNT_METRIC, "count")
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
        "trend": trend,
    }

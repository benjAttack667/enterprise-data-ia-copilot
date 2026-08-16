"""Audit Data Quality explicable fondé sur Pandas."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .profiling import normalize_blanks, profile_dataframe


def _normalise_blanks(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Traite les chaînes vides comme des valeurs manquantes."""

    return normalize_blanks(dataframe)


def _outlier_mask(series: pd.Series) -> pd.Series:
    """Détecte les valeurs extrêmes avec la règle robuste de l'IQR."""

    numeric = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    clean = numeric.dropna()
    if len(clean) < 4 or clean.nunique() < 2:
        return pd.Series(False, index=series.index)
    maximum_magnitude = float(clean.abs().max())
    if np.isfinite(maximum_magnitude) and maximum_magnitude > 0:
        numeric = numeric / maximum_magnitude
        clean = numeric.dropna()
    q1, q3 = clean.quantile([0.25, 0.75])
    iqr = q3 - q1
    if not np.isfinite(iqr) or iqr == 0:
        return pd.Series(False, index=series.index)
    return (numeric < q1 - 1.5 * iqr) | (numeric > q3 + 1.5 * iqr)


def _mixed_type_mask(series: pd.Series) -> bool:
    """Signale prudemment un mélange de nombres et de texte dans une colonne."""

    clean = series.dropna().astype(str).str.strip()
    if len(clean) < 4:
        return False
    numeric_share = pd.to_numeric(clean, errors="coerce").notna().mean()
    return bool(0.1 < numeric_share < 0.9)


def _duplicate_masks(dataframe: pd.DataFrame) -> dict[str, pd.Series]:
    """Distingue doublons stricts, identifiants répétés et indicateurs explicites."""

    strict = dataframe.duplicated(keep="first")
    identifier = pd.Series(False, index=dataframe.index)
    flagged = pd.Series(False, index=dataframe.index)
    identifier_columns = [
        column
        for column in dataframe.columns
        if str(column).lower() == "id" or str(column).lower().endswith("_id")
    ]
    for column in identifier_columns:
        non_null = dataframe[column].notna()
        identifier |= non_null & dataframe[column].duplicated(keep="first")
    for column in dataframe.columns:
        if "duplicate" not in str(column).lower():
            continue
        numeric = pd.to_numeric(dataframe[column], errors="coerce")
        text = dataframe[column].astype("string").str.strip().str.lower()
        flagged |= (numeric.gt(0) | text.isin({"true", "yes", "y", "oui"})).fillna(False)
    return {
        "strict": strict.fillna(False),
        "identifier": identifier.fillna(False),
        "flagged": flagged.fillna(False),
        "combined": (strict | identifier | flagged).fillna(False),
    }


def audit_data_quality(dataframe: pd.DataFrame) -> dict[str, Any]:
    """Calcule un score sur 100 et le détail de chaque contrôle.

    Le score est un indicateur de triage : complétude (50 points), doublons
    (25), valeurs extrêmes (15) et incohérences de type/valeurs infinies (10).
    Il ne remplace pas les règles de validité propres au métier.
    """

    profiles = profile_dataframe(dataframe)
    df = _normalise_blanks(dataframe)
    row_count, column_count = df.shape
    total_cells = max(row_count * column_count, 1)
    missing_by_column = df.isna().sum()
    missing_count = int(missing_by_column.sum())
    missing_fraction = missing_count / total_cells if row_count and column_count else 1.0
    duplicate_masks = _duplicate_masks(df)
    duplicate_mask = duplicate_masks["combined"]
    duplicate_count = int(duplicate_mask.sum())
    duplicate_fraction = duplicate_count / row_count if row_count else 0.0

    outlier_masks: dict[str, pd.Series] = {}
    invalid_masks: dict[str, pd.Series] = {}
    all_outliers = pd.Series(False, index=df.index)
    all_invalid = pd.Series(False, index=df.index)
    for column in df.columns:
        column_name = str(column)
        profile = profiles[column_name]
        if profile.semantic_type != "number" or profile.numeric is None:
            continue
        numeric = profile.numeric.reindex(df.index)
        outliers = _outlier_mask(numeric).fillna(False)
        invalid = (numeric.eq(np.inf) | numeric.eq(-np.inf)).fillna(False)
        outlier_masks[column_name] = outliers
        invalid_masks[column_name] = invalid
        all_outliers |= outliers
        all_invalid |= invalid

    outlier_count = int(all_outliers.sum())
    outlier_fraction = outlier_count / row_count if row_count else 0.0
    invalid_count = int(all_invalid.sum())
    invalid_fraction = invalid_count / row_count if row_count else 0.0
    invalid_numeric_cell_count = sum(
        int(mask.sum()) for mask in invalid_masks.values()
    )
    blank_count = sum(profile.blank_count for profile in profiles.values())
    invalid_date_count = sum(
        profile.invalid_date_count for profile in profiles.values()
    )
    parse_invalid_count = sum(
        profile.invalid_count for profile in profiles.values()
    )
    invalid_semantic_count = parse_invalid_count + invalid_numeric_cell_count
    semantic_invalid_fraction = parse_invalid_count / total_cells
    invalid_numeric_text_count = sum(
        profile.invalid_count
        for profile in profiles.values()
        if profile.semantic_type == "number"
    )
    mixed_columns = [
        str(column)
        for column in df.select_dtypes(include=["object", "string"]).columns
        if _mixed_type_mask(df[column])
    ]
    mixed_fraction = len(mixed_columns) / column_count if column_count else 0.0

    penalty = (
        min(missing_fraction, 1.0) * 50
        + min(duplicate_fraction, 1.0) * 25
        + min(outlier_fraction, 1.0) * 15
        + min(
            mixed_fraction + invalid_fraction + semantic_invalid_fraction,
            1.0,
        )
        * 10
    )
    score = 0.0 if not row_count or not column_count else round(max(0.0, 100 - penalty), 1)

    problems: list[str] = []
    recommendations: list[str] = []
    if missing_count:
        problems.append(f"{missing_count} valeur(s) manquante(s) ont été détectées.")
        recommendations.append(
            "Définir avec le métier une stratégie d'imputation ou d'exclusion des valeurs manquantes."
        )
    strict_duplicate_count = int(duplicate_masks["strict"].sum())
    identifier_duplicate_count = int(duplicate_masks["identifier"].sum())
    flagged_duplicate_count = int(duplicate_masks["flagged"].sum())
    if strict_duplicate_count:
        problems.append(f"{strict_duplicate_count} ligne(s) strictement dupliquée(s).")
    if identifier_duplicate_count:
        problems.append(f"{identifier_duplicate_count} identifiant(s) répété(s) à contrôler.")
    if flagged_duplicate_count:
        problems.append(f"{flagged_duplicate_count} ligne(s) marquée(s) par un indicateur de doublon.")
    if duplicate_count:
        recommendations.append("Valider les clés métier avant de supprimer les doublons.")
    if outlier_count:
        problems.append(f"{outlier_count} ligne(s) contiennent une valeur extrême au sens de l'IQR.")
        recommendations.append("Contrôler les valeurs extrêmes avec un référent métier.")
    if invalid_count:
        problems.append(f"{invalid_count} ligne(s) contiennent une valeur numérique infinie.")
        recommendations.append("Remplacer les valeurs infinies avant les agrégations et modèles.")
    if invalid_date_count:
        problems.append(
            f"{invalid_date_count} valeur(s) de date invalide(s) ont été détectée(s)."
        )
        recommendations.append(
            "Corriger les dates invalides et expliciter le format avant l'analyse temporelle."
        )
    if invalid_numeric_text_count:
        problems.append(
            f"{invalid_numeric_text_count} valeur(s) ne respectent pas le format numérique inféré."
        )
        recommendations.append(
            "Standardiser ou corriger les valeurs non numériques des mesures concernées."
        )
    if mixed_columns:
        problems.append(f"Types potentiellement mixtes : {', '.join(mixed_columns)}.")
        recommendations.append("Standardiser les formats des colonnes aux types mixtes.")
    if not problems:
        problems.append("Aucun problème structurel majeur détecté par les contrôles automatiques.")
        recommendations.append("Compléter l'audit par des règles de validité propres au métier.")

    columns: list[dict[str, Any]] = []
    for column in df.columns:
        column_name = str(column)
        profile = profiles[column_name]
        missing = int(missing_by_column[column])
        missing_rate = round((missing / row_count * 100) if row_count else 100.0, 2)
        column_outliers = int(outlier_masks.get(column_name, pd.Series(dtype=bool)).sum())
        column_invalid = int(invalid_masks.get(column_name, pd.Series(dtype=bool)).sum())
        semantic_invalid = int(profile.invalid_count)
        total_invalid = semantic_invalid + column_invalid
        issue_labels: list[str] = []
        if missing:
            issue_labels.append("missing_values")
        if missing == row_count and row_count:
            issue_labels.append("empty_column")
        if column_outliers:
            issue_labels.append("outliers")
        if column_invalid:
            issue_labels.append("non_finite_values")
        if profile.invalid_date_count:
            issue_labels.append("invalid_dates")
        elif semantic_invalid:
            issue_labels.append("invalid_numeric_values")
        if column_name in mixed_columns:
            issue_labels.append("mixed_types")
        column_penalty = missing_rate * 0.7
        if row_count:
            column_penalty += column_outliers / row_count * 20
            column_penalty += column_invalid / row_count * 20
            column_penalty += semantic_invalid / row_count * 20
        if column_name in mixed_columns:
            column_penalty += 10
        column_score = round(max(0.0, 100 - column_penalty), 1)
        status = "healthy" if column_score >= 95 else "warning" if column_score >= 70 else "critical"
        columns.append(
            {
                "column": column_name,
                "dtype": str(df[column].dtype),
                "inferred_type": profile.semantic_type,
                "semantic_type": profile.semantic_type,
                "parse_rate": profile.parse_rate,
                "invalid_count": total_invalid,
                "invalid_date_count": profile.invalid_date_count,
                "ambiguous_count": profile.ambiguous_count,
                "blank_count": profile.blank_count,
                "missing_count": missing,
                "missing_rate": missing_rate,
                "unique_count": int(df[column].nunique(dropna=True)),
                "score": column_score,
                "status": status,
                "issues": issue_labels,
            }
        )

    return {
        "score": score,
        "summary": {
            "row_count": int(row_count),
            "column_count": int(column_count),
            "missing_count": missing_count,
            "missing_rate": round(missing_fraction * 100, 2),
            "duplicate_count": duplicate_count,
            "duplicate_rate": round(duplicate_fraction * 100, 2),
            "strict_duplicate_count": strict_duplicate_count,
            "identifier_duplicate_count": identifier_duplicate_count,
            "flagged_duplicate_count": flagged_duplicate_count,
            "outlier_count": outlier_count,
            "outlier_rate": round(outlier_fraction * 100, 2),
            "invalid_numeric_count": invalid_count,
            "invalid_numeric_cell_count": int(invalid_numeric_cell_count),
            "blank_count": int(blank_count),
            "invalid_date_count": int(invalid_date_count),
            "invalid_semantic_count": int(invalid_semantic_count),
        },
        "problems": problems,
        "recommendations": recommendations,
        "columns": columns,
    }

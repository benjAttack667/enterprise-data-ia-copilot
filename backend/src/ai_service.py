"""Assistant IA avec mode local déterministe et bascule OpenAI facultative."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fallback_summary(
    overview: dict[str, Any],
    quality: dict[str, Any],
    anomalies: dict[str, Any],
    focus: str | None,
) -> str:
    dataset = overview["dataset"]
    anomaly_sentence = (
        f"{anomalies['count']} anomalie(s) détectée(s) par Isolation Forest."
        if anomalies.get("applicable", True)
        else "La détection d'anomalies n'est pas applicable à ce dataset."
    )
    summary = (
        f"Le dataset {dataset['name']} contient {dataset['rows']} lignes et "
        f"{dataset['columns']} colonnes. Son score de qualité est de "
        f"{quality['score']}/100 : {quality['summary']['missing_count']} valeur(s) "
        f"manquante(s) et {quality['summary']['duplicate_count']} alerte(s) de doublon. "
        f"{anomaly_sentence}"
    )
    if focus:
        summary += f" La synthèse a été orientée sur : {focus.strip()}."
    return summary


def _aggregate_context(
    overview: dict[str, Any], quality: dict[str, Any], anomalies: dict[str, Any]
) -> dict[str, Any]:
    """Limite le contexte envoyé à OpenAI aux indicateurs agrégés."""

    return {
        "dataset": overview["dataset"],
        "kpis": overview["kpis"],
        "quality": {
            "score": quality["score"],
            "summary": quality["summary"],
            "problems": quality["problems"],
            "recommendations": quality["recommendations"],
        },
        "schema": [
            {
                "column": column["column"],
                "dtype": column["dtype"],
                "inferred_type": column.get("inferred_type"),
                "parse_rate": column.get("parse_rate"),
                "invalid_count": column.get("invalid_count", 0),
                "blank_count": column.get("blank_count", 0),
                "missing_rate": column["missing_rate"],
                "unique_count": column["unique_count"],
            }
            for column in quality["columns"]
        ],
        "anomalies": {
            "applicable": anomalies.get("applicable", True),
            "count": anomalies["count"],
            "rate": anomalies["rate"],
            "message": anomalies.get("message"),
        },
    }


class AIService:
    """Utilise OpenAI si configuré, sinon répond à partir des statistiques locales."""

    def __init__(self, api_key: str | None, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def _openai_text(self, instruction: str, context: dict[str, Any]) -> str | None:
        if not self.api_key:
            return None
        try:
            # Import tardif : le fallback local reste disponible même sans le SDK.
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key, timeout=20.0, max_retries=1)
            response = client.responses.create(
                model=self.model,
                store=False,
                input=(
                    "Tu es un data analyst senior. Réponds en français, avec des faits "
                    "présents dans les agrégats et sans inventer de causalité. "
                    f"Instruction : {instruction}\n"
                    f"Agrégats JSON : {json.dumps(context, ensure_ascii=False)}"
                ),
            )
            text = getattr(response, "output_text", None)
            return text.strip() if text and text.strip() else None
        except Exception:
            # Une clé invalide, un quota ou une indisponibilité réseau ne doit pas
            # casser la démonstration : le calcul local reste la source de vérité.
            return None

    def summary(
        self,
        overview: dict[str, Any],
        quality: dict[str, Any],
        anomalies: dict[str, Any],
        focus: str | None = None,
    ) -> dict[str, Any]:
        """Génère une synthèse fondée sur les résultats d'analyse actuels."""

        context = _aggregate_context(overview, quality, anomalies)
        instruction = "Produis une synthèse exécutive en un court paragraphe."
        if focus:
            instruction += f" Mets l'accent sur : {focus.strip()}."
        text = self._openai_text(instruction, context)
        mode = "openai" if text else "fallback"
        if not text:
            text = _fallback_summary(overview, quality, anomalies, focus)
        return {
            "summary": text,
            "recommendations": quality["recommendations"][:4],
            "mode": mode,
            "provider": "openai" if mode == "openai" else "local-fallback",
            "generated_at": _now(),
        }

    def ask(
        self,
        question: str,
        overview: dict[str, Any],
        quality: dict[str, Any],
        anomalies: dict[str, Any],
    ) -> dict[str, Any]:
        """Répond à une question avec OpenAI ou des règles locales transparentes."""

        context = _aggregate_context(overview, quality, anomalies)
        text = self._openai_text(f"Question utilisateur : {question}", context)
        mode = "openai" if text else "fallback"
        if not text:
            lowered = question.casefold()
            summary = quality["summary"]
            if any(token in lowered for token in ("manquant", "missing", "complét")):
                text = (
                    f"Le dataset contient {summary['missing_count']} valeur(s) manquante(s), "
                    f"soit {summary['missing_rate']} % des cellules."
                )
            elif any(token in lowered for token in ("doublon", "duplicate")):
                text = (
                    f"L'audit a identifié {summary['duplicate_count']} doublon(s) ou "
                    f"identifiant(s) répété(s), soit {summary['duplicate_rate']} % des lignes."
                )
            elif any(token in lowered for token in ("anomal", "atyp", "isolation")):
                if anomalies.get("applicable", True):
                    text = (
                        f"Isolation Forest a signalé {anomalies['count']} ligne(s), soit "
                        f"{anomalies['rate']} % du dataset. Ces lignes doivent être validées par le métier."
                    )
                else:
                    text = (
                        "La détection d'anomalies n'est pas applicable : "
                        f"{anomalies.get('message', 'les données sont insuffisantes.')}"
                    )
            elif any(token in lowered for token in ("date", "invalide", "format")):
                text = (
                    f"L'audit a relevé {summary.get('invalid_date_count', 0)} date(s) "
                    f"invalide(s) et {summary.get('invalid_semantic_count', 0)} "
                    "valeur(s) non conformes au type sémantique inféré."
                )
            elif any(token in lowered for token in ("type", "schéma", "schema")):
                schema = ", ".join(
                    f"{column['column']} ({column.get('inferred_type') or column['dtype']})"
                    for column in quality["columns"][:12]
                )
                text = f"Types sémantiques détectés : {schema}."
            elif any(token in lowered for token in ("revenu", "revenue", "chiffre")):
                revenue_kpi = next(
                    (kpi for kpi in overview["kpis"] if kpi["id"] == "revenue"), None
                )
                text = (
                    f"Le revenu total calculé est {revenue_kpi['value']}."
                    if revenue_kpi
                    else "Le dataset actif ne contient pas de colonne revenue exploitable."
                )
            elif any(token in lowered for token in ("qualité", "quality", "score")):
                text = (
                    f"Le score Data Quality est de {quality['score']}/100. "
                    f"Priorité recommandée : {quality['recommendations'][0]}"
                )
            elif any(token in lowered for token in ("ligne", "colonne", "taille", "volume")):
                dataset = overview["dataset"]
                text = (
                    f"{dataset['name']} contient {dataset['rows']} lignes et "
                    f"{dataset['columns']} colonnes."
                )
            else:
                text = (
                    _fallback_summary(overview, quality, anomalies, None)
                    + " Vous pouvez préciser si vous souhaitez analyser la qualité, "
                    "les doublons, les valeurs manquantes, le revenu ou les anomalies."
                )
        return {
            "answer": text,
            "mode": mode,
            "provider": "openai" if mode == "openai" else "local-fallback",
            "suggestions": [
                "Quel est le score de qualité ?",
                "Combien de valeurs manquantes ?",
                "Quelles anomalies ont été détectées ?",
            ],
            "generated_at": _now(),
        }

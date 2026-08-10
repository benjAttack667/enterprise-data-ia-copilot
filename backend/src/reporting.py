"""Génération et sauvegarde de rapports Markdown ou HTML."""

from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any


def _markdown_report(
    overview: dict[str, Any], quality: dict[str, Any], anomalies: dict[str, Any]
) -> str:
    dataset = overview["dataset"]
    generated_at = datetime.now(timezone.utc).isoformat()
    kpi_lines = "\n".join(
        f"- **{kpi['label']}** : {kpi['value']}{kpi.get('unit', '')}"
        for kpi in overview["kpis"]
    )
    problem_lines = "\n".join(f"- {problem}" for problem in quality["problems"])
    recommendation_lines = "\n".join(
        f"- {recommendation}" for recommendation in quality["recommendations"]
    )
    anomaly_summary = (
        f"Isolation Forest a signalé **{anomalies['count']} ligne(s)**, soit\n"
        f"**{anomalies['rate']} %** du dataset. Une anomalie statistique doit être validée\n"
        "avant toute correction métier."
        if anomalies.get("applicable", True)
        else (
            "Détection non applicable à ce dataset : "
            f"{anomalies.get('message', 'données numériques insuffisantes.')}"
        )
    )
    return f"""# Rapport Data & IA — {dataset['name']}

Généré le : {generated_at}

## Périmètre

- Source : {dataset['source']}
- Contexte : {dataset['context']}
- Volume : {dataset['rows']} lignes × {dataset['columns']} colonnes

## Indicateurs clés

{kpi_lines}

## Synthèse

{overview['summary']}

## Data Quality

Score global : **{quality['score']}/100**

{problem_lines}

## Détection d'anomalies

{anomaly_summary}

## Recommandations

{recommendation_lines}
"""


def _html_report(
    overview: dict[str, Any], quality: dict[str, Any], anomalies: dict[str, Any]
) -> str:
    dataset = overview["dataset"]
    generated_at = datetime.now(timezone.utc).isoformat()
    kpis = "".join(
        "<article><span>{}</span><strong>{}{}</strong></article>".format(
            escape(str(kpi["label"])),
            escape(str(kpi["value"])),
            escape(str(kpi.get("unit", ""))),
        )
        for kpi in overview["kpis"]
    )
    problems = "".join(f"<li>{escape(problem)}</li>" for problem in quality["problems"])
    recommendations = "".join(
        f"<li>{escape(recommendation)}</li>" for recommendation in quality["recommendations"]
    )
    anomaly_summary = (
        f"Isolation Forest a signalé {anomalies['count']} ligne(s), soit "
        f"{anomalies['rate']} %. Ces observations doivent être validées par le métier."
        if anomalies.get("applicable", True)
        else (
            "Détection non applicable à ce dataset : "
            f"{anomalies.get('message', 'données numériques insuffisantes.')}"
        )
    )
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Rapport Data & IA — {escape(str(dataset['name']))}</title>
<style>
body{{font-family:Inter,Arial,sans-serif;max-width:1000px;margin:40px auto;padding:0 24px;color:#172033;background:#f7f8fb}}
h1,h2{{color:#111827}} .muted{{color:#64748b}} .grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}
article{{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:18px}} article span{{display:block;color:#64748b}}
article strong{{display:block;font-size:24px;margin-top:8px}} section{{background:white;padding:24px;border-radius:12px;margin-top:18px;border:1px solid #e2e8f0}}
@media(max-width:700px){{.grid{{grid-template-columns:1fr 1fr}}}}
</style></head><body>
<p class="muted">Enterprise Data & IA Copilot · {escape(generated_at)}</p>
<h1>Rapport — {escape(str(dataset['name']))}</h1>
<p>{dataset['rows']} lignes × {dataset['columns']} colonnes · {escape(str(dataset['context']))}</p>
<div class="grid">{kpis}</div>
<section><h2>Synthèse</h2><p>{escape(str(overview['summary']))}</p></section>
<section><h2>Data Quality — {quality['score']}/100</h2><ul>{problems}</ul></section>
<section><h2>Anomalies</h2><p>{escape(anomaly_summary)}</p></section>
<section><h2>Recommandations</h2><ul>{recommendations}</ul></section>
</body></html>"""


class ReportService:
    """Crée un rapport sur disque et renvoie exactement son contenu."""

    def __init__(self, reports_dir: Path, max_files: int = 20) -> None:
        self.reports_dir = reports_dir
        self.max_files = max_files
        self._lock = threading.RLock()
        self._filename_sequence = 0
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._cleanup_staged_reports()
            self._prune_reports()

    def _report_paths(self) -> list[Path]:
        return [
            path
            for pattern in ("data-report-*.md", "data-report-*.html")
            for path in self.reports_dir.glob(pattern)
            if path.is_file()
        ]

    def _cleanup_staged_reports(self) -> None:
        for path in self.reports_dir.glob(".report-*.part"):
            path.unlink(missing_ok=True)

    def _prune_reports(self, keep: Path | None = None) -> None:
        paths = sorted(
            self._report_paths(),
            # Filename is a deterministic tie-breaker on filesystems whose
            # timestamp resolution collapses several rapid generations.
            key=lambda path: (path.stat().st_mtime_ns, path.name),
            reverse=True,
        )
        keep_is_present = keep is not None and keep in paths
        candidates = [path for path in paths if path != keep]
        retained_candidate_count = self.max_files - int(keep_is_present)
        for path in candidates[retained_candidate_count:]:
            path.unlink(missing_ok=True)

    def generate(
        self,
        report_format: str,
        overview: dict[str, Any],
        quality: dict[str, Any],
        anomalies: dict[str, Any],
    ) -> dict[str, Any]:
        """Génère le format demandé, sans conversion ou fonctionnalité simulée."""

        created_at = datetime.now(timezone.utc)
        stamp = created_at.strftime("%Y%m%dT%H%M%S%fZ")
        if report_format == "markdown":
            extension = "md"
            content = _markdown_report(overview, quality, anomalies)
        elif report_format == "html":
            extension = "html"
            content = _html_report(overview, quality, anomalies)
        else:
            raise ValueError("Format de rapport non pris en charge.")
        with self._lock:
            # Windows clocks can return the same microsecond for rapid calls.
            # A locked sequence plus UUID prevents replacement and also gives
            # retention a stable order when filesystem mtimes are tied.
            self._filename_sequence += 1
            filename = (
                f"data-report-{stamp}-{self._filename_sequence:08d}-"
                f"{uuid.uuid4().hex}.{extension}"
            )
            path = self.reports_dir / filename
            staged_path = self.reports_dir / f".report-{uuid.uuid4().hex}.part"
            try:
                with staged_path.open(
                    "w", encoding="utf-8", newline="\n"
                ) as staged_file:
                    staged_file.write(content)
                os.replace(staged_path, path)
                try:
                    self._prune_reports(keep=path)
                except OSError as prune_error:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError as rollback_error:
                        raise rollback_error from prune_error
                    raise
            finally:
                try:
                    staged_path.unlink(missing_ok=True)
                except OSError:
                    pass
        return {
            "filename": filename,
            "format": report_format,
            "content": content,
            "created_at": created_at.isoformat(),
        }

    def storage_metrics(self) -> dict[str, int]:
        """Return aggregate retained usage without exposing report names."""

        with self._lock:
            paths = self._report_paths()
            return {
                "files": len(paths),
                "bytes": sum(path.stat().st_size for path in paths),
                "max_files": self.max_files,
            }

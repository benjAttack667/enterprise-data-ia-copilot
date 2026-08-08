"""API FastAPI de l'Enterprise Data & IA Copilot.

L'application expose uniquement des fonctionnalités reliées à des calculs
Pandas/scikit-learn, à SQLite ou à la génération réelle de fichiers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Body, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

try:  # Permet ``uvicorn backend.main:app`` depuis la racine.
    from .src.ai_service import AIService
    from .src.analytics import build_dashboard, build_overview
    from .src.anomalies import detect_anomalies
    from .src.config import Settings
    from .src.dataset_store import DatasetError, DatasetSnapshot, DatasetStore
    from .src.history import HistoryRepository
    from .src.models import AISummaryRequest, Aggregation, AskRequest, ReportRequest
    from .src.quality import audit_data_quality
    from .src.reporting import ReportService
except ImportError:  # Permet aussi ``uvicorn main:app`` depuis ``backend``.
    from src.ai_service import AIService
    from src.analytics import build_dashboard, build_overview
    from src.anomalies import detect_anomalies
    from src.config import Settings
    from src.dataset_store import DatasetError, DatasetSnapshot, DatasetStore
    from src.history import HistoryRepository
    from src.models import AISummaryRequest, Aggregation, AskRequest, ReportRequest
    from src.quality import audit_data_quality
    from src.reporting import ReportService


API_VERSION = "1.0.0"
ALLOWED_CONTENT_TYPES = {
    ".csv": {
        "text/csv",
        "application/csv",
        "application/vnd.ms-excel",
        "text/plain",
        "application/octet-stream",
    },
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
    },
}


def _active(request: Request) -> DatasetSnapshot:
    """Récupère une photographie immuable du dataset actif."""

    return request.app.state.dataset_store.get_active()


def _record(request: Request, action: str, snapshot: DatasetSnapshot, **details: object) -> None:
    """Centralise l'enregistrement des opérations terminées avec succès."""

    request.app.state.history.record(
        action=action,
        dataset_id=snapshot.id,
        dataset_name=snapshot.name,
        details=dict(details),
    )


def _analysis_bundle(snapshot: DatasetSnapshot) -> tuple[dict, dict, dict]:
    """Calcule le contexte partagé par l'IA et les rapports."""

    quality = audit_data_quality(snapshot.dataframe)
    anomalies = detect_anomalies(snapshot.dataframe)
    overview = build_overview(snapshot, quality=quality, anomalies=anomalies)
    return overview, quality, anomalies


def create_app(settings: Settings | None = None) -> FastAPI:
    """Fabrique l'application et permet d'injecter des chemins isolés en test."""

    active_settings = settings or Settings.from_env()
    active_settings.ensure_directories()
    application = FastAPI(
        title="Enterprise Data & IA Copilot API",
        version=API_VERSION,
        description=(
            "API d'analyse de données, Data Quality, détection d'anomalies, "
            "assistant IA avec fallback local et rapports exportables."
        ),
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    application.state.settings = active_settings
    application.state.dataset_store = DatasetStore(
        active_settings.samples_dir, active_settings.uploads_dir
    )
    application.state.history = HistoryRepository(active_settings.database_path)
    application.state.ai = AIService(
        active_settings.openai_api_key, active_settings.openai_model
    )
    application.state.reports = ReportService(active_settings.reports_dir)

    @application.get("/api/health", tags=["system"])
    def health(request: Request) -> dict[str, object]:
        """Confirme que l'API et son dataset par défaut sont disponibles."""

        snapshot = _active(request)
        return {
            "status": "ok",
            "version": API_VERSION,
            "dataset_id": snapshot.id,
            "dataset_name": snapshot.name,
        }

    @application.post("/api/upload", tags=["datasets"])
    async def upload_dataset(
        request: Request,
        file: Annotated[UploadFile, File(description="Fichier CSV ou XLSX")],
    ) -> dict[str, object]:
        """Valide, limite à 50 Mio par défaut, stocke et active un dataset."""

        filename = Path(file.filename or "").name
        suffix = Path(filename).suffix.lower()
        if not filename or suffix not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=415,
                detail="Format non pris en charge. Utilisez un fichier CSV ou XLSX.",
            )
        if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES[suffix]:
            raise HTTPException(status_code=415, detail="Type MIME incompatible avec l'extension.")

        chunks: list[bytes] = []
        total_size = 0
        try:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > request.app.state.settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="Fichier trop volumineux pour la limite configurée.",
                    )
                chunks.append(chunk)
        finally:
            await file.close()
        if total_size == 0:
            raise HTTPException(status_code=400, detail="Le fichier est vide.")
        try:
            snapshot = request.app.state.dataset_store.activate_upload(
                filename, b"".join(chunks)
            )
        except DatasetError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _record(request, "dataset_uploaded", snapshot, filename=filename, size=total_size)
        metadata = snapshot.metadata()
        return {
            "dataset": metadata,
            "dataset_id": metadata["id"],
            "name": metadata["name"],
            "rows": metadata["rows"],
            "columns": metadata["columns"],
            "updated_at": metadata["updated_at"],
            "message": "Dataset importé et activé avec succès.",
        }

    @application.get("/api/overview", tags=["analytics"])
    def overview(request: Request) -> dict[str, object]:
        """Retourne les KPI et séries de la vue d'ensemble."""

        snapshot = _active(request)
        payload = build_overview(snapshot)
        _record(request, "overview_analyzed", snapshot, quality_score=payload["quality_score"])
        return payload

    @application.get("/api/data-quality", tags=["analytics"])
    def data_quality(request: Request) -> dict[str, object]:
        """Exécute l'audit Data Quality détaillé du dataset actif."""

        snapshot = _active(request)
        payload = audit_data_quality(snapshot.dataframe)
        _record(
            request,
            "data_quality_analyzed",
            snapshot,
            score=payload["score"],
            problems=len(payload["problems"]),
        )
        return payload

    @application.get("/api/dashboard", tags=["analytics"])
    def dashboard(
        request: Request,
        dimension: str | None = Query(default=None, max_length=200),
        metric: str | None = Query(default=None, max_length=200),
        aggregation: Aggregation | None = Query(default=None),
    ) -> dict[str, object]:
        """Agrège une métrique par dimension pour les graphiques Recharts."""

        snapshot = _active(request)
        try:
            payload = build_dashboard(
                snapshot.dataframe,
                dimension=dimension,
                metric=metric,
                aggregation=aggregation,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _record(
            request,
            "dashboard_analyzed",
            snapshot,
            dimension=payload["dimension"],
            metric=payload["metric"],
            aggregation=payload["aggregation"],
        )
        return payload

    @application.post("/api/ai-summary", tags=["ai"])
    def ai_summary(
        request: Request,
        payload: Annotated[AISummaryRequest | None, Body()] = None,
    ) -> dict[str, object]:
        """Génère une synthèse OpenAI ou locale à partir des agrégats."""

        snapshot = _active(request)
        overview_data, quality, anomalies = _analysis_bundle(snapshot)
        result = request.app.state.ai.summary(
            overview_data,
            quality,
            anomalies,
            focus=payload.focus if payload else None,
        )
        _record(request, "ai_summary_generated", snapshot, mode=result["mode"])
        return result

    @application.post("/api/ask", tags=["ai"])
    def ask_assistant(request: Request, payload: AskRequest) -> dict[str, object]:
        """Répond à une question sur les indicateurs calculés du dataset actif."""

        snapshot = _active(request)
        overview_data, quality, anomalies = _analysis_bundle(snapshot)
        result = request.app.state.ai.ask(
            payload.question, overview_data, quality, anomalies
        )
        _record(request, "assistant_question_answered", snapshot, mode=result["mode"])
        return result

    @application.get("/api/anomalies", tags=["analytics"])
    def anomalies(request: Request) -> dict[str, object]:
        """Retourne les lignes atypiques réellement prédites par Isolation Forest."""

        snapshot = _active(request)
        payload = detect_anomalies(snapshot.dataframe)
        _record(request, "anomalies_analyzed", snapshot, count=payload["count"])
        return payload

    @application.post("/api/report", tags=["reports"])
    def create_report(
        request: Request,
        payload: Annotated[ReportRequest | None, Body()] = None,
    ) -> dict[str, object]:
        """Génère et sauvegarde un rapport Markdown (défaut) ou HTML."""

        snapshot = _active(request)
        overview_data, quality, anomalies = _analysis_bundle(snapshot)
        report_format = payload.format if payload else "markdown"
        result = request.app.state.reports.generate(
            report_format, overview_data, quality, anomalies
        )
        _record(
            request,
            "report_generated",
            snapshot,
            filename=result["filename"],
            format=result["format"],
        )
        return result

    @application.get("/api/history", tags=["history"])
    def history(
        request: Request,
        limit: int = Query(default=100, ge=1, le=200),
    ) -> dict[str, object]:
        """Liste l'historique SQLite sans créer lui-même un nouvel événement."""

        return {"items": request.app.state.history.list_recent(limit)}

    return application


app = create_app()

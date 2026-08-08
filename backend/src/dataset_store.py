"""Chargement sécurisé et gestion du dataset actif."""

from __future__ import annotations

import csv
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd


class DatasetError(ValueError):
    """Erreur de validation ou de lecture d'un dataset."""


@dataclass(frozen=True)
class DatasetSnapshot:
    """Copie cohérente du dataset et de ses métadonnées."""

    id: str
    name: str
    source: str
    updated_at: str
    context: str
    dataframe: pd.DataFrame

    def metadata(self) -> dict[str, object]:
        """Expose les métadonnées attendues par le frontend."""

        rows, columns = self.dataframe.shape
        return {
            "id": self.id,
            "name": self.name,
            "rows": int(rows),
            "columns": int(columns),
            "source": self.source,
            "updated_at": self.updated_at,
            "context": self.context,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _display_name(filename: str) -> str:
    stem = Path(filename).stem
    words = re.sub(r"[_-]+", " ", stem).strip()
    return words.title() or "Dataset importé"


def _infer_context(filename: str, columns: list[str]) -> str:
    """Déduit un contexte lisible sans prétendre connaître le métier du client."""

    tokens = " ".join([filename, *columns]).lower()
    if any(token in tokens for token in ("lead", "campaign", "conversion", "revenue")):
        return "Marketing & Sales"
    if any(token in tokens for token in ("supplier", "compliance", "recycl", "packaging")):
        return "Supply Chain & ESG"
    if any(token in tokens for token in ("project", "innovation", "progress", "roi")):
        return "Innovation & PMO"
    if any(token in tokens for token in ("forecast", "margin", "actual", "finance")):
        return "Finance & Performance"
    return "Analyse de données"


def _validate_raw_headers(filename: str, content: bytes) -> None:
    """Contrôle les en-têtes avant que Pandas ne renomme les doublons.

    ``read_csv`` et ``read_excel`` rendent par défaut les noms dupliqués
    artificiellement uniques (par exemple ``name.1``). Le contrôle doit donc
    lire la première ligne directement depuis le format source.
    """

    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        headers = next(csv.reader(StringIO(text)), [])
    elif suffix == ".xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        try:
            headers = list(
                next(
                    workbook.active.iter_rows(min_row=1, max_row=1, values_only=True),
                    (),
                )
            )
        finally:
            workbook.close()
    else:
        return

    normalized = ["" if value is None else str(value).strip() for value in headers]
    if not normalized or any(not value for value in normalized):
        raise DatasetError("Chaque colonne doit avoir un nom non vide.")
    if len(normalized) != len(set(normalized)):
        raise DatasetError("Le fichier contient des noms de colonnes dupliqués.")


def _read_dataframe(filename: str, content: bytes) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    stream = BytesIO(content)
    try:
        _validate_raw_headers(filename, content)
        if suffix == ".csv":
            try:
                dataframe = pd.read_csv(stream)
            except UnicodeDecodeError:
                stream.seek(0)
                dataframe = pd.read_csv(stream, encoding="latin-1")
        elif suffix == ".xlsx":
            dataframe = pd.read_excel(stream, engine="openpyxl")
        else:
            raise DatasetError("Format non pris en charge. Utilisez un fichier CSV ou XLSX.")
    except DatasetError:
        raise
    except Exception as exc:  # Pandas remonte plusieurs familles d'erreurs de parse.
        raise DatasetError(f"Le fichier ne peut pas être lu : {exc}") from exc

    if dataframe.empty or dataframe.shape[1] == 0:
        raise DatasetError("Le fichier ne contient aucune donnée exploitable.")
    dataframe.columns = [str(column).strip() for column in dataframe.columns]
    if any(not column for column in dataframe.columns):
        raise DatasetError("Chaque colonne doit avoir un nom non vide.")
    if dataframe.columns.duplicated().any():
        raise DatasetError("Le fichier contient des noms de colonnes dupliqués.")
    return dataframe


class DatasetStore:
    """Conserve un dataset actif et renvoie toujours des copies en lecture."""

    def __init__(self, samples_dir: Path, uploads_dir: Path) -> None:
        self.samples_dir = samples_dir
        self.uploads_dir = uploads_dir
        self._lock = threading.RLock()
        self._active = self._load_default()

    def _load_default(self) -> DatasetSnapshot:
        default_path = self.samples_dir / "marketing_leads.csv"
        if not default_path.is_file():
            raise RuntimeError(f"Dataset de démonstration absent : {default_path}")
        content = default_path.read_bytes()
        dataframe = _read_dataframe(default_path.name, content)
        updated_at = datetime.fromtimestamp(
            default_path.stat().st_mtime, tz=timezone.utc
        ).isoformat()
        return DatasetSnapshot(
            id="marketing-leads",
            name="Marketing Leads",
            source="sample",
            updated_at=updated_at,
            context="Marketing & Sales",
            dataframe=dataframe,
        )

    def get_active(self) -> DatasetSnapshot:
        """Retourne une copie, empêchant un endpoint de modifier l'état partagé."""

        with self._lock:
            active = self._active
            return DatasetSnapshot(
                id=active.id,
                name=active.name,
                source=active.source,
                updated_at=active.updated_at,
                context=active.context,
                dataframe=active.dataframe.copy(deep=True),
            )

    def activate_upload(self, filename: str, content: bytes) -> DatasetSnapshot:
        """Valide, sauvegarde puis active un CSV/XLSX.

        La sauvegarde n'a lieu qu'après un parsing réussi, ce qui évite de garder
        des fichiers invalides dans ``data/uploads``.
        """

        safe_original_name = Path(filename).name
        suffix = Path(safe_original_name).suffix.lower()
        if suffix not in {".csv", ".xlsx"}:
            raise DatasetError("Format non pris en charge. Utilisez un fichier CSV ou XLSX.")
        dataframe = _read_dataframe(safe_original_name, content)
        dataset_id = uuid.uuid4().hex
        stored_name = f"{dataset_id}{suffix}"
        stored_path = (self.uploads_dir / stored_name).resolve()
        uploads_root = self.uploads_dir.resolve()
        if uploads_root not in stored_path.parents:
            raise DatasetError("Nom de fichier invalide.")
        stored_path.write_bytes(content)

        snapshot = DatasetSnapshot(
            id=dataset_id,
            name=_display_name(safe_original_name),
            source="upload",
            updated_at=_utc_now(),
            context=_infer_context(safe_original_name, list(dataframe.columns)),
            dataframe=dataframe,
        )
        with self._lock:
            self._active = snapshot
        return self.get_active()

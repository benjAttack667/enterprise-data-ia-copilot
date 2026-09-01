"""Chargement sécurisé et gestion du dataset actif."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import threading
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import pandas as pd


logger = logging.getLogger(__name__)

_ACTIVE_MANIFEST_NAME = ".active-dataset.json"
_ACTIVE_MANIFEST_VERSION = 1
_FALLBACK_MESSAGE = (
    "Le dataset persistant n'a pas pu être restauré. "
    "L'échantillon de démonstration est actif."
)
_CLEANUP_WARNING_MESSAGE = (
    "Le dataset actif a été restauré, mais le nettoyage du stockage reste incomplet."
)
_DATASET_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class DatasetError(ValueError):
    """Erreur de validation ou de lecture d'un dataset."""


class WorkbookSheetError(DatasetError):
    """Actionable workbook error that safely exposes sheet names only."""

    def __init__(
        self,
        message: str,
        *,
        code: Literal["sheet_selection_required", "invalid_sheet_name"],
        sheets: list[str],
    ) -> None:
        super().__init__(message)
        self.code = code
        self.sheets = tuple(sheets)


@dataclass(frozen=True)
class DatasetLimits:
    """Resource limits applied before a dataframe becomes active."""

    max_file_bytes: int = 10 * 1024 * 1024
    max_rows: int = 100_000
    max_columns: int = 200
    max_cells: int = 2_000_000
    max_xlsx_uncompressed_bytes: int = 50 * 1024 * 1024
    max_xlsx_compression_ratio: float = 100.0
    max_xlsx_entries: int = 1_000


@dataclass(frozen=True)
class DatasetSnapshot:
    """Copie cohérente du dataset et de ses métadonnées."""

    id: str
    name: str
    source: str
    updated_at: str
    context: str
    dataframe: pd.DataFrame
    selected_sheet: str | None = None
    available_sheets: tuple[str, ...] = ()

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
            "selected_sheet": self.selected_sheet,
            "available_sheets": list(self.available_sheets),
        }


@dataclass(frozen=True)
class _CSVLayout:
    """Encoding and separator selected once for validation and Pandas."""

    encoding: str
    delimiter: str
    headers: list[str]
    rows: int


@dataclass(frozen=True)
class _ParsedDataset:
    """A dataframe plus non-sensitive ingestion metadata."""

    dataframe: pd.DataFrame
    selected_sheet: str | None = None
    available_sheets: tuple[str, ...] = ()


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


def _validate_headers(headers: list[object]) -> list[str]:
    """Reject empty/duplicate headers before Pandas can silently rename them."""

    normalized = ["" if value is None else str(value).strip() for value in headers]
    if not normalized or any(not value for value in normalized):
        raise DatasetError("Chaque colonne doit avoir un nom non vide.")
    if len(normalized) != len(set(normalized)):
        raise DatasetError("Le fichier contient des noms de colonnes dupliqués.")
    return normalized


_CSV_DELIMITERS = (",", ";", "\t")


def _csv_encoding(path: Path) -> str:
    """Select one supported encoding before delimiter inspection."""

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            while stream.read(64 * 1024):
                pass
        return "utf-8-sig"
    except UnicodeDecodeError:
        # Latin-1 maps every byte deterministically and preserves support for
        # exports from older spreadsheet applications.
        return "latin-1"


def _inspect_csv_candidate(
    path: Path,
    *,
    encoding: str,
    delimiter: str,
) -> tuple[list[str], int, bool]:
    """Return header, data-row count and structural consistency."""

    try:
        with path.open("r", encoding=encoding, newline="") as stream:
            reader = csv.reader(stream, delimiter=delimiter, strict=True)
            records = (row for row in reader if row)
            headers = list(next(records, []))
            row_count = 0
            consistent = bool(headers)
            expected_width = len(headers)
            for row in records:
                row_count += 1
                if len(row) != expected_width:
                    consistent = False
            return headers, row_count, consistent
    except (csv.Error, UnicodeDecodeError) as exc:
        raise DatasetError(
            "Structure CSV incohérente : chaque ligne doit utiliser le même "
            "séparateur et contenir le même nombre de colonnes."
        ) from exc


def _detect_csv_layout(path: Path) -> _CSVLayout:
    """Detect comma, semicolon or tab deterministically and only once.

    A candidate must produce a constant number of columns for every logical
    CSV record. More than one multi-column candidate is rejected instead of
    silently guessing and corrupting the imported schema.
    """

    encoding = _csv_encoding(path)
    inspections: dict[str, tuple[list[str], int, bool]] = {}
    parse_error: DatasetError | None = None
    for delimiter in _CSV_DELIMITERS:
        try:
            inspections[delimiter] = _inspect_csv_candidate(
                path,
                encoding=encoding,
                delimiter=delimiter,
            )
        except DatasetError as exc:
            parse_error = exc
            inspections[delimiter] = ([], 0, False)

    multi_column = [
        delimiter
        for delimiter, (headers, _rows, consistent) in inspections.items()
        if consistent and len(headers) > 1
    ]
    if len(multi_column) > 1:
        raise DatasetError(
            "Séparateur CSV ambigu : utilisez un seul séparateur parmi virgule, "
            "point-virgule ou tabulation."
        )
    if len(multi_column) == 1:
        delimiter = multi_column[0]
    else:
        # A delimiter-free file is a valid single-column CSV. If any candidate
        # changes width between records, however, the source is malformed.
        single_column = [
            delimiter
            for delimiter, (headers, _rows, consistent) in inspections.items()
            if consistent and len(headers) == 1
        ]
        if len(single_column) != len(_CSV_DELIMITERS):
            if parse_error is not None:
                raise parse_error
            raise DatasetError(
                "Structure CSV incohérente : chaque ligne doit utiliser le même "
                "séparateur et contenir le même nombre de colonnes."
            )
        delimiter = ","

    headers, rows, _consistent = inspections[delimiter]
    return _CSVLayout(
        encoding=encoding,
        delimiter=delimiter,
        headers=_validate_headers(headers),
        rows=rows,
    )


def _validate_xlsx_archive(path: Path, limits: DatasetLimits) -> None:
    """Reject malformed, encrypted or disproportionately expanded XLSX files."""

    if not zipfile.is_zipfile(path):
        raise DatasetError("Le fichier XLSX n'est pas une archive Excel valide.")
    archive_size = max(path.stat().st_size, 1)
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > limits.max_xlsx_entries:
                raise DatasetError(
                    "Le fichier XLSX contient trop d'éléments internes."
                )
            if any(member.flag_bits & 0x1 for member in members):
                raise DatasetError("Les fichiers XLSX chiffrés ne sont pas acceptés.")
            uncompressed_size = sum(member.file_size for member in members)
    except DatasetError:
        raise
    except OSError:
        raise
    except zipfile.BadZipFile as exc:
        raise DatasetError("Le fichier XLSX n'est pas une archive valide.") from exc

    if uncompressed_size > limits.max_xlsx_uncompressed_bytes:
        raise DatasetError("Le contenu XLSX décompressé dépasse la limite configurée.")
    if uncompressed_size / archive_size > limits.max_xlsx_compression_ratio:
        raise DatasetError("Le taux de compression du fichier XLSX est trop élevé.")


def _normalise_sheet_name(sheet_name: str | None) -> str | None:
    """Validate an optional worksheet name before workbook lookup."""

    if sheet_name is None:
        return None
    if not sheet_name.strip():
        raise DatasetError("Le nom de feuille ne peut pas être vide.")
    if len(sheet_name) > 128:
        raise DatasetError("Le nom de feuille dépasse la limite de 128 caractères.")
    if not sheet_name.isprintable():
        raise DatasetError("Le nom de feuille contient des caractères non autorisés.")
    # Preserve the exact title: Excel permits leading/trailing spaces and the
    # client receives the canonical names directly from this API.
    return sheet_name


def _xlsx_shape_and_headers(
    path: Path,
    limits: DatasetLimits,
    sheet_name: str | None = None,
) -> tuple[int, int, list[str], str, tuple[str, ...]]:
    """Inspect worksheet dimensions in read-only mode before Pandas parsing."""

    from openpyxl import load_workbook

    _validate_xlsx_archive(path, limits)
    try:
        with path.open("rb") as binary_stream:
            workbook = load_workbook(
                binary_stream,
                read_only=True,
                data_only=True,
                keep_links=False,
            )
            try:
                # Hidden worksheets are intentionally selectable. Hiding a
                # sheet is a presentation preference, not an access-control
                # boundary, and the workbook was supplied by the caller.
                # Chart sheets are excluded because they contain no tabular
                # cells and cannot be consumed by Pandas as a worksheet.
                sheets = [worksheet.title for worksheet in workbook.worksheets]
                if not sheets:
                    raise DatasetError(
                        "Le classeur XLSX ne contient aucune feuille de données."
                    )
                requested_sheet = _normalise_sheet_name(sheet_name)
                if requested_sheet is None and len(sheets) > 1:
                    raise WorkbookSheetError(
                        "Ce classeur contient plusieurs feuilles. Sélectionnez "
                        "la feuille à analyser.",
                        code="sheet_selection_required",
                        sheets=sheets,
                    )
                selected_sheet = requested_sheet or sheets[0]
                if selected_sheet not in sheets:
                    raise WorkbookSheetError(
                        f"La feuille « {selected_sheet} » est introuvable.",
                        code="invalid_sheet_name",
                        sheets=sheets,
                    )
                worksheet = workbook[selected_sheet]
                row_count = max(int(worksheet.max_row or 0) - 1, 0)
                column_count = int(worksheet.max_column or 0)
                headers = _validate_headers(
                    list(
                        next(
                            worksheet.iter_rows(
                                min_row=1,
                                max_row=1,
                                values_only=True,
                            ),
                            (),
                        )
                    )
                )
            finally:
                workbook.close()
    except DatasetError:
        raise
    except OSError:
        raise
    except Exception as exc:
        raise DatasetError("Le fichier XLSX ne peut pas être inspecté.") from exc
    return row_count, column_count, headers, selected_sheet, tuple(sheets)


def _validate_shape(rows: int, columns: int, limits: DatasetLimits) -> None:
    """Enforce bounded dataframe dimensions with stable public errors."""

    if columns > limits.max_columns:
        raise DatasetError(
            f"Le dataset dépasse la limite de {limits.max_columns} colonnes."
        )
    if rows > limits.max_rows:
        raise DatasetError(
            f"Le dataset dépasse la limite de {limits.max_rows} lignes."
        )
    if rows * columns > limits.max_cells:
        raise DatasetError(
            f"Le dataset dépasse la limite de {limits.max_cells} cellules."
        )


def _read_dataframe_path(
    filename: str,
    path: Path,
    limits: DatasetLimits,
    sheet_name: str | None = None,
) -> _ParsedDataset:
    """Contrôle les en-têtes avant que Pandas ne renomme les doublons.

    ``read_csv`` et ``read_excel`` rendent par défaut les noms dupliqués
    artificiellement uniques (par exemple ``name.1``). Le contrôle doit donc
    lire la première ligne directement depuis le format source.
    """

    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".csv":
            if sheet_name is not None:
                raise DatasetError(
                    "Le paramètre sheet_name est réservé aux fichiers XLSX."
                )
            layout = _detect_csv_layout(path)
            _validate_shape(layout.rows, len(layout.headers), limits)
            max_rows_by_cells = limits.max_cells // len(layout.headers)
            read_limit = min(limits.max_rows, max_rows_by_cells)
            dataframe = pd.read_csv(
                path,
                encoding=layout.encoding,
                sep=layout.delimiter,
                nrows=read_limit + 1,
                # Les libellés métier comme "NA" ou "NULL" doivent rester
                # des valeurs brutes. Le profilage sémantique normalise
                # ensuite uniquement les cellules vides ou composées
                # d'espaces, de façon identique dans toutes les analyses.
                keep_default_na=False,
            )
            selected_sheet = None
            available_sheets: tuple[str, ...] = ()
        elif suffix == ".xlsx":
            rows, columns, _headers, selected_sheet, available_sheets = (
                _xlsx_shape_and_headers(path, limits, sheet_name)
            )
            _validate_shape(rows, columns, limits)
            with path.open("rb") as binary_stream:
                dataframe = pd.read_excel(
                    binary_stream,
                    engine="openpyxl",
                    sheet_name=selected_sheet,
                    nrows=limits.max_rows + 1,
                    keep_default_na=False,
                )
        else:
            raise DatasetError("Format non pris en charge. Utilisez un fichier CSV ou XLSX.")
    except DatasetError:
        raise
    except OSError:
        raise
    except Exception as exc:  # Pandas remonte plusieurs familles d'erreurs de parse.
        raise DatasetError(f"Le fichier ne peut pas être lu : {exc}") from exc

    if dataframe.empty or dataframe.shape[1] == 0:
        raise DatasetError("Le fichier ne contient aucune donnée exploitable.")
    _validate_shape(int(dataframe.shape[0]), int(dataframe.shape[1]), limits)
    dataframe.columns = [str(column).strip() for column in dataframe.columns]
    if any(not column for column in dataframe.columns):
        raise DatasetError("Chaque colonne doit avoir un nom non vide.")
    if dataframe.columns.duplicated().any():
        raise DatasetError("Le fichier contient des noms de colonnes dupliqués.")
    return _ParsedDataset(
        dataframe=dataframe,
        selected_sheet=selected_sheet,
        available_sheets=available_sheets,
    )


class DatasetStore:
    """Conserve un dataset actif et renvoie toujours des copies en lecture."""

    def __init__(
        self,
        samples_dir: Path,
        uploads_dir: Path,
        limits: DatasetLimits | None = None,
    ) -> None:
        self.samples_dir = samples_dir
        self.uploads_dir = uploads_dir
        self.limits = limits or DatasetLimits()
        self._lock = threading.RLock()
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self._manifest_path = self.uploads_dir / _ACTIVE_MANIFEST_NAME
        self._active_stored_path: Path | None = None
        self._active_manifest_payload: dict[str, object] | None = None
        self._recovery_status: Literal["sample", "active", "restored", "fallback"] = (
            "sample"
        )
        self._recovery_message: str | None = None
        self._cleanup_staged_uploads()
        self._cleanup_staged_manifests()
        self._initialize_active_dataset()

    def _initialize_active_dataset(self) -> None:
        """Restore the durable pointer before deleting any retained upload."""

        final_uploads = self._final_upload_paths()
        manifest_present = self._manifest_path.exists() or self._manifest_path.is_symlink()
        if manifest_present and self._manifest_path.is_file():
            try:
                snapshot, stored_path, payload = self._restore_manifest()
            except (DatasetError, OSError, ValueError, TypeError):
                logger.warning(
                    "Persistent dataset restoration failed; using the bundled sample.",
                    exc_info=True,
                )
            else:
                self._active = snapshot
                self._active_stored_path = stored_path
                self._active_manifest_payload = payload
                self._recovery_status = "restored"
                self._recovery_message = None
                try:
                    self._prune_final_uploads(keep=stored_path)
                except OSError:
                    logger.warning(
                        "Persistent dataset restored but orphan cleanup failed."
                    )
                    self._recovery_message = _CLEANUP_WARNING_MESSAGE
                return

        fallback_required = manifest_present or bool(final_uploads)
        self._active = self._load_default()
        self._active_stored_path = None
        self._active_manifest_payload = None
        self._recovery_status = "fallback" if fallback_required else "sample"
        self._recovery_message = _FALLBACK_MESSAGE if fallback_required else None
        if fallback_required:
            logger.warning(
                "Persistent dataset state is incomplete; using the bundled sample."
            )
        self._discard_manifest()
        try:
            self._prune_final_uploads(keep=None)
        except OSError:
            # Availability wins during recovery. Future uploads retry orphan
            # cleanup before committing a new durable pointer.
            logger.warning("Persistent dataset orphan cleanup failed.")

    def _load_default(self) -> DatasetSnapshot:
        default_path = self.samples_dir / "marketing_leads.csv"
        if not default_path.is_file():
            raise RuntimeError(f"Dataset de démonstration absent : {default_path}")
        parsed = _read_dataframe_path(default_path.name, default_path, self.limits)
        dataframe = parsed.dataframe
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

    def _final_upload_paths(self) -> list[Path]:
        return [
            path
            for pattern in ("*.csv", "*.xlsx")
            for path in self.uploads_dir.glob(pattern)
            if path.is_file()
        ]

    def _cleanup_staged_uploads(self) -> None:
        """Remove interrupted uploads left by a stopped process."""

        for path in self.uploads_dir.glob(".upload-*.part"):
            path.unlink(missing_ok=True)

    def _cleanup_staged_manifests(self) -> None:
        """Remove manifests that were never atomically published."""

        for path in self.uploads_dir.glob(".active-dataset-*.tmp"):
            path.unlink(missing_ok=True)

    def _prune_final_uploads(self, keep: Path | None = None) -> None:
        """Delete every immutable upload except the durable active target."""

        paths = self._final_upload_paths()
        resolved_keep = keep.resolve() if keep is not None else None
        for path in paths:
            if resolved_keep is not None and path.resolve() == resolved_keep:
                continue
            path.unlink(missing_ok=True)

    @staticmethod
    def _best_effort_fsync_file(path: Path) -> None:
        """Request crash durability where the host filesystem supports it."""

        try:
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
        except OSError:
            # Some Windows/filesystem combinations do not support fsync for
            # every file type. Atomic replacement still remains available.
            pass

    @staticmethod
    def _best_effort_fsync_directory(path: Path) -> None:
        """Persist directory entries on POSIX without breaking Windows."""

        if os.name == "nt":
            return
        descriptor: int | None = None
        try:
            descriptor = os.open(path, os.O_RDONLY)
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            if descriptor is not None:
                os.close(descriptor)

    @staticmethod
    def _sha256_path(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _discard_manifest(self) -> None:
        try:
            self._manifest_path.unlink(missing_ok=True)
        except OSError:
            return
        self._best_effort_fsync_directory(self.uploads_dir)

    @staticmethod
    def _manifest_text(
        payload: dict[str, object],
        key: str,
        *,
        max_length: int = 512,
    ) -> str:
        value = payload.get(key)
        if (
            not isinstance(value, str)
            or not value
            or len(value) > max_length
            or not value.isprintable()
        ):
            raise DatasetError("Le manifeste du dataset actif est invalide.")
        return value

    def _validate_manifest_payload(self, raw_payload: object) -> dict[str, object]:
        """Validate an untrusted on-volume manifest without reading its dataset."""

        expected_keys = {
            "version",
            "dataset_id",
            "stored_filename",
            "original_filename",
            "name",
            "context",
            "updated_at",
            "selected_sheet",
            "available_sheets",
            "rows",
            "columns",
            "size_bytes",
            "sha256",
        }
        if not isinstance(raw_payload, dict) or set(raw_payload) != expected_keys:
            raise DatasetError("Le manifeste du dataset actif est invalide.")
        payload = dict(raw_payload)
        version = payload.get("version")
        if type(version) is not int or version != _ACTIVE_MANIFEST_VERSION:
            raise DatasetError("Version de manifeste non prise en charge.")

        dataset_id = self._manifest_text(payload, "dataset_id", max_length=32)
        if _DATASET_ID_PATTERN.fullmatch(dataset_id) is None:
            raise DatasetError("Identifiant de dataset persistant invalide.")

        stored_filename = self._manifest_text(
            payload, "stored_filename", max_length=64
        )
        stored_match = re.fullmatch(r"([0-9a-f]{32})(\.(?:csv|xlsx))", stored_filename)
        if stored_match is None or stored_match.group(1) != dataset_id:
            raise DatasetError("Nom de dataset persistant invalide.")

        original_filename = self._manifest_text(
            payload, "original_filename", max_length=512
        )
        if (
            Path(original_filename).name != original_filename
            or "/" in original_filename
            or "\\" in original_filename
            or Path(original_filename).suffix.lower() != stored_match.group(2)
        ):
            raise DatasetError("Nom de fichier source persistant invalide.")
        self._manifest_text(payload, "name")
        self._manifest_text(payload, "context")

        updated_at = self._manifest_text(payload, "updated_at", max_length=64)
        try:
            parsed_timestamp = datetime.fromisoformat(updated_at)
        except ValueError as exc:
            raise DatasetError("Horodatage persistant invalide.") from exc
        if (
            parsed_timestamp.tzinfo is None
            or parsed_timestamp.utcoffset() != timedelta(0)
        ):
            raise DatasetError("L'horodatage persistant doit être en UTC.")

        selected_sheet_raw = payload.get("selected_sheet")
        if selected_sheet_raw is not None and not isinstance(selected_sheet_raw, str):
            raise DatasetError("Feuille persistante invalide.")
        selected_sheet = _normalise_sheet_name(selected_sheet_raw)
        available_sheets_raw = payload.get("available_sheets")
        if not isinstance(available_sheets_raw, list):
            raise DatasetError("Liste de feuilles persistante invalide.")
        if len(available_sheets_raw) > self.limits.max_xlsx_entries:
            raise DatasetError("Liste de feuilles persistante trop volumineuse.")
        available_sheets: list[str] = []
        for sheet in available_sheets_raw:
            if not isinstance(sheet, str):
                raise DatasetError("Liste de feuilles persistante invalide.")
            normalized_sheet = _normalise_sheet_name(sheet)
            if normalized_sheet is None:
                raise DatasetError("Liste de feuilles persistante invalide.")
            available_sheets.append(normalized_sheet)
        if len(available_sheets) != len(set(available_sheets)):
            raise DatasetError("Liste de feuilles persistante invalide.")

        suffix = stored_match.group(2)
        if suffix == ".csv":
            if selected_sheet is not None or available_sheets:
                raise DatasetError("Métadonnées de feuilles incompatibles avec le CSV.")
        elif (
            selected_sheet is None
            or not available_sheets
            or selected_sheet not in available_sheets
        ):
            raise DatasetError("Métadonnées de feuilles XLSX invalides.")

        dimensions: dict[str, int] = {}
        for key in ("rows", "columns", "size_bytes"):
            value = payload.get(key)
            if type(value) is not int or value <= 0:
                raise DatasetError("Dimensions persistantes invalides.")
            dimensions[key] = value
        _validate_shape(dimensions["rows"], dimensions["columns"], self.limits)
        if dimensions["size_bytes"] > self.limits.max_file_bytes:
            raise DatasetError("Le fichier persistant dépasse la limite configurée.")

        sha256 = self._manifest_text(payload, "sha256", max_length=64)
        if _SHA256_PATTERN.fullmatch(sha256) is None:
            raise DatasetError("Empreinte persistante invalide.")
        return payload

    def _restore_manifest(
        self,
    ) -> tuple[DatasetSnapshot, Path, dict[str, object]]:
        """Verify the durable manifest and rebuild the exact active snapshot."""

        if self._manifest_path.is_symlink():
            raise DatasetError("Le manifeste du dataset actif est invalide.")
        if self._manifest_path.stat().st_size > 64 * 1024:
            raise DatasetError("Le manifeste du dataset actif est trop volumineux.")
        try:
            raw_payload = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise DatasetError("Le manifeste du dataset actif est illisible.") from exc
        payload = self._validate_manifest_payload(raw_payload)

        stored_filename = str(payload["stored_filename"])
        stored_candidate = self.uploads_dir / stored_filename
        if stored_candidate.is_symlink():
            raise DatasetError("Chemin de dataset persistant invalide.")
        stored_path = stored_candidate.resolve()
        uploads_root = self.uploads_dir.resolve()
        if uploads_root not in stored_path.parents:
            raise DatasetError("Chemin de dataset persistant invalide.")
        if not stored_path.is_file():
            raise DatasetError("Le fichier du dataset actif est absent.")

        # Bound the raw file before hashing or invoking a parser. The volume is
        # untrusted startup input and may have been altered out-of-process.
        actual_size = stored_path.stat().st_size
        if actual_size > self.limits.max_file_bytes:
            raise DatasetError("Le fichier persistant dépasse la limite configurée.")
        if actual_size != payload["size_bytes"]:
            raise DatasetError("La taille du dataset persistant a changé.")
        if self._sha256_path(stored_path) != payload["sha256"]:
            raise DatasetError("L'empreinte du dataset persistant a changé.")

        parsed = _read_dataframe_path(
            str(payload["original_filename"]),
            stored_path,
            self.limits,
            (
                payload["selected_sheet"]
                if isinstance(payload["selected_sheet"], str)
                else None
            ),
        )
        rows, columns = parsed.dataframe.shape
        if rows != payload["rows"] or columns != payload["columns"]:
            raise DatasetError("Les dimensions du dataset persistant ont changé.")
        if list(parsed.available_sheets) != payload["available_sheets"]:
            raise DatasetError("La liste des feuilles du dataset persistant a changé.")
        if parsed.selected_sheet != payload["selected_sheet"]:
            raise DatasetError("La feuille active du dataset persistant a changé.")

        original_filename = str(payload["original_filename"])
        if payload["name"] != _display_name(original_filename):
            raise DatasetError("Le nom du dataset persistant a changé.")
        if payload["context"] != _infer_context(
            original_filename,
            list(parsed.dataframe.columns),
        ):
            raise DatasetError("Le contexte du dataset persistant a changé.")

        snapshot = DatasetSnapshot(
            id=str(payload["dataset_id"]),
            name=str(payload["name"]),
            source="upload",
            updated_at=str(payload["updated_at"]),
            context=str(payload["context"]),
            dataframe=parsed.dataframe,
            selected_sheet=parsed.selected_sheet,
            available_sheets=parsed.available_sheets,
        )
        return snapshot, stored_path, payload

    def _write_manifest_atomically(self, payload: dict[str, object]) -> None:
        """Publish one private, versioned manifest through same-volume replace."""

        validated_payload = self._validate_manifest_payload(payload)
        encoded = (
            json.dumps(
                validated_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        if len(encoded) > 64 * 1024:
            raise DatasetError("Le manifeste du dataset actif est trop volumineux.")
        temporary_path = self.uploads_dir / (
            f".active-dataset-{uuid.uuid4().hex}.tmp"
        )
        descriptor: int | None = os.open(
            temporary_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = None
                written = stream.write(encoded)
                if written != len(encoded):
                    raise OSError("Écriture partielle du manifeste actif.")
                stream.flush()
                try:
                    os.fsync(stream.fileno())
                except OSError:
                    pass
            os.replace(temporary_path, self._manifest_path)
            self._best_effort_fsync_directory(self.uploads_dir)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _build_manifest_payload(
        snapshot: DatasetSnapshot,
        *,
        stored_filename: str,
        original_filename: str,
        size_bytes: int,
        sha256: str,
    ) -> dict[str, object]:
        rows, columns = snapshot.dataframe.shape
        return {
            "version": _ACTIVE_MANIFEST_VERSION,
            "dataset_id": snapshot.id,
            "stored_filename": stored_filename,
            "original_filename": original_filename,
            "name": snapshot.name,
            "context": snapshot.context,
            "updated_at": snapshot.updated_at,
            "selected_sheet": snapshot.selected_sheet,
            "available_sheets": list(snapshot.available_sheets),
            "rows": int(rows),
            "columns": int(columns),
            "size_bytes": size_bytes,
            "sha256": sha256,
        }

    @staticmethod
    def _copy_snapshot(snapshot: DatasetSnapshot) -> DatasetSnapshot:
        return DatasetSnapshot(
            id=snapshot.id,
            name=snapshot.name,
            source=snapshot.source,
            updated_at=snapshot.updated_at,
            context=snapshot.context,
            dataframe=snapshot.dataframe.copy(deep=True),
            selected_sheet=snapshot.selected_sheet,
            available_sheets=snapshot.available_sheets,
        )

    def get_active(self) -> DatasetSnapshot:
        """Retourne une copie, empêchant un endpoint de modifier l'état partagé."""

        with self._lock:
            return self._copy_snapshot(self._active)

    def recovery_metadata(self) -> dict[str, str | None]:
        """Expose a stable, non-sensitive recovery state for the overview."""

        with self._lock:
            return {
                "status": self._recovery_status,
                "message": self._recovery_message,
            }

    def create_staged_upload(self) -> Path:
        """Reserve a private path used by the endpoint for incremental writes."""

        path = self.uploads_dir / f".upload-{uuid.uuid4().hex}.part"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        return path

    def discard_staged_upload(self, staged_path: Path) -> None:
        """Remove only a staging file contained in the configured upload root."""

        resolved = staged_path.resolve()
        root = self.uploads_dir.resolve()
        if root not in resolved.parents or not resolved.name.startswith(".upload-"):
            return
        try:
            resolved.unlink(missing_ok=True)
        except OSError:
            pass

    def activate_staged_upload(
        self,
        filename: str,
        staged_path: Path,
        sheet_name: str | None = None,
    ) -> DatasetSnapshot:
        """Validate a staged file, atomically retain it and activate its data.

        La sauvegarde n'a lieu qu'après un parsing réussi, ce qui évite de garder
        des fichiers invalides dans ``data/uploads``.
        """

        safe_original_name = Path(filename.replace("\\", "/")).name
        suffix = Path(safe_original_name).suffix.lower()
        if suffix not in {".csv", ".xlsx"}:
            raise DatasetError("Format non pris en charge. Utilisez un fichier CSV ou XLSX.")
        if (
            not safe_original_name
            or len(safe_original_name) > 512
            or not safe_original_name.isprintable()
        ):
            raise DatasetError("Nom de fichier invalide.")
        if staged_path.is_symlink():
            raise DatasetError("Chemin temporaire invalide.")
        staged_path = staged_path.resolve()
        uploads_root = self.uploads_dir.resolve()
        if (
            uploads_root not in staged_path.parents
            or not staged_path.name.startswith(".upload-")
            or not staged_path.is_file()
        ):
            raise DatasetError("Chemin temporaire invalide.")
        size_bytes = staged_path.stat().st_size
        if size_bytes > self.limits.max_file_bytes:
            raise DatasetError("Le fichier dépasse la limite configurée.")
        sha256 = self._sha256_path(staged_path)
        parsed = _read_dataframe_path(
            safe_original_name,
            staged_path,
            self.limits,
            sheet_name,
        )
        dataframe = parsed.dataframe
        dataset_id = uuid.uuid4().hex
        stored_name = f"{dataset_id}{suffix}"
        stored_path = (self.uploads_dir / stored_name).resolve()
        if uploads_root not in stored_path.parents:
            raise DatasetError("Nom de fichier invalide.")

        snapshot = DatasetSnapshot(
            id=dataset_id,
            name=_display_name(safe_original_name),
            source="upload",
            updated_at=_utc_now(),
            context=_infer_context(safe_original_name, list(dataframe.columns)),
            dataframe=dataframe,
            selected_sheet=parsed.selected_sheet,
            available_sheets=parsed.available_sheets,
        )
        manifest_payload = self._build_manifest_payload(
            snapshot,
            stored_filename=stored_name,
            original_filename=safe_original_name,
            size_bytes=size_bytes,
            sha256=sha256,
        )
        # The same strict validator used during recovery prevents publishing a
        # state that the next process could not restore.
        self._validate_manifest_payload(manifest_payload)
        with self._lock:
            previous_stored_path = self._active_stored_path
            previous_manifest_payload = (
                dict(self._active_manifest_payload)
                if self._active_manifest_payload is not None
                else None
            )

            # Begin from one known durable target so a failed final prune can
            # strictly roll back to the previous manifest and file.
            self._prune_final_uploads(keep=previous_stored_path)

            manifest_committed = False
            try:
                os.replace(staged_path, stored_path)
                self._best_effort_fsync_file(stored_path)
                self._best_effort_fsync_directory(self.uploads_dir)
                self._write_manifest_atomically(manifest_payload)
                manifest_committed = True
                self._prune_final_uploads(keep=stored_path)
            except OSError as commit_error:
                rollback_error: OSError | None = None
                try:
                    if manifest_committed:
                        if previous_manifest_payload is None:
                            self._manifest_path.unlink(missing_ok=True)
                            self._best_effort_fsync_directory(self.uploads_dir)
                        else:
                            self._write_manifest_atomically(previous_manifest_payload)
                except OSError as exc:
                    rollback_error = exc
                if rollback_error is None:
                    try:
                        stored_path.unlink(missing_ok=True)
                        self._best_effort_fsync_directory(self.uploads_dir)
                    except OSError as exc:
                        rollback_error = exc
                if rollback_error is not None:
                    raise rollback_error from commit_error
                raise

            # Publish memory only after file, manifest and retention succeeded.
            self._active = snapshot
            self._active_stored_path = stored_path
            self._active_manifest_payload = manifest_payload
            self._recovery_status = "active"
            self._recovery_message = None
            return self._copy_snapshot(snapshot)

    def activate_upload(
        self,
        filename: str,
        content: bytes,
        sheet_name: str | None = None,
    ) -> DatasetSnapshot:
        """Compatibility wrapper for trusted in-process callers using bytes."""

        staged_path = self.create_staged_upload()
        try:
            staged_path.write_bytes(content)
            return self.activate_staged_upload(filename, staged_path, sheet_name)
        finally:
            self.discard_staged_upload(staged_path)

    def storage_metrics(self) -> dict[str, int]:
        """Return bounded aggregate usage without exposing names or paths."""

        with self._lock:
            files = self._final_upload_paths()
            return {
                "files": len(files),
                "bytes": sum(path.stat().st_size for path in files),
                "max_files": 1,
            }

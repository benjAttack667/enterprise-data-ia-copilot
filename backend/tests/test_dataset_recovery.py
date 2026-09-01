"""Acceptance contract for durable recovery of the active dataset.

These tests intentionally recreate the whole FastAPI application instead of
calling private restore helpers.  They therefore exercise the same boundary as
a container restart while keeping every artefact inside pytest's temporary
directories.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.src.config import Settings


MANIFEST_NAME = ".active-dataset.json"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SERVICE_TOKEN = "dataset-recovery-test-service-token-2026"


def _upload(
    client: TestClient,
    filename: str,
    content: bytes,
    *,
    sheet_name: str | None = None,
    headers: dict[str, str] | None = None,
):
    data = {} if sheet_name is None else {"sheet_name": sheet_name}
    content_type = XLSX_MIME if filename.lower().endswith(".xlsx") else "text/csv"
    return client.post(
        "/api/upload",
        data=data,
        files={"file": (filename, content, content_type)},
        headers=headers,
    )


def _xlsx_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        for sheet_name, dataframe in sheets.items():
            dataframe.to_excel(writer, sheet_name=sheet_name, index=False)
    return stream.getvalue()


def _manifest_path(settings: Settings) -> Path:
    return settings.uploads_dir / MANIFEST_NAME


def _manifest(settings: Settings) -> dict[str, Any]:
    payload = json.loads(_manifest_path(settings).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_manifest(settings: Settings, payload: dict[str, Any]) -> None:
    _manifest_path(settings).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def _final_uploads(settings: Settings) -> list[Path]:
    return sorted(
        [
            path
            for pattern in ("*.csv", "*.xlsx")
            for path in settings.uploads_dir.glob(pattern)
            if path.is_file() or path.is_symlink()
        ],
        key=lambda path: path.name,
    )


def _assert_recovery(
    overview: dict[str, Any],
    status: str,
    *,
    message: str | None = None,
) -> None:
    recovery = overview["dataset_recovery"]
    assert set(recovery) == {"status", "message"}
    assert recovery["status"] == status
    if message is None:
        assert recovery["message"] is None
    else:
        assert isinstance(recovery["message"], str)
        assert message.casefold() in recovery["message"].casefold()


def _assert_same_dataset(before: dict[str, Any], after: dict[str, Any]) -> None:
    stable_fields = {
        "id",
        "name",
        "source",
        "updated_at",
        "context",
        "rows",
        "columns",
        "selected_sheet",
        "available_sheets",
    }
    assert {field: before[field] for field in stable_fields} == {
        field: after[field] for field in stable_fields
    }


def _dataset_upload_events(client: TestClient) -> list[dict[str, Any]]:
    items = client.get("/api/history", params={"limit": 200}).json()["items"]
    return [item for item in items if item["action"] == "dataset_uploaded"]


def _create_persisted_csv(settings: Settings) -> dict[str, Any]:
    content = b"segment,amount\nEnterprise,10\nSMB,20\n"
    with TestClient(create_app(settings)) as client:
        response = _upload(client, "baseline-sales.csv", content)
        assert response.status_code == 200, response.text
        overview = client.get("/api/overview").json()
        _assert_recovery(overview, "active")
        return overview


def test_fresh_start_reports_the_bundled_sample_without_warning(
    settings: Settings,
) -> None:
    with TestClient(create_app(settings)) as client:
        overview = client.get("/api/overview").json()

    assert overview["dataset"]["id"] == "marketing-leads"
    assert overview["dataset"]["source"] == "sample"
    _assert_recovery(overview, "sample")
    assert not _manifest_path(settings).exists()


def test_semicolon_csv_is_restored_with_identical_metadata_and_values(
    settings: Settings,
) -> None:
    content = (
        'label;amount\n"France; métropole";100\nBelgique;200\n'.encode("utf-8")
    )
    with TestClient(create_app(settings)) as client:
        response = _upload(client, "regional-sales.csv", content)
        assert response.status_code == 200, response.text
        active = client.get("/api/overview").json()
        _assert_recovery(active, "active")
        assert len(_dataset_upload_events(client)) == 1

    assert _manifest_path(settings).is_file()
    assert len(_final_uploads(settings)) == 1
    if os.name == "posix":
        assert _manifest_path(settings).stat().st_mode & 0o777 == 0o600

    with TestClient(create_app(settings)) as restarted:
        restored = restarted.get("/api/overview").json()
        dashboard = restarted.get(
            "/api/dashboard",
            params={
                "dimension": "label",
                "metric": "amount",
                "aggregation": "sum",
            },
        )
        upload_events = _dataset_upload_events(restarted)

    _assert_same_dataset(active["dataset"], restored["dataset"])
    _assert_recovery(restored, "restored")
    assert dashboard.status_code == 200, dashboard.text
    values = {point["label"]: point["value"] for point in dashboard.json()["data"]}
    assert values == {"Belgique": 200.0, "France; métropole": 100.0}
    assert len(upload_events) == 1


def test_single_sheet_xlsx_is_restored_without_a_new_selection(
    settings: Settings,
) -> None:
    workbook = _xlsx_bytes(
        {"Data": pd.DataFrame({"team": ["A", "B"], "amount": [10, 20]})}
    )
    with TestClient(create_app(settings)) as client:
        response = _upload(client, "single-sheet.xlsx", workbook)
        assert response.status_code == 200, response.text
        active = client.get("/api/overview").json()
        assert active["dataset"]["selected_sheet"] == "Data"
        assert active["dataset"]["available_sheets"] == ["Data"]

    with TestClient(create_app(settings)) as restarted:
        restored = restarted.get("/api/overview").json()

    _assert_same_dataset(active["dataset"], restored["dataset"])
    _assert_recovery(restored, "restored")


def test_multi_sheet_xlsx_restores_the_exact_selected_sheet(
    settings: Settings,
) -> None:
    workbook = _xlsx_bytes(
        {
            "Summary": pd.DataFrame({"metric": ["revenue"], "value": [60]}),
            "Details": pd.DataFrame(
                {"team": ["Alpha", "Beta", "Gamma"], "amount": [10, 20, 30]}
            ),
        }
    )
    with TestClient(create_app(settings)) as client:
        selection = _upload(client, "multi-sheet.xlsx", workbook)
        assert selection.status_code == 409
        assert selection.json()["detail"]["code"] == "sheet_selection_required"
        assert not _manifest_path(settings).exists()
        assert _final_uploads(settings) == []

        accepted = _upload(
            client,
            "multi-sheet.xlsx",
            workbook,
            sheet_name="Details",
        )
        assert accepted.status_code == 200, accepted.text
        active = client.get("/api/overview").json()
        assert active["dataset"]["selected_sheet"] == "Details"
        assert active["dataset"]["available_sheets"] == ["Summary", "Details"]

    with TestClient(create_app(settings)) as restarted:
        restored = restarted.get("/api/overview").json()
        dashboard = restarted.get(
            "/api/dashboard",
            params={
                "dimension": "team",
                "metric": "amount",
                "aggregation": "sum",
            },
        )

    _assert_same_dataset(active["dataset"], restored["dataset"])
    _assert_recovery(restored, "restored")
    assert dashboard.status_code == 200, dashboard.text
    assert {point["label"]: point["value"] for point in dashboard.json()["data"]} == {
        "Alpha": 10.0,
        "Beta": 20.0,
        "Gamma": 30.0,
    }


def test_failed_xlsx_attempts_preserve_the_previous_manifest_across_restart(
    settings: Settings,
) -> None:
    baseline = _create_persisted_csv(settings)
    manifest_before = _manifest_path(settings).read_bytes()
    files_before = {path.name: path.read_bytes() for path in _final_uploads(settings)}
    workbook = _xlsx_bytes(
        {
            "Summary": pd.DataFrame({"metric": ["revenue"], "value": [30]}),
            "Details": pd.DataFrame({"team": ["A", "B"], "amount": [10, 20]}),
        }
    )

    with TestClient(create_app(settings)) as client:
        selection = _upload(client, "candidate.xlsx", workbook)
        invalid_sheet = _upload(
            client,
            "candidate.xlsx",
            workbook,
            sheet_name="Unknown",
        )
        corrupt = _upload(client, "candidate.xlsx", b"not an xlsx archive")
        assert selection.status_code == 409
        assert invalid_sheet.status_code == 422
        assert corrupt.status_code == 422
        assert client.get("/api/overview").json()["dataset"]["id"] == baseline[
            "dataset"
        ]["id"]

    assert _manifest_path(settings).read_bytes() == manifest_before
    assert {path.name: path.read_bytes() for path in _final_uploads(settings)} == files_before
    with TestClient(create_app(settings)) as restarted:
        restored = restarted.get("/api/overview").json()
    assert restored["dataset"]["id"] == baseline["dataset"]["id"]
    _assert_recovery(restored, "restored")


@pytest.mark.parametrize("damage", ["missing", "hash_mismatch"])
def test_missing_or_modified_active_file_falls_back_and_self_heals(
    settings: Settings,
    damage: str,
) -> None:
    _create_persisted_csv(settings)
    retained = _final_uploads(settings)
    assert len(retained) == 1
    if damage == "missing":
        retained[0].unlink()
    else:
        original = retained[0].read_bytes()
        tampered = original.replace(b"Enterprise,10", b"Enterprise,99")
        assert len(tampered) == len(original)
        retained[0].write_bytes(tampered)

    with TestClient(create_app(settings)) as restarted:
        fallback = restarted.get("/api/overview").json()

    assert fallback["dataset"]["id"] == "marketing-leads"
    _assert_recovery(fallback, "fallback", message="restaur")
    assert not _manifest_path(settings).exists()
    assert _final_uploads(settings) == []

    with TestClient(create_app(settings)) as healthy_restart:
        healthy = healthy_restart.get("/api/overview").json()
    _assert_recovery(healthy, "sample")


@pytest.mark.parametrize("damage", ["invalid_json", "unsupported_version"])
def test_invalid_manifest_falls_back_without_guessing_an_upload(
    settings: Settings,
    damage: str,
) -> None:
    _create_persisted_csv(settings)
    if damage == "invalid_json":
        _manifest_path(settings).write_text("{truncated", encoding="utf-8")
    else:
        payload = _manifest(settings)
        payload["version"] = 999
        _write_manifest(settings, payload)

    with TestClient(create_app(settings)) as restarted:
        fallback = restarted.get("/api/overview").json()

    assert fallback["dataset"]["id"] == "marketing-leads"
    _assert_recovery(fallback, "fallback", message="restaur")
    assert not _manifest_path(settings).exists()
    assert _final_uploads(settings) == []


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("dataset_id", "f" * 32),
        ("rows", 999),
        ("columns", 999),
        ("size_bytes", 1),
        ("sha256", "0" * 64),
        ("selected_sheet", "Injected"),
        ("available_sheets", ["Injected"]),
        ("name", "Forged dataset"),
        ("context", "Forged context"),
    ],
)
def test_tampered_manifest_metadata_is_not_silently_trusted(
    settings: Settings,
    field: str,
    replacement: object,
) -> None:
    _create_persisted_csv(settings)
    payload = _manifest(settings)
    assert payload[field] != replacement
    payload[field] = replacement
    _write_manifest(settings, payload)

    with TestClient(create_app(settings)) as restarted:
        fallback = restarted.get("/api/overview").json()

    assert fallback["dataset"]["id"] == "marketing-leads"
    _assert_recovery(fallback, "fallback", message="restaur")


@pytest.mark.parametrize("malicious_reference", ["relative", "absolute"])
def test_manifest_cannot_read_a_dataset_outside_the_upload_directory(
    settings: Settings,
    malicious_reference: str,
) -> None:
    _create_persisted_csv(settings)
    payload = _manifest(settings)
    retained = _final_uploads(settings)[0]
    outside = settings.uploads_dir.parent / retained.name
    outside.write_bytes(retained.read_bytes())
    payload["stored_filename"] = (
        f"../{outside.name}"
        if malicious_reference == "relative"
        else str(outside.resolve())
    )
    _write_manifest(settings, payload)

    with TestClient(create_app(settings)) as restarted:
        fallback = restarted.get("/api/overview").json()

    assert fallback["dataset"]["id"] == "marketing-leads"
    _assert_recovery(fallback, "fallback", message="restaur")
    assert outside.read_bytes() == b"segment,amount\nEnterprise,10\nSMB,20\n"


def test_manifest_cannot_restore_a_symlinked_dataset(settings: Settings) -> None:
    _create_persisted_csv(settings)
    retained = _final_uploads(settings)[0]
    content = retained.read_bytes()
    outside = settings.uploads_dir.parent / "outside-symlink-target.csv"
    outside.write_bytes(content)
    retained.unlink()
    try:
        retained.symlink_to(outside)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"Symbolic links are unavailable on this test host: {exc}")

    with TestClient(create_app(settings)) as restarted:
        fallback = restarted.get("/api/overview").json()

    assert fallback["dataset"]["id"] == "marketing-leads"
    _assert_recovery(fallback, "fallback", message="restaur")
    assert outside.read_bytes() == content


def test_manifest_write_failure_rolls_back_memory_disk_and_restart_state(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _create_persisted_csv(settings)
    manifest_before = _manifest_path(settings).read_bytes()
    files_before = {path.name: path.read_bytes() for path in _final_uploads(settings)}

    with TestClient(create_app(settings)) as client:
        store = client.app.state.dataset_store
        original_writer = store._write_manifest_atomically
        calls = 0

        def fail_once(payload: dict[str, object]) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("simulated manifest write failure")
            original_writer(payload)

        monkeypatch.setattr(store, "_write_manifest_atomically", fail_once)
        rejected = _upload(
            client,
            "replacement.csv",
            b"segment,amount\nEnterprise,70\nSMB,80\n",
        )

        assert rejected.status_code == 507
        assert store.get_active().id == baseline["dataset"]["id"]
        assert len(_dataset_upload_events(client)) == 1
        assert calls >= 1

    assert _manifest_path(settings).read_bytes() == manifest_before
    assert {path.name: path.read_bytes() for path in _final_uploads(settings)} == files_before
    assert list(settings.uploads_dir.glob(".active-dataset-*.tmp")) == []
    assert list(settings.uploads_dir.glob(".upload-*.part")) == []

    with TestClient(create_app(settings)) as restarted:
        restored = restarted.get("/api/overview").json()
    assert restored["dataset"]["id"] == baseline["dataset"]["id"]
    _assert_recovery(restored, "restored")


def test_restart_removes_interrupted_files_and_newer_orphans_without_mtime_guessing(
    settings: Settings,
) -> None:
    baseline = _create_persisted_csv(settings)
    retained = _final_uploads(settings)[0]
    interrupted_upload = settings.uploads_dir / ".upload-crash.part"
    interrupted_manifest = settings.uploads_dir / ".active-dataset-crash.tmp"
    orphan = settings.uploads_dir / f"{'e' * 32}.csv"
    interrupted_upload.write_bytes(b"partial")
    interrupted_manifest.write_bytes(b"partial")
    orphan.write_bytes(b"value\n999\n")
    os.utime(orphan, (4_000_000_000, 4_000_000_000))

    with TestClient(create_app(settings)) as restarted:
        restored = restarted.get("/api/overview").json()

    assert restored["dataset"]["id"] == baseline["dataset"]["id"]
    _assert_recovery(restored, "restored")
    assert _final_uploads(settings) == [retained]
    assert not interrupted_upload.exists()
    assert not interrupted_manifest.exists()


def test_restored_dataset_keeps_the_production_api_boundary(
    settings: Settings,
) -> None:
    production = replace(
        settings,
        environment="production",
        backend_service_token=SERVICE_TOKEN,
    )
    authorization = {"Authorization": f"Bearer {SERVICE_TOKEN}"}
    with TestClient(create_app(production)) as client:
        accepted = _upload(
            client,
            "protected.csv",
            b"segment,amount\nA,10\nB,20\n",
            headers=authorization,
        )
        assert accepted.status_code == 200, accepted.text

    with TestClient(create_app(production)) as restarted:
        unauthorized = restarted.get("/api/overview")
        health = restarted.get("/api/health")
        authorized = restarted.get("/api/overview", headers=authorization)

    assert unauthorized.status_code == 401
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "version": "1.0.0"}
    assert authorized.status_code == 200
    assert authorized.json()["dataset"]["name"] == "Protected"
    _assert_recovery(authorized.json(), "restored")

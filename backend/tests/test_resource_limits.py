"""Regression tests for bounded uploads, storage and retained artefacts."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.src.config import (
    MAX_XLSX_COMPRESSION_RATIO_LIMIT,
    RESOURCE_INTEGER_UPPER_BOUNDS,
    Settings,
)
from backend.src.dataset_store import (
    DatasetError,
    DatasetLimits,
    _validate_xlsx_archive,
)
from backend.src.history import HistoryRepository
from backend.src import rate_limit as rate_limit_module
from backend.src.rate_limit import SlidingWindowRateLimiter
from backend.src.reporting import ReportService


MULTIPART_OVERHEAD_BYTES = 64 * 1024


def _tiny_settings(
    settings: Settings,
    tmp_path: Path,
    **overrides: object,
) -> Settings:
    """Build an isolated app whose sample also fits deliberately small limits."""

    samples_dir = tmp_path / "samples"
    samples_dir.mkdir(parents=True)
    (samples_dir / "marketing_leads.csv").write_bytes(b"value\n1\n")
    return replace(
        settings,
        samples_dir=samples_dir,
        uploads_dir=tmp_path / "uploads",
        reports_dir=tmp_path / "reports",
        database_path=tmp_path / "history.db",
        **overrides,
    )


def _csv_with_exact_size(size: int) -> bytes:
    prefix = b"value\n"
    suffix = b"\n"
    assert size >= len(prefix) + len(suffix) + 1
    return prefix + (b"x" * (size - len(prefix) - len(suffix))) + suffix


def _multipart_parts(
    boundary: str,
    content: bytes,
    filename: str = "dataset.csv",
) -> tuple[bytes, bytes, bytes]:
    opening = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: text/csv\r\n\r\n"
    ).encode("ascii")
    closing = f"\r\n--{boundary}--\r\n".encode("ascii")
    return opening, content, closing


def _report_payloads() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    overview: dict[str, object] = {
        "dataset": {
            "name": "Bounded dataset",
            "source": "test",
            "context": "Tests",
            "rows": 1,
            "columns": 1,
        },
        "kpis": [],
        "summary": "Résumé déterministe.",
    }
    quality: dict[str, object] = {
        "score": 100,
        "problems": [],
        "recommendations": [],
    }
    anomalies: dict[str, object] = {
        "applicable": False,
        "count": 0,
        "rate": 0,
        "message": "échantillon insuffisant",
    }
    return overview, quality, anomalies


def test_upload_accepts_exact_file_limit_and_rejects_one_extra_byte(
    client: TestClient,
    settings: Settings,
) -> None:
    exact = _csv_with_exact_size(settings.max_upload_bytes)
    accepted = client.post(
        "/api/upload",
        files={"file": ("exact.csv", exact, "text/csv")},
    )

    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["rows"] == 1
    assert sum(path.stat().st_size for path in settings.uploads_dir.glob("*.csv")) == len(
        exact
    )

    rejected = client.post(
        "/api/upload",
        files={
            "file": (
                "one-byte-too-large.csv",
                _csv_with_exact_size(settings.max_upload_bytes + 1),
                "text/csv",
            )
        },
    )

    assert rejected.status_code == 413
    assert list(settings.uploads_dir.glob(".upload-*.part")) == []
    retained = list(settings.uploads_dir.glob("*.csv"))
    assert len(retained) == 1
    assert retained[0].stat().st_size == len(exact)


@pytest.mark.parametrize(
    ("limit_overrides", "accepted_csv", "rejected_csv", "error_fragment"),
    [
        (
            {"max_dataset_rows": 2, "max_dataset_columns": 2, "max_dataset_cells": 4},
            b"a\n1\n2\n",
            b"a\n1\n2\n3\n",
            "lignes",
        ),
        (
            {"max_dataset_rows": 2, "max_dataset_columns": 2, "max_dataset_cells": 4},
            b"a,b\n1,2\n",
            b"a,b,c\n1,2,3\n",
            "colonnes",
        ),
        (
            {"max_dataset_rows": 3, "max_dataset_columns": 2, "max_dataset_cells": 4},
            b"a,b\n1,2\n3,4\n",
            b"a,b\n1,2\n3,4\n5,6\n",
            "cellules",
        ),
    ],
    ids=["rows", "columns", "cells"],
)
def test_dataset_shape_limits_accept_boundary_and_reject_overflow(
    settings: Settings,
    tmp_path: Path,
    limit_overrides: dict[str, int],
    accepted_csv: bytes,
    rejected_csv: bytes,
    error_fragment: str,
) -> None:
    bounded = _tiny_settings(settings, tmp_path, **limit_overrides)
    with TestClient(create_app(bounded)) as client:
        accepted = client.post(
            "/api/upload",
            files={"file": ("accepted.csv", accepted_csv, "text/csv")},
        )
        rejected = client.post(
            "/api/upload",
            files={"file": ("rejected.csv", rejected_csv, "text/csv")},
        )

    assert accepted.status_code == 200, accepted.text
    assert rejected.status_code == 422
    assert error_fragment in rejected.json()["detail"]
    assert len(list(bounded.uploads_dir.glob("*.csv"))) == 1
    assert list(bounded.uploads_dir.glob(".upload-*.part")) == []


def test_xlsx_preflight_rejects_uncompressed_size(tmp_path: Path) -> None:
    archive_path = tmp_path / "large-uncompressed.xlsx"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", b"A" * 2_048)

    limits = DatasetLimits(
        max_xlsx_uncompressed_bytes=1_024,
        max_xlsx_compression_ratio=10_000,
    )
    with pytest.raises(DatasetError, match="décompressé"):
        _validate_xlsx_archive(archive_path, limits)


def test_xlsx_preflight_rejects_suspicious_compression_ratio(tmp_path: Path) -> None:
    archive_path = tmp_path / "compression-bomb.xlsx"
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", b"0" * 100_000)

    limits = DatasetLimits(
        max_xlsx_uncompressed_bytes=200_000,
        max_xlsx_compression_ratio=2,
    )
    with pytest.raises(DatasetError, match="compression"):
        _validate_xlsx_archive(archive_path, limits)


def test_xlsx_preflight_rejects_too_many_archive_entries(tmp_path: Path) -> None:
    archive_path = tmp_path / "too-many-entries.xlsx"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for index in range(3):
            archive.writestr(f"entry-{index}.xml", b"x")

    limits = DatasetLimits(max_xlsx_entries=2)
    with pytest.raises(DatasetError, match="trop d'éléments"):
        _validate_xlsx_archive(archive_path, limits)


def test_xlsx_preflight_rejects_encrypted_member_flag(tmp_path: Path) -> None:
    archive_path = tmp_path / "encrypted.xlsx"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("xl/workbook.xml", b"workbook")

    raw_archive = bytearray(archive_path.read_bytes())
    local_header = raw_archive.index(b"PK\x03\x04")
    central_header = raw_archive.index(b"PK\x01\x02")
    raw_archive[local_header + 6] |= 0x01
    raw_archive[central_header + 8] |= 0x01
    archive_path.write_bytes(raw_archive)

    with pytest.raises(DatasetError, match="chiffrés"):
        _validate_xlsx_archive(archive_path, DatasetLimits())


def test_upload_rate_limit_returns_retry_after(
    settings: Settings,
    tmp_path: Path,
) -> None:
    limited = _tiny_settings(
        settings,
        tmp_path,
        upload_rate_limit_requests=2,
        upload_rate_limit_window_seconds=60,
    )
    with TestClient(create_app(limited)) as client:
        first = client.post(
            "/api/upload",
            files={"file": ("first.csv", b"value\n1\n", "text/csv")},
        )
        second = client.post(
            "/api/upload",
            files={"file": ("second.csv", b"value\n2\n", "text/csv")},
        )
        throttled = client.post(
            "/api/upload",
            files={"file": ("third.csv", b"value\n3\n", "text/csv")},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert throttled.status_code == 429
    assert int(throttled.headers["retry-after"]) >= 1
    assert "quota" in throttled.json()["detail"].casefold()


def test_upload_storage_failure_returns_507_and_releases_gate(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = client.app.state.dataset_store
    monkeypatch.setattr(
        store,
        "create_staged_upload",
        Mock(side_effect=OSError("simulated disk failure")),
    )

    response = client.post(
        "/api/upload",
        files={"file": ("dataset.csv", b"value\n1\n", "text/csv")},
    )

    assert response.status_code == 507
    assert "stockage" in response.json()["detail"].casefold()
    assert client.app.state.history.storage_metrics()["entries"] == 0
    gate = client.app.state.upload_gate
    assert gate.acquire(blocking=False) is True
    gate.release()


def test_report_storage_failure_returns_507_without_audit_event(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate = Mock(side_effect=OSError("simulated disk failure"))
    monkeypatch.setattr(client.app.state.reports, "generate", generate)

    response = client.post("/api/report", json={"format": "markdown"})

    assert response.status_code == 507
    assert "stockage" in response.json()["detail"].casefold()
    assert generate.call_count == 1
    assert client.app.state.history.storage_metrics()["entries"] == 0


def test_audit_failure_does_not_rollback_successful_upload_or_report(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = Mock(side_effect=sqlite3.OperationalError("simulated audit failure"))
    monkeypatch.setattr(client.app.state.history, "record", record)

    upload = client.post(
        "/api/upload",
        files={"file": ("durable.csv", b"value\n1\n2\n", "text/csv")},
    )
    report = client.post("/api/report", json={"format": "markdown"})

    assert upload.status_code == 200, upload.text
    assert report.status_code == 200, report.text
    assert record.call_count == 2
    assert client.app.state.dataset_store.get_active().id == upload.json()["dataset_id"]
    assert len(list(settings.uploads_dir.glob("*.csv"))) == 1
    assert (settings.reports_dir / report.json()["filename"]).is_file()
    assert client.app.state.history.storage_metrics()["entries"] == 0


def test_upload_gate_rejects_second_request_before_consuming_its_body(
    settings: Settings,
    tmp_path: Path,
) -> None:
    bounded = _tiny_settings(settings, tmp_path)
    app = create_app(bounded)
    boundary = "concurrency-boundary"
    first_opening, first_content, first_closing = _multipart_parts(
        boundary,
        b"value\n1\n",
        "first.csv",
    )
    second_parts = _multipart_parts(boundary, b"value\n2\n", "second.csv")

    async def exercise_gate() -> tuple[httpx.Response, httpx.Response, bool]:
        first_chunk_consumed = asyncio.Event()
        release_first_body = asyncio.Event()
        second_body_consumed = False

        async def slow_first_body():
            yield first_opening
            first_chunk_consumed.set()
            await release_first_body.wait()
            yield first_content
            yield first_closing

        async def observable_second_body():
            nonlocal second_body_consumed
            second_body_consumed = True
            for part in second_parts:
                yield part

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as async_client:
            first_task = asyncio.create_task(
                async_client.post(
                    "/api/upload",
                    content=slow_first_body(),
                    headers={
                        "Content-Type": f"multipart/form-data; boundary={boundary}"
                    },
                )
            )
            await asyncio.wait_for(first_chunk_consumed.wait(), timeout=2)
            try:
                second_response = await asyncio.wait_for(
                    async_client.post(
                        "/api/upload",
                        content=observable_second_body(),
                        headers={
                            "Content-Type": (
                                f"multipart/form-data; boundary={boundary}"
                            )
                        },
                    ),
                    timeout=2,
                )
            finally:
                release_first_body.set()
            first_response = await asyncio.wait_for(first_task, timeout=5)
        return first_response, second_response, second_body_consumed

    first, second, second_body_consumed = asyncio.run(exercise_gate())

    assert first.status_code == 200, first.text
    assert second.status_code == 429
    assert second.headers["retry-after"] == "1"
    assert second_body_consumed is False


def test_shared_workload_gate_rejects_second_analytics_before_body_or_work(
    settings: Settings,
    tmp_path: Path,
) -> None:
    bounded = _tiny_settings(settings, tmp_path)
    app = create_app(bounded)
    get_active = Mock(wraps=app.state.dataset_store.get_active)
    ask = Mock(wraps=app.state.ai.ask)
    app.state.dataset_store.get_active = get_active
    app.state.ai.ask = ask

    async def exercise_gate() -> tuple[httpx.Response, httpx.Response, bool]:
        first_chunk_consumed = asyncio.Event()
        release_first_body = asyncio.Event()
        second_body_consumed = False

        async def slow_first_body():
            yield b'{"question":"'
            first_chunk_consumed.set()
            await release_first_body.wait()
            yield b'first analytics request"}'

        async def observable_second_body():
            nonlocal second_body_consumed
            second_body_consumed = True
            yield b'{"question":"second analytics request"}'

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as async_client:
            first_task = asyncio.create_task(
                async_client.post(
                    "/api/ask",
                    content=slow_first_body(),
                    headers={"Content-Type": "application/json"},
                )
            )
            await asyncio.wait_for(first_chunk_consumed.wait(), timeout=2)
            try:
                second_response = await asyncio.wait_for(
                    async_client.post(
                        "/api/ask",
                        content=observable_second_body(),
                        headers={"Content-Type": "application/json"},
                    ),
                    timeout=2,
                )
                assert get_active.call_count == 0
                assert ask.call_count == 0
            finally:
                release_first_body.set()
            first_response = await asyncio.wait_for(first_task, timeout=5)

            released_response = await async_client.post(
                "/api/ask",
                json={"question": "request after gate release"},
            )

        assert released_response.status_code == 200, released_response.text
        return first_response, second_response, second_body_consumed

    first, second, second_body_consumed = asyncio.run(exercise_gate())

    assert first.status_code == 200, first.text
    assert second.status_code == 429
    assert second.headers["retry-after"] == "1"
    assert second_body_consumed is False
    assert get_active.call_count == 2
    assert ask.call_count == 2


def test_upload_parsing_does_not_block_public_health_endpoint(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bounded = _tiny_settings(settings, tmp_path)
    app = create_app(bounded)
    original_activate = app.state.dataset_store.activate_staged_upload
    parsing_started = threading.Event()
    release_parsing = threading.Event()

    def blocking_activate(filename: str, staged_path: Path):
        parsing_started.set()
        assert release_parsing.wait(timeout=5), "upload parser was never released"
        return original_activate(filename, staged_path)

    monkeypatch.setattr(
        app.state.dataset_store,
        "activate_staged_upload",
        blocking_activate,
    )

    async def exercise_responsiveness() -> tuple[httpx.Response, httpx.Response, bool]:
        # This timer only prevents a deadlock on a regression where parsing is
        # accidentally moved back onto the event-loop thread.
        fallback_release = threading.Timer(3, release_parsing.set)
        fallback_release.daemon = True
        fallback_release.start()
        upload_task: asyncio.Task[httpx.Response] | None = None
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as async_client:
                upload_task = asyncio.create_task(
                    async_client.post(
                        "/api/upload",
                        files={
                            "file": (
                                "background.csv",
                                b"value\n1\n",
                                "text/csv",
                            )
                        },
                    )
                )
                started = await asyncio.to_thread(parsing_started.wait, 2)
                assert started, "upload parsing did not start"
                health = await async_client.get("/api/health")
                released_before_health = release_parsing.is_set()
                release_parsing.set()
                upload = await asyncio.wait_for(upload_task, timeout=5)
        finally:
            release_parsing.set()
            fallback_release.cancel()
            if upload_task is not None and not upload_task.done():
                upload_task.cancel()

        return upload, health, released_before_health

    upload, health, released_before_health = asyncio.run(exercise_responsiveness())

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert released_before_health is False
    assert upload.status_code == 200, upload.text


def test_sliding_window_timestamps_remain_ordered_under_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock_lock = threading.Lock()
    next_timestamp = 1_000

    def deterministic_monotonic() -> float:
        nonlocal next_timestamp
        with clock_lock:
            current = next_timestamp
            next_timestamp += 1
            return float(current)

    monkeypatch.setattr(
        rate_limit_module,
        "time",
        SimpleNamespace(monotonic=deterministic_monotonic),
    )
    limiter = SlidingWindowRateLimiter(max_requests=8, window_seconds=10_000)
    barrier = threading.Barrier(32)

    def consume_concurrently() -> bool:
        barrier.wait(timeout=5)
        return limiter.consume().allowed

    with ThreadPoolExecutor(max_workers=32) as executor:
        decisions = list(executor.map(lambda _: consume_concurrently(), range(32)))

    assert decisions.count(True) == 8
    assert decisions.count(False) == 24
    assert list(limiter._timestamps) == [float(value) for value in range(1_000, 1_008)]


def test_upload_prune_failure_rolls_back_new_file_and_active_snapshot(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_content = b"value\n1\n"
    accepted = client.post(
        "/api/upload",
        files={"file": ("retained.csv", first_content, "text/csv")},
    )
    assert accepted.status_code == 200, accepted.text

    store = client.app.state.dataset_store
    previous_snapshot = store.get_active()
    previous_files = list(settings.uploads_dir.glob("*.csv"))
    assert len(previous_files) == 1
    previous_file = previous_files[0]
    assert previous_file.read_bytes() == first_content

    prune = Mock(side_effect=OSError("simulated upload prune failure"))
    monkeypatch.setattr(store, "_prune_final_uploads", prune)
    rejected = client.post(
        "/api/upload",
        files={"file": ("rolled-back.csv", b"value\n2\n3\n", "text/csv")},
    )

    assert rejected.status_code == 507
    assert "stockage" in rejected.json()["detail"].casefold()
    assert prune.call_count == 1
    assert store.get_active().id == previous_snapshot.id
    assert list(settings.uploads_dir.glob("*.csv")) == [previous_file]
    assert previous_file.read_bytes() == first_content
    assert list(settings.uploads_dir.glob(".upload-*.part")) == []
    assert client.app.state.history.storage_metrics()["entries"] == 1


def test_report_prune_failure_rolls_back_new_report_and_preserves_previous_one(
    client: TestClient,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accepted = client.post("/api/report", json={"format": "markdown"})
    assert accepted.status_code == 200, accepted.text

    reports = client.app.state.reports
    previous_snapshot_id = client.app.state.dataset_store.get_active().id
    previous_files = list(settings.reports_dir.glob("data-report-*.md"))
    assert len(previous_files) == 1
    previous_file = previous_files[0]
    previous_content = previous_file.read_bytes()

    prune = Mock(side_effect=OSError("simulated report prune failure"))
    monkeypatch.setattr(reports, "_prune_reports", prune)
    rejected = client.post("/api/report", json={"format": "markdown"})

    assert rejected.status_code == 507
    assert "stockage" in rejected.json()["detail"].casefold()
    assert prune.call_count == 1
    assert client.app.state.dataset_store.get_active().id == previous_snapshot_id
    assert list(settings.reports_dir.glob("data-report-*.md")) == [previous_file]
    assert previous_file.read_bytes() == previous_content
    assert list(settings.reports_dir.glob(".report-*.part")) == []
    assert client.app.state.history.storage_metrics()["entries"] == 1


@pytest.mark.parametrize("declared_content_length", [None, "1"])
def test_request_body_limit_precedes_multipart_parsing_even_without_trusted_length(
    settings: Settings,
    tmp_path: Path,
    declared_content_length: str | None,
) -> None:
    bounded = _tiny_settings(settings, tmp_path)
    app = create_app(bounded)
    original_create_staged = app.state.dataset_store.create_staged_upload
    create_staged = Mock(wraps=original_create_staged)
    app.state.dataset_store.create_staged_upload = create_staged
    boundary = "body-limit-boundary"
    parts = _multipart_parts(
        boundary,
        b"x" * (bounded.max_upload_bytes + MULTIPART_OVERHEAD_BYTES + 1),
        "oversized.csv",
    )

    async def send_oversized_request() -> httpx.Response:
        async def chunked_body():
            for part in parts:
                yield part

        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
        if declared_content_length is not None:
            headers["Content-Length"] = declared_content_length
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as async_client:
            return await async_client.post(
                "/api/upload",
                content=chunked_body(),
                headers=headers,
            )

    response = asyncio.run(send_oversized_request())

    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/json")
    assert isinstance(response.json()["detail"], str)
    create_staged.assert_not_called()
    assert list(bounded.uploads_dir.glob(".upload-*.part")) == []
    assert list(bounded.uploads_dir.glob("*.csv")) == []
    assert app.state.history.storage_metrics()["entries"] == 0


def test_non_upload_business_body_is_limited_before_json_validation(
    settings: Settings,
    tmp_path: Path,
) -> None:
    bounded = _tiny_settings(settings, tmp_path)
    app = create_app(bounded)
    ask = Mock(wraps=app.state.ai.ask)
    app.state.ai.ask = ask
    oversized_json = (
        b'{"question":"'
        + (b"x" * (64 * 1024 + 1))
        + b'"}'
    )

    async def send_oversized_request() -> httpx.Response:
        async def chunked_body():
            yield oversized_json[:1_024]
            yield oversized_json[1_024:]

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as async_client:
            return await async_client.post(
                "/api/ask",
                content=chunked_body(),
                headers={"Content-Type": "application/json"},
            )

    response = asyncio.run(send_oversized_request())

    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/json")
    ask.assert_not_called()
    assert app.state.history.storage_metrics()["entries"] == 0


def test_missing_production_auth_is_rejected_without_consuming_request_body(
    settings: Settings,
    tmp_path: Path,
) -> None:
    production = replace(
        _tiny_settings(settings, tmp_path),
        environment="production",
        backend_service_token="resource-test-service-token-32-bytes-minimum",
    )
    app = create_app(production)

    async def send_unauthenticated_request() -> tuple[httpx.Response, bool]:
        body_consumed = False

        async def observable_body():
            nonlocal body_consumed
            body_consumed = True
            yield b'{"question":"should not be read"}'

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as async_client:
            response = await async_client.post(
                "/api/ask",
                content=observable_body(),
                headers={"Content-Type": "application/json"},
            )
        return response, body_consumed

    response, body_consumed = asyncio.run(send_unauthenticated_request())

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert body_consumed is False


def test_startup_cleans_interrupted_upload_and_report_staging_files(
    settings: Settings,
    tmp_path: Path,
) -> None:
    bounded = _tiny_settings(settings, tmp_path)
    bounded.uploads_dir.mkdir(parents=True)
    bounded.reports_dir.mkdir(parents=True)
    interrupted_upload = bounded.uploads_dir / ".upload-interrupted.part"
    interrupted_report = bounded.reports_dir / ".report-interrupted.part"
    interrupted_upload.write_bytes(b"partial")
    interrupted_report.write_bytes(b"partial")

    create_app(bounded)

    assert not interrupted_upload.exists()
    assert not interrupted_report.exists()


def test_successive_uploads_keep_only_the_active_file(
    client: TestClient,
    settings: Settings,
) -> None:
    first = client.post(
        "/api/upload",
        files={"file": ("first.csv", b"value\n1\n", "text/csv")},
    )
    first_paths = list(settings.uploads_dir.glob("*.csv"))
    second = client.post(
        "/api/upload",
        files={"file": ("second.csv", b"value\n2\n3\n", "text/csv")},
    )
    retained_paths = list(settings.uploads_dir.glob("*.csv"))

    assert first.status_code == 200
    assert len(first_paths) == 1
    assert second.status_code == 200
    assert len(retained_paths) == 1
    assert retained_paths[0] != first_paths[0]
    assert not first_paths[0].exists()
    assert client.get("/api/overview").json()["dataset"]["id"] == second.json()[
        "dataset_id"
    ]


def test_report_retention_keeps_twenty_newest_files(tmp_path: Path) -> None:
    reports_dir = tmp_path / "reports"
    service = ReportService(reports_dir, max_files=20)
    overview, quality, anomalies = _report_payloads()

    generated: list[dict[str, object]] = []
    for index in range(20):
        result = service.generate("markdown", overview, quality, anomalies)
        generated.append(result)
        # Give pruning an unambiguous order even on filesystems with a coarse
        # timestamp resolution. Distinct filenames are still required here.
        report_path = reports_dir / str(result["filename"])
        explicit_time_ns = (index + 1) * 1_000_000_000
        os.utime(report_path, ns=(explicit_time_ns, explicit_time_ns))
    generated.append(service.generate("markdown", overview, quality, anomalies))
    retained = list(reports_dir.glob("data-report-*.md"))

    assert len(retained) == 20
    assert service.storage_metrics()["files"] == 20
    assert not (reports_dir / str(generated[0]["filename"])).exists()
    assert (reports_dir / str(generated[-1]["filename"])).exists()
    assert list(reports_dir.glob(".report-*.part")) == []


def test_history_retention_keeps_five_hundred_newest_entries(tmp_path: Path) -> None:
    database_path = tmp_path / "history.db"
    history = HistoryRepository(database_path, max_entries=500)
    for index in range(501):
        history.record(
            action=f"event-{index}",
            dataset_id="dataset",
            dataset_name="Dataset",
        )

    with sqlite3.connect(database_path) as connection:
        count, minimum_id, maximum_id = connection.execute(
            "SELECT COUNT(*), MIN(id), MAX(id) FROM analysis_history"
        ).fetchone()

    assert (count, minimum_id, maximum_id) == (500, 2, 501)
    assert history.storage_metrics()["entries"] == 500
    assert history.list_recent(1)[0]["action"] == "event-500"


@pytest.mark.parametrize(
    ("attribute", "environment_name"),
    [
        ("max_upload_bytes", "MAX_UPLOAD_BYTES"),
        ("max_dataset_rows", "MAX_DATASET_ROWS"),
        ("max_dataset_columns", "MAX_DATASET_COLUMNS"),
        ("max_dataset_cells", "MAX_DATASET_CELLS"),
        ("max_xlsx_uncompressed_bytes", "MAX_XLSX_UNCOMPRESSED_BYTES"),
        ("max_xlsx_entries", "MAX_XLSX_ENTRIES"),
        ("upload_rate_limit_requests", "UPLOAD_RATE_LIMIT_REQUESTS"),
        (
            "upload_rate_limit_window_seconds",
            "UPLOAD_RATE_LIMIT_WINDOW_SECONDS",
        ),
        ("max_report_files", "MAX_REPORT_FILES"),
        ("max_history_entries", "MAX_HISTORY_ENTRIES"),
    ],
)
def test_settings_reject_resource_values_above_safe_upper_bounds(
    settings: Settings,
    attribute: str,
    environment_name: str,
) -> None:
    with pytest.raises(ValueError, match=environment_name):
        replace(
            settings,
            **{attribute: RESOURCE_INTEGER_UPPER_BOUNDS[environment_name] + 1},
        )


def test_settings_reject_excessive_xlsx_compression_ratio(
    settings: Settings,
) -> None:
    with pytest.raises(ValueError, match="MAX_XLSX_COMPRESSION_RATIO"):
        replace(
            settings,
            max_xlsx_compression_ratio=MAX_XLSX_COMPRESSION_RATIO_LIMIT + 1,
        )


def test_read_only_analytics_do_not_grow_history(client: TestClient) -> None:
    history = client.app.state.history
    before = history.storage_metrics()["entries"]

    for path in (
        "/api/overview",
        "/api/data-quality",
        "/api/dashboard",
        "/api/anomalies",
        "/api/history",
    ):
        response = client.get(path)
        assert response.status_code == 200, response.text

    assert history.storage_metrics()["entries"] == before


def test_overview_reports_real_storage_usage_and_quotas(
    client: TestClient,
    settings: Settings,
) -> None:
    csv_content = b"value\n1\n2\n"
    upload = client.post(
        "/api/upload",
        files={"file": ("storage.csv", csv_content, "text/csv")},
    )
    report = client.post("/api/report", json={"format": "markdown"})
    overview = client.get("/api/overview")

    assert upload.status_code == 200
    assert report.status_code == 200
    assert overview.status_code == 200
    storage = overview.json()["storage"]
    assert storage["uploads"] == {
        "files": 1,
        "bytes": len(csv_content),
        "max_files": 1,
        "max_file_bytes": settings.max_upload_bytes,
    }
    assert storage["reports"]["files"] == 1
    report_path = settings.reports_dir / report.json()["filename"]
    expected_report_bytes = report.json()["content"].encode("utf-8")
    assert report_path.read_bytes() == expected_report_bytes
    assert storage["reports"]["bytes"] == len(expected_report_bytes)
    assert storage["reports"]["max_files"] == settings.max_report_files
    assert storage["history"]["entries"] == 2
    assert storage["history"]["max_entries"] == settings.max_history_entries
    assert storage["history"]["files"] >= 1
    assert storage["history"]["bytes"] > 0


def test_upload_staging_file_permissions_are_private(
    settings: Settings,
    tmp_path: Path,
) -> None:
    """The assertion is meaningful on POSIX and harmless on Windows ACL hosts."""

    bounded = _tiny_settings(settings, tmp_path)
    app = create_app(bounded)
    staged = app.state.dataset_store.create_staged_upload()
    try:
        if os.name == "posix":
            assert staged.stat().st_mode & 0o777 == 0o600
    finally:
        app.state.dataset_store.discard_staged_upload(staged)

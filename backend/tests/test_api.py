"""Tests du contrat JSON et des fonctionnalités réellement exposées."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.src.config import Settings


def test_health_and_default_marketing_overview(client: TestClient) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "version": "1.0.0"}

    response = client.get("/api/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset"]["name"] == "Marketing Leads"
    assert payload["dataset"]["rows"] == 15
    assert payload["dataset"]["columns"] == 11
    assert set(payload) == {
        "dataset",
        "kpis",
        "quality_score",
        "summary",
        "recommendations",
        "quality_by_column",
        "missing_distribution",
        "category_breakdown",
        "trend",
        "storage",
    }
    assert payload["storage"]["uploads"]["max_files"] == 1
    assert payload["storage"]["reports"]["max_files"] == 20
    assert payload["storage"]["history"]["max_entries"] == 500
    assert all({"id", "label", "value", "hint", "tone"} <= set(kpi) for kpi in payload["kpis"])
    assert {"rows", "columns", "quality", "anomalies", "missing_values", "duplicates"} <= {
        kpi["id"] for kpi in payload["kpis"]
    }
    assert payload["trend"]


def test_data_quality_detects_real_missing_value_and_duplicate(client: TestClient) -> None:
    response = client.get("/api/data-quality")
    assert response.status_code == 200
    payload = response.json()
    assert 0 <= payload["score"] <= 100
    assert payload["summary"]["missing_count"] == 1
    assert payload["summary"]["duplicate_count"] == 1
    assert payload["summary"]["strict_duplicate_count"] == 0
    assert payload["summary"]["identifier_duplicate_count"] == 1
    assert len(payload["columns"]) == 11
    score_column = next(column for column in payload["columns"] if column["column"] == "score")
    assert score_column["missing_count"] == 1
    assert "missing_values" in score_column["issues"]


def test_dashboard_aggregates_requested_dimension_and_metric(client: TestClient) -> None:
    response = client.get(
        "/api/dashboard",
        params={"dimension": "source", "metric": "revenue", "aggregation": "sum"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["dimension"] == "source"
    assert payload["metric"] == "revenue"
    assert payload["aggregation"] == "sum"
    assert payload["chart_type"] == "bar"
    assert {"label", "value"} <= set(payload["data"][0])

    invalid = client.get("/api/dashboard", params={"dimension": "does_not_exist"})
    assert invalid.status_code == 422


def test_ai_endpoints_use_deterministic_fallback_without_key(client: TestClient) -> None:
    summary = client.post("/api/ai-summary", json={"focus": "qualité"})
    assert summary.status_code == 200
    assert summary.json()["mode"] == "fallback"
    assert summary.json()["provider"] == "local-fallback"
    assert "15 lignes" in summary.json()["summary"]

    answer = client.post("/api/ask", json={"question": "Combien de valeurs manquantes ?"})
    assert answer.status_code == 200
    assert answer.json()["mode"] == "fallback"
    assert "1 valeur" in answer.json()["answer"]
    assert client.post("/api/ask", json={"question": ""}).status_code == 422
    assert client.post("/api/ask", json={"question": "   "}).status_code == 422


def test_anomalies_are_explained_with_original_values(client: TestClient) -> None:
    response = client.get("/api/anomalies")
    assert response.status_code == 200
    payload = response.json()
    assert payload["method"] == "IsolationForest"
    assert payload["count"] == len(payload["rows"])
    assert 0 <= payload["rate"] <= 100
    if payload["rows"]:
        row = payload["rows"][0]
        assert {"row_index", "anomaly_score", "contributing_columns", "values"} <= set(row)
        assert row["contributing_columns"]


def test_csv_upload_is_validated_saved_and_activated(client: TestClient) -> None:
    csv_content = (
        b"segment,amount,event_date\n"
        b"Enterprise,100,2026-01-01\nSMB,30,2026-01-02\n"
        b"Enterprise,120,2026-02-01\nSMB,45,2026-02-02\nEnterprise,500,2026-03-01\n"
    )
    upload = client.post(
        "/api/upload",
        files={"file": ("../../sales.csv", csv_content, "text/csv")},
    )
    assert upload.status_code == 200
    assert upload.json()["dataset_id"] == upload.json()["dataset"]["id"]
    assert upload.json()["dataset"]["name"] == "Sales"
    assert upload.json()["dataset"]["source"] == "upload"

    overview = client.get("/api/overview").json()
    assert overview["dataset"]["rows"] == 5
    assert overview["dataset"]["id"] == upload.json()["dataset"]["id"]
    dashboard = client.get(
        "/api/dashboard",
        params={"dimension": "segment", "metric": "amount", "aggregation": "sum"},
    ).json()
    enterprise = next(item for item in dashboard["data"] if item["label"] == "Enterprise")
    assert enterprise["value"] == 720


def test_excel_upload_and_upload_security(client: TestClient, settings: Settings) -> None:
    stream = BytesIO()
    pd.DataFrame({"team": ["A", "B"], "value": [1, 2]}).to_excel(stream, index=False)
    excel = client.post(
        "/api/upload",
        files={
            "file": (
                "teams.xlsx",
                stream.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert excel.status_code == 200
    assert excel.json()["dataset"]["rows"] == 2
    unsupported = client.post(
        "/api/upload", files={"file": ("script.exe", b"not a dataset", "application/octet-stream")}
    )
    assert unsupported.status_code == 415
    corrupt_excel = client.post(
        "/api/upload",
        files={
            "file": (
                "broken.xlsx",
                b"not an Excel archive",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert corrupt_excel.status_code == 422
    duplicate_headers = client.post(
        "/api/upload",
        files={"file": ("duplicates.csv", b"name,name\nA,B\n", "text/csv")},
    )
    assert duplicate_headers.status_code == 422
    duplicate_excel_stream = BytesIO()
    pd.DataFrame([["A", "B"]], columns=["name", "name"]).to_excel(
        duplicate_excel_stream, index=False
    )
    duplicate_excel_headers = client.post(
        "/api/upload",
        files={
            "file": (
                "duplicates.xlsx",
                duplicate_excel_stream.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert duplicate_excel_headers.status_code == 422
    oversized = client.post(
        "/api/upload",
        files={"file": ("large.csv", b"a\n" + b"1\n" * 10_000, "text/csv")},
    )
    assert oversized.status_code == 413
    assert not (settings.uploads_dir / "script.exe").exists()


def test_report_is_persisted_and_history_lists_completed_actions(
    client: TestClient, settings: Settings
) -> None:
    report = client.post("/api/report", json={"format": "html"})
    assert report.status_code == 200
    payload = report.json()
    assert payload["format"] == "html"
    assert payload["content"].startswith("<!doctype html>")
    assert (settings.reports_dir / payload["filename"]).read_text(encoding="utf-8") == payload["content"]

    markdown = client.post("/api/report", json={"format": "markdown"})
    assert markdown.status_code == 200
    assert markdown.json()["content"].startswith("# Rapport Data & IA")
    assert (settings.reports_dir / markdown.json()["filename"]).is_file()

    history = client.get("/api/history")
    assert history.status_code == 200
    items = history.json()["items"]
    assert items
    assert items[0]["action"] == "report_generated"
    assert items[0]["status"] == "completed"
    assert items[0]["details"]["filename"] == markdown.json()["filename"]

    # La base reste lisible après reconstruction complète de l'application.
    with TestClient(create_app(settings)) as restarted_client:
        persisted = restarted_client.get("/api/history").json()["items"]
    assert persisted[0]["details"]["filename"] == markdown.json()["filename"]


def test_dashboard_supports_numeric_only_datasets(client: TestClient) -> None:
    upload = client.post(
        "/api/upload",
        files={
            "file": (
                "numeric.csv",
                b"x,y\n1,10\n2,20\n3,30\n4,40\n5,50\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 200
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["dimension"] == "x"
    assert dashboard.json()["metric"] == "y"
    assert dashboard.json()["data"]

    single_column = b"x\n" + b"".join(f"{value}\n".encode() for value in range(1, 41))
    assert client.post(
        "/api/upload",
        files={"file": ("single-numeric.csv", single_column, "text/csv")},
    ).status_code == 200
    single_dashboard = client.get("/api/dashboard")
    assert single_dashboard.status_code == 200
    assert single_dashboard.json()["metric"] == "__row_count__"
    assert single_dashboard.json()["data"]
    same_dimension_metric = client.get(
        "/api/dashboard",
        params={"dimension": "x", "metric": "x", "aggregation": "sum"},
    )
    assert same_dimension_metric.status_code == 200


def test_real_count_column_does_not_collide_with_row_count(client: TestClient) -> None:
    upload = client.post(
        "/api/upload",
        files={
            "file": (
                "counts.csv",
                b"category,count\nA,10\nA,20\nB,5\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 200
    response = client.get(
        "/api/dashboard",
        params={"dimension": "category", "metric": "count", "aggregation": "sum"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["metric_options"].count("count") == 1
    assert "__row_count__" in payload["metric_options"]
    values = {item["label"]: item["value"] for item in payload["data"]}
    assert values == {"A": 30.0, "B": 5.0}


def test_conversion_kpi_accepts_decimal_or_percent_encoding(client: TestClient) -> None:
    upload = client.post(
        "/api/upload",
        files={
            "file": (
                "conversion.csv",
                b"segment,conversion\nA,50\nB,60\nC,50\nD,60\nE,55\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 200
    overview = client.get("/api/overview").json()
    conversion = next(kpi for kpi in overview["kpis"] if kpi["id"] == "conversion_rate")
    assert conversion["value"] == 55.0


def test_anomaly_non_applicability_is_explicit_everywhere(client: TestClient) -> None:
    upload = client.post(
        "/api/upload",
        files={"file": ("small.csv", b"category\nA\nB\nC\n", "text/csv")},
    )
    assert upload.status_code == 200

    anomalies = client.get("/api/anomalies").json()
    assert anomalies["applicable"] is False
    summary = client.post("/api/ai-summary", json={}).json()
    assert "n'est pas applicable" in summary["summary"]
    report = client.post("/api/report", json={"format": "markdown"}).json()
    assert "non applicable" in report["content"]

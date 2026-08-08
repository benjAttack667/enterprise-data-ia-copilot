"""Tests de non-régression pour les datasets valides mais atypiques."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _upload_csv(client: TestClient, filename: str, content: bytes) -> None:
    response = client.post(
        "/api/upload",
        files={"file": (filename, content, "text/csv")},
    )
    assert response.status_code == 200, response.text


def test_numeric_only_dashboard_uses_numeric_dimensions_and_a_distinct_metric(
    client: TestClient,
) -> None:
    _upload_csv(
        client,
        "numeric-only.csv",
        b"x,y\n1,10\n2,20\n3,30\n4,40\n5,50\n",
    )

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dimension_options"] == ["x", "y"]
    assert payload["dimension"] == "x"
    assert payload["metric"] == "y"
    assert {point["label"]: point["value"] for point in payload["data"]} == {
        "1": 10.0,
        "2": 20.0,
        "3": 30.0,
        "4": 40.0,
        "5": 50.0,
    }


def test_real_count_column_remains_aggregatable_next_to_row_count_metric(
    client: TestClient,
) -> None:
    _upload_csv(
        client,
        "business-count.csv",
        b"category,count\nA,10\nA,20\nB,5\n",
    )

    business_metric = client.get(
        "/api/dashboard",
        params={"dimension": "category", "metric": "count", "aggregation": "sum"},
    )
    row_count = client.get(
        "/api/dashboard",
        params={"dimension": "category", "metric": "__row_count__"},
    )

    assert business_metric.status_code == 200
    assert row_count.status_code == 200
    business_payload = business_metric.json()
    row_count_payload = row_count.json()
    assert business_payload["metric_options"] == ["__row_count__", "count"]
    assert {point["label"]: point["value"] for point in business_payload["data"]} == {
        "A": 30.0,
        "B": 5.0,
    }
    assert {point["label"]: point["value"] for point in row_count_payload["data"]} == {
        "A": 2.0,
        "B": 1.0,
    }


@pytest.mark.parametrize(
    ("values", "expected_percentage"),
    [
        ([0.50, 0.60, 0.50, 0.60, 0.55], 55.0),
        ([50, 60, 50, 60, 55], 55.0),
    ],
    ids=["decimal-ratio", "already-percent"],
)
def test_conversion_kpi_normalises_only_decimal_ratios(
    client: TestClient,
    values: list[float],
    expected_percentage: float,
) -> None:
    rows = "\n".join(
        f"segment-{index},{value}" for index, value in enumerate(values, start=1)
    )
    _upload_csv(
        client,
        "conversion.csv",
        f"segment,conversion\n{rows}\n".encode(),
    )

    response = client.get("/api/overview")

    assert response.status_code == 200
    conversion = next(
        kpi for kpi in response.json()["kpis"] if kpi["id"] == "conversion_rate"
    )
    assert conversion["value"] == expected_percentage
    assert conversion["unit"] == "%"


@pytest.mark.parametrize(
    ("filename", "content", "expected_numeric_columns"),
    [
        ("too-small.csv", b"x\n1\n2\n3\n4\n", ["x"]),
        (
            "no-numeric.csv",
            b"category,status\nA,open\nB,closed\nC,open\nD,closed\nE,open\n",
            [],
        ),
    ],
    ids=["fewer-than-five-rows", "no-numeric-column"],
)
def test_non_applicable_anomalies_are_propagated_to_all_consumers(
    client: TestClient,
    filename: str,
    content: bytes,
    expected_numeric_columns: list[str],
) -> None:
    _upload_csv(client, filename, content)

    anomaly_response = client.get("/api/anomalies")
    overview_response = client.get("/api/overview")
    summary_response = client.post("/api/ai-summary", json={})
    answer_response = client.post(
        "/api/ask", json={"question": "Quelles anomalies ont été détectées ?"}
    )
    markdown_response = client.post("/api/report", json={"format": "markdown"})
    html_response = client.post("/api/report", json={"format": "html"})

    for response in (
        anomaly_response,
        overview_response,
        summary_response,
        answer_response,
        markdown_response,
        html_response,
    ):
        assert response.status_code == 200, response.text

    anomalies = anomaly_response.json()
    assert anomalies["applicable"] is False
    assert anomalies["count"] == 0
    assert anomalies["rows"] == []
    assert anomalies["numeric_columns"] == expected_numeric_columns

    anomaly_kpi = next(
        kpi for kpi in overview_response.json()["kpis"] if kpi["id"] == "anomalies"
    )
    assert anomaly_kpi["value"] == "—"
    assert anomaly_kpi["tone"] == "neutral"
    assert "non applicable" in anomaly_kpi["hint"].casefold()
    assert "n'est pas applicable" in summary_response.json()["summary"].casefold()
    assert "n'est pas applicable" in answer_response.json()["answer"].casefold()
    assert "non applicable" in markdown_response.json()["content"].casefold()
    assert "non applicable" in html_response.json()["content"].casefold()

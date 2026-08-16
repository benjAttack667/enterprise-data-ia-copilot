"""Tests d'acceptation des sémantiques de données de la partie 3.

Ces tests privilégient les contrats observables : une donnée acceptée doit
rester analysable, les absences ne doivent pas devenir des zéros métier et les
réponses doivent être sérialisables en JSON strict.
"""

from __future__ import annotations

import json
import warnings
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.src.analytics import build_dashboard, build_overview
from backend.src.anomalies import detect_anomalies
from backend.src.dataset_store import DatasetSnapshot
from backend.src.quality import audit_data_quality
from backend.src.reporting import ReportService
from backend.src.serialization import json_value


def _assert_strict_json(payload: Any) -> None:
    """Reject NaN, infinity and Pandas objects unsupported by JSON."""

    json.dumps(payload, ensure_ascii=False, allow_nan=False)


def _column_quality(payload: dict[str, Any], column: str) -> dict[str, Any]:
    return next(item for item in payload["columns"] if item["column"] == column)


def _snapshot(dataframe: pd.DataFrame) -> DatasetSnapshot:
    return DatasetSnapshot(
        id="semantic-test",
        name="Semantic Test",
        source="test",
        updated_at="2026-08-10T00:00:00+00:00",
        context="Tests",
        dataframe=dataframe,
    )


def test_json_value_serializes_nat_and_timedelta_to_native_json_values() -> None:
    assert json_value(pd.NaT) is None

    duration = json_value(pd.Timedelta(days=1, hours=2, minutes=3))

    assert isinstance(duration, str)
    assert duration
    _assert_strict_json({"missing_date": json_value(pd.NaT), "duration": duration})


def test_mixed_timezone_dates_remain_aggregatable() -> None:
    dataframe = pd.DataFrame(
        {
            "event_date": [
                "2024-01-15",
                "2024-02-15T12:00:00+01:00",
                "2024-03-15T12:00:00Z",
                "2024-04-15",
                "2024-05-15T12:00:00-04:00",
            ],
            "amount": [10, 20, 30, 40, 50],
        }
    )

    payload = build_dashboard(
        dataframe,
        dimension="event_date",
        metric="amount",
        aggregation="sum",
    )

    assert payload["chart_type"] == "line"
    assert payload["series_kind"] == "temporal"
    assert {point["label"]: point["value"] for point in payload["data"]} == {
        "2024-01": 10.0,
        "2024-02": 20.0,
        "2024-03": 30.0,
        "2024-04": 40.0,
        "2024-05": 50.0,
    }
    _assert_strict_json(payload)


def test_numeric_year_dimension_is_not_interpreted_as_unix_nanoseconds() -> None:
    dataframe = pd.DataFrame(
        {
            "year": [2022, 2023, 2024, 2025, 2026],
            "sales": [10, 20, 30, 40, 50],
        }
    )

    payload = build_dashboard(
        dataframe,
        dimension="year",
        metric="sales",
        aggregation="sum",
    )

    labels = [point["label"] for point in payload["data"]]
    assert len(labels) == 5
    assert not any("1970" in label for label in labels)
    assert all(any(str(year) in label for label in labels) for year in range(2022, 2027))
    assert sorted(point["value"] for point in payload["data"]) == [
        10.0,
        20.0,
        30.0,
        40.0,
        50.0,
    ]


def test_datetime_dtype_with_neutral_name_is_a_temporal_series() -> None:
    dataframe = pd.DataFrame(
        {
            "when": pd.to_datetime(
                [
                    "2024-01-01",
                    "2024-01-15",
                    "2024-02-01",
                    "2024-02-15",
                    "2024-03-01",
                ]
            ),
            "amount": [1, 4, 2, 5, 3],
        }
    )

    dashboard = build_dashboard(
        dataframe,
        dimension="when",
        metric="amount",
        aggregation="sum",
    )
    overview = build_overview(_snapshot(dataframe))

    assert dashboard["chart_type"] == "line"
    assert dashboard["series_kind"] == "temporal"
    assert dashboard["data"] == [
        {"label": "2024-01", "value": 5.0},
        {"label": "2024-02", "value": 7.0},
        {"label": "2024-03", "value": 3.0},
    ]
    assert overview["series_kind"] == "temporal"
    assert overview["trend_series_kind"] == "temporal"
    assert overview["trend_meta"]["series_kind"] == "temporal"


def test_french_day_first_dates_are_grouped_deterministically() -> None:
    dataframe = pd.DataFrame(
        {
            "event_date": [
                "01/02/2024",
                "15/02/2024",
                "01/03/2024",
                "15/03/2024",
                "01/04/2024",
            ],
            "amount": [1, 1, 1, 1, 1],
        }
    )

    payload = build_dashboard(
        dataframe,
        dimension="event_date",
        metric="amount",
        aggregation="sum",
    )

    assert payload["series_kind"] == "temporal"
    assert payload["data"] == [
        {"label": "2024-02", "value": 2.0},
        {"label": "2024-03", "value": 2.0},
        {"label": "2024-04", "value": 1.0},
    ]


def test_fully_ambiguous_dates_are_reported_without_us_interpretation(
    client: TestClient,
) -> None:
    content = (
        b"event_date,amount\n"
        b"01/02/2024,1\n"
        b"03/04/2024,2\n"
        b"05/06/2024,3\n"
        b"07/08/2024,4\n"
        b"09/10/2024,5\n"
    )

    upload = client.post(
        "/api/upload",
        files={"file": ("ambiguous-dates.csv", content, "text/csv")},
    )
    quality = client.get("/api/data-quality")
    dashboard = client.get(
        "/api/dashboard",
        params={
            "dimension": "event_date",
            "metric": "amount",
            "aggregation": "sum",
        },
    )

    assert upload.status_code == 200, upload.text
    assert quality.status_code == 200, quality.text
    date_quality = _column_quality(quality.json(), "event_date")
    assert date_quality["ambiguous_count"] == 5
    assert date_quality["invalid_count"] == 5
    assert "invalid_dates" in date_quality["issues"]
    assert any("date" in problem.casefold() for problem in quality.json()["problems"])

    assert dashboard.status_code in {200, 422}, dashboard.text
    if dashboard.status_code == 200:
        payload = dashboard.json()
        assert payload["series_kind"] == "categorical"
        assert {point["label"] for point in payload["data"]} == {
            "01/02/2024",
            "03/04/2024",
            "05/06/2024",
            "07/08/2024",
            "09/10/2024",
        }
    else:
        assert "date" in dashboard.json()["detail"].casefold()


@pytest.mark.parametrize("dimension", ["candidate", "lifetime"])
def test_substrings_date_and_time_do_not_make_business_dimensions_temporal(
    dimension: str,
) -> None:
    dataframe = pd.DataFrame(
        {
            dimension: ["Alpha", "Beta", "Alpha", "Gamma", "Beta"],
            "amount": [1, 2, 3, 4, 5],
        }
    )

    payload = build_dashboard(
        dataframe,
        dimension=dimension,
        metric="amount",
        aggregation="sum",
    )

    assert payload["chart_type"] == "bar"
    assert payload["series_kind"] == "categorical"
    assert {point["label"]: point["value"] for point in payload["data"]} == {
        "Alpha": 4.0,
        "Beta": 7.0,
        "Gamma": 4.0,
    }
    overview = build_overview(_snapshot(dataframe))
    assert overview["series_kind"] == "categorical"
    assert overview["trend_series_kind"] == "categorical"
    assert overview["trend_meta"]["series_kind"] == "categorical"


def test_quality_distinguishes_invalid_dates_from_blank_dates() -> None:
    dataframe = pd.DataFrame(
        {
            "event_date": [
                "2024-01-01",
                "not-a-date",
                "   ",
                None,
                "2024-02-01",
            ],
            "amount": [1, 2, 3, 4, 5],
        }
    )

    payload = audit_data_quality(dataframe)
    column = _column_quality(payload, "event_date")

    assert column["missing_count"] == 2
    assert column["blank_count"] == 1
    assert column["invalid_count"] == 1
    assert "missing_values" in column["issues"]
    assert "invalid_dates" in column["issues"]
    assert column["semantic_type"] in {"date", "datetime"}
    assert 60 <= column["parse_rate"] <= 70
    assert payload["summary"]["blank_count"] == 1
    assert payload["summary"]["invalid_date_count"] == 1
    assert payload["summary"]["invalid_semantic_count"] == 1
    assert payload["score"] < 100
    assert any("date" in problem.casefold() for problem in payload["problems"])
    _assert_strict_json(payload)


def test_fully_invalid_date_hint_falls_back_to_a_non_empty_categorical_series() -> None:
    dataframe = pd.DataFrame(
        {
            "event_date": ["never", "invalid", "unknown", "later", "pending"],
            "amount": [1, 2, 3, 4, 5],
        }
    )

    quality = audit_data_quality(dataframe)
    date_quality = _column_quality(quality, "event_date")
    dashboard = build_dashboard(
        dataframe,
        dimension="event_date",
        metric="amount",
        aggregation="sum",
    )

    assert date_quality["invalid_count"] == 5
    assert "invalid_dates" in date_quality["issues"]
    assert dashboard["series_kind"] == "categorical"
    assert dashboard["chart_type"] == "bar"
    assert len(dashboard["data"]) == 5
    assert {point["value"] for point in dashboard["data"]} == {
        1.0,
        2.0,
        3.0,
        4.0,
        5.0,
    }
    _assert_strict_json({"quality": quality, "dashboard": dashboard})


def test_entirely_missing_numeric_aggregate_is_null_instead_of_zero() -> None:
    dataframe = pd.DataFrame(
        {
            "category": ["A", "A", "B", "B"],
            "amount": [np.nan, np.nan, np.nan, np.nan],
        }
    )

    payload = build_dashboard(
        dataframe,
        dimension="category",
        metric="amount",
        aggregation="sum",
    )

    assert payload["data"]
    assert all(point["value"] is None for point in payload["data"])
    _assert_strict_json(payload)


def test_real_missing_value_label_does_not_collide_with_missing_bucket() -> None:
    dataframe = pd.DataFrame(
        {
            "category": ["Valeur manquante", None, "Valeur manquante", None],
            "amount": [10, 20, 5, 7],
        }
    )

    payload = build_dashboard(
        dataframe,
        dimension="category",
        metric="amount",
        aggregation="sum",
    )

    assert len(payload["data"]) == 2
    assert len({point["label"] for point in payload["data"]}) == 2
    assert {point["value"] for point in payload["data"]} == {15.0, 27.0}
    real_category = next(
        point for point in payload["data"] if point["label"] == "Valeur manquante"
    )
    assert real_category["value"] == 15.0
    assert payload["missing_label"] != "Valeur manquante"
    missing_bucket = next(
        point for point in payload["data"] if point["label"] == payload["missing_label"]
    )
    assert missing_bucket["value"] == 27.0


@pytest.mark.parametrize(
    ("extension", "content_type"),
    [
        ("csv", "text/csv"),
        (
            "xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    ],
)
def test_import_preserves_business_na_labels_and_only_blanks_are_missing(
    client: TestClient,
    extension: str,
    content_type: str,
) -> None:
    source = pd.DataFrame(
        {
            "category": ["NA", "N/A", "NULL", "", "   "],
            "amount": [1, 2, 3, 4, 5],
        }
    )
    if extension == "csv":
        content = source.to_csv(index=False).encode("utf-8")
    else:
        stream = BytesIO()
        source.to_excel(stream, index=False)
        content = stream.getvalue()

    upload = client.post(
        "/api/upload",
        files={"file": (f"semantic.{extension}", content, content_type)},
    )
    quality = client.get("/api/data-quality")
    dashboard = client.get(
        "/api/dashboard",
        params={"dimension": "category", "metric": "amount", "aggregation": "sum"},
    )

    assert upload.status_code == 200, upload.text
    assert quality.status_code == 200, quality.text
    assert dashboard.status_code == 200, dashboard.text
    quality_payload = quality.json()
    category = _column_quality(quality_payload, "category")
    assert category["missing_count"] == 2
    assert category["blank_count"] == 2
    assert category["unique_count"] == 3

    dashboard_payload = dashboard.json()
    values = {point["label"]: point["value"] for point in dashboard_payload["data"]}
    assert values["NA"] == 1.0
    assert values["N/A"] == 2.0
    assert values["NULL"] == 3.0
    assert values[dashboard_payload["missing_label"]] == 9.0
    assert len(values) == 4


def test_numeric_strings_are_usable_by_isolation_forest() -> None:
    dataframe = pd.DataFrame(
        {
            "amount": [str(value) for value in range(1, 20)] + ["1000"],
            "segment": [f"segment-{value}" for value in range(1, 21)],
        }
    )

    payload = detect_anomalies(dataframe)

    assert payload["applicable"] is True
    assert "amount" in payload["numeric_columns"]
    assert payload["total_count"] == payload["count"]
    assert payload["returned_count"] == len(payload["rows"])
    assert payload["returned_count"] <= 100
    assert payload["truncated"] is (payload["total_count"] > payload["returned_count"])
    assert payload["count"] >= 1
    assert any(row["row_index"] == 20 for row in payload["rows"])
    _assert_strict_json(payload)


def test_mostly_numeric_text_has_one_invalid_value_but_remains_analysable() -> None:
    dataframe = pd.DataFrame(
        {
            "amount": [str(value) for value in range(1, 10)] + ["oops"],
            "category": [f"category-{value}" for value in range(1, 11)],
        }
    )

    quality = audit_data_quality(dataframe)
    amount = _column_quality(quality, "amount")
    dashboard = build_dashboard(
        dataframe,
        dimension="category",
        metric="amount",
        aggregation="sum",
    )
    anomalies = detect_anomalies(dataframe)

    assert amount["semantic_type"] == "number"
    assert amount["inferred_type"] == "number"
    assert amount["parse_rate"] == 90.0
    assert amount["invalid_count"] == 1
    assert "invalid_numeric_values" in amount["issues"]
    assert quality["summary"]["invalid_semantic_count"] == 1
    assert "amount" in dashboard["metric_options"]
    assert "amount" in anomalies["numeric_columns"]
    assert anomalies["applicable"] is True
    _assert_strict_json({
        "quality": quality,
        "dashboard": dashboard,
        "anomalies": anomalies,
    })


def test_neutral_numeric_text_is_not_inferred_as_a_date_series() -> None:
    dataframe = pd.DataFrame(
        {
            "category": ["A", "B", "C", "D", "E"],
            "amount": ["2000", "2001", "2002", "2003", "2004"],
        }
    )

    quality = audit_data_quality(dataframe)
    amount = _column_quality(quality, "amount")
    dashboard = build_dashboard(
        dataframe,
        dimension="category",
        metric="amount",
        aggregation="sum",
    )

    assert amount["semantic_type"] == "number"
    assert amount["inferred_type"] == "number"
    assert amount["invalid_count"] == 0
    assert "amount" in dashboard["metric_options"]
    assert dashboard["series_kind"] == "categorical"
    assert dashboard["chart_type"] == "bar"
    assert {point["label"]: point["value"] for point in dashboard["data"]} == {
        "A": 2000.0,
        "B": 2001.0,
        "C": 2002.0,
        "D": 2003.0,
        "E": 2004.0,
    }


@pytest.mark.parametrize("identifier", ["id", "customer_id"])
def test_identifier_columns_are_excluded_from_isolation_forest(identifier: str) -> None:
    dataframe = pd.DataFrame(
        {
            identifier: list(range(1, 20)) + [999_999],
            "amount": [10] * 19 + [1_000],
        }
    )

    payload = detect_anomalies(dataframe)

    assert payload["applicable"] is True
    assert identifier not in payload["numeric_columns"]
    assert "amount" in payload["numeric_columns"]
    assert any(row["row_index"] == 20 for row in payload["rows"])


def test_extreme_finite_values_do_not_overflow_the_anomaly_pipeline() -> None:
    dataframe = pd.DataFrame(
        {
            "x": [1e308, -1e308, 1e308, -1e308, *range(1, 17)],
            "y": [-1e308, 1e308, -1e308, 1e308, *range(16, 0, -1)],
        }
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        payload = detect_anomalies(dataframe)

    assert isinstance(payload["applicable"], bool)
    assert 0 <= payload["rate"] <= 100
    _assert_strict_json(payload)


def test_anomaly_rows_normalize_missing_values_and_are_strict_json() -> None:
    dataframe = pd.DataFrame(
        {
            "signal": [0.0] * 19 + [1_000.0],
            "nullable_metric": [float(value) for value in range(1, 20)]
            + [np.nan],
            "event_date": [*pd.date_range("2024-01-01", periods=19), pd.NaT],
            "duration": pd.to_timedelta(range(20), unit="h"),
        }
    )
    original = dataframe.copy(deep=True)

    payload = detect_anomalies(dataframe)
    anomalous_row = next(row for row in payload["rows"] if row["row_index"] == 20)

    pd.testing.assert_frame_equal(dataframe, original)
    assert anomalous_row["values"]["nullable_metric"] is None
    assert anomalous_row["values"]["event_date"] is None
    assert isinstance(anomalous_row["values"]["duration"], str)
    _assert_strict_json(payload)


def test_reports_render_missing_kpi_as_dash_instead_of_python_none(
    tmp_path: Path,
) -> None:
    overview = {
        "dataset": {
            "name": "Missing KPI",
            "source": "test",
            "context": "Tests",
            "rows": 2,
            "columns": 2,
        },
        "kpis": [
            {
                "id": "amount",
                "label": "Montant total",
                "value": None,
                "hint": "Toutes les valeurs sont absentes",
                "tone": "neutral",
            }
        ],
        "summary": "Le KPI ne contient aucune valeur exploitable.",
    }
    quality = {
        "score": 75.0,
        "problems": ["Les montants sont absents."],
        "recommendations": ["Compléter les montants."],
    }
    anomalies = {
        "applicable": False,
        "count": 0,
        "rate": 0.0,
        "message": "Données numériques insuffisantes.",
    }
    service = ReportService(tmp_path / "reports")

    markdown = service.generate("markdown", overview, quality, anomalies)["content"]
    html = service.generate("html", overview, quality, anomalies)["content"]

    for content in (markdown, html):
        assert "None" not in content
        assert "—" in content

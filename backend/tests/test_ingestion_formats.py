"""Acceptance tests for identifier semantics and robust CSV/XLSX ingestion.

The suite exercises the public upload contract whenever possible.  It also
checks the shared identifier helper directly so quality and anomaly consumers
cannot silently drift back to their former, name-specific heuristics.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from openpyxl.chart import BarChart

from backend.src.config import Settings
from backend.src.profiling import is_identifier_name
from backend.src.quality import audit_data_quality


CSV_MIME = "text/csv"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _upload_csv(
    client: TestClient,
    content: bytes,
    *,
    filename: str = "dataset.csv",
    sheet_name: str | None = None,
) -> Response:
    data = {} if sheet_name is None else {"sheet_name": sheet_name}
    return client.post(
        "/api/upload",
        data=data,
        files={"file": (filename, content, CSV_MIME)},
    )


def _xlsx_bytes(
    sheets: dict[str, pd.DataFrame],
    *,
    hidden_sheets: tuple[str, ...] = (),
    chart_sheets: tuple[str, ...] = (),
) -> bytes:
    stream = BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        for sheet_name, dataframe in sheets.items():
            dataframe.to_excel(writer, sheet_name=sheet_name, index=False)
        for sheet_name in hidden_sheets:
            writer.book[sheet_name].sheet_state = "hidden"
        for sheet_name in chart_sheets:
            chartsheet = writer.book.create_chartsheet(sheet_name)
            chartsheet.add_chart(BarChart())
    return stream.getvalue()


def _upload_xlsx(
    client: TestClient,
    content: bytes,
    *,
    filename: str = "workbook.xlsx",
    sheet_name: str | None = None,
) -> Response:
    data = {} if sheet_name is None else {"sheet_name": sheet_name}
    return client.post(
        "/api/upload",
        data=data,
        files={"file": (filename, content, XLSX_MIME)},
    )


def _active_frame(client: TestClient) -> pd.DataFrame:
    return client.app.state.dataset_store.get_active().dataframe


def _retained_uploads(uploads_dir: Path) -> set[Path]:
    return {
        path
        for pattern in ("*.csv", "*.xlsx")
        for path in uploads_dir.glob(pattern)
    }


@pytest.mark.parametrize(
    "column_name",
    ["customerId", "customer-id", "user_code", "account_number"],
)
def test_supported_identifier_variants_share_duplicate_semantics(
    column_name: str,
) -> None:
    dataframe = pd.DataFrame(
        {
            column_name: [101, 101, 202],
            "row_marker": [1, 2, 3],
        }
    )

    quality = audit_data_quality(dataframe)
    column = next(item for item in quality["columns"] if item["column"] == column_name)

    assert is_identifier_name(column_name) is True
    assert column["semantic_type"] == "identifier"
    assert quality["summary"]["strict_duplicate_count"] == 0
    assert quality["summary"]["identifier_duplicate_count"] == 1
    assert quality["summary"]["duplicate_count"] == 1


@pytest.mark.parametrize(
    ("column_name", "values", "expected_type"),
    [
        ("country_code", ["FR", "FR", "BE"], "categorical"),
        ("status_code", [200, 200, 500], "number"),
    ],
)
def test_business_codes_are_not_false_positive_identifiers(
    column_name: str,
    values: list[object],
    expected_type: str,
) -> None:
    dataframe = pd.DataFrame(
        {
            column_name: values,
            "row_marker": [1, 2, 3],
        }
    )

    quality = audit_data_quality(dataframe)
    column = next(item for item in quality["columns"] if item["column"] == column_name)

    assert is_identifier_name(column_name) is False
    assert column["semantic_type"] == expected_type
    assert quality["summary"]["strict_duplicate_count"] == 0
    assert quality["summary"]["identifier_duplicate_count"] == 0
    assert quality["summary"]["duplicate_count"] == 0


@pytest.mark.parametrize(
    ("delimiter", "embedded_value"),
    [
        (",", "Alpha,Beta"),
        (";", "Alpha;Beta"),
        ("\t", "Alpha\tBeta"),
    ],
    ids=["comma", "semicolon", "tab"],
)
def test_csv_delimiter_is_detected_without_splitting_quoted_fields(
    client: TestClient,
    delimiter: str,
    embedded_value: str,
) -> None:
    content = (
        f"label{delimiter}amount\n"
        f'"{embedded_value}"{delimiter}10\n'
        f"Plain{delimiter}20\n"
    ).encode("utf-8")

    response = _upload_csv(client, content)

    assert response.status_code == 200, response.text
    assert response.json()["dataset"]["rows"] == 2
    assert response.json()["dataset"]["columns"] == 2
    frame = _active_frame(client)
    assert list(frame.columns) == ["label", "amount"]
    assert frame.iloc[0].to_dict() == {"label": embedded_value, "amount": 10}


def test_csv_utf8_bom_is_removed_from_header_with_semicolon_detection(
    client: TestClient,
) -> None:
    content = "\ufeffcountry;amount\nFrance;10\nBelgique;20\n".encode("utf-8")

    response = _upload_csv(client, content, filename="bom-semicolon.csv")

    assert response.status_code == 200, response.text
    assert list(_active_frame(client).columns) == ["country", "amount"]
    assert _active_frame(client)["amount"].tolist() == [10, 20]


def test_ambiguous_csv_separator_is_rejected_atomically(
    client: TestClient,
    settings: Settings,
) -> None:
    # Both comma and semicolon produce two consistent columns: guessing would
    # silently corrupt half of the apparent structure.
    content = (
        b"name,amount;region\n"
        b"Alpha,10;Europe\n"
        b"Beta,20;Americas\n"
    )
    before = client.app.state.dataset_store.get_active()
    retained_before = _retained_uploads(settings.uploads_dir)

    response = _upload_csv(client, content, filename="ambiguous.csv")

    assert response.status_code == 422
    assert response.json()["detail"].startswith("S\u00e9parateur CSV ambigu")
    assert client.app.state.dataset_store.get_active().id == before.id
    assert _retained_uploads(settings.uploads_dir) == retained_before


def test_inconsistent_csv_separator_is_rejected_atomically(
    client: TestClient,
    settings: Settings,
) -> None:
    content = b"name,amount\nAlpha;10\nBeta,20\n"
    before = client.app.state.dataset_store.get_active()
    retained_before = _retained_uploads(settings.uploads_dir)

    response = _upload_csv(client, content, filename="inconsistent.csv")

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Structure CSV incoh\u00e9rente : chaque ligne doit utiliser le m\u00eame "
        "s\u00e9parateur et contenir le m\u00eame nombre de colonnes."
    )
    assert client.app.state.dataset_store.get_active().id == before.id
    assert _retained_uploads(settings.uploads_dir) == retained_before


def test_genuine_single_column_csv_remains_supported(client: TestClient) -> None:
    response = _upload_csv(client, b"label\nAlpha\nBeta\n", filename="labels.csv")

    assert response.status_code == 200, response.text
    assert response.json()["dataset"]["rows"] == 2
    assert response.json()["dataset"]["columns"] == 1
    assert _active_frame(client)["label"].tolist() == ["Alpha", "Beta"]


@pytest.mark.parametrize("delimiter", [",", ";", "\t"], ids=["comma", "semicolon", "tab"])
def test_duplicate_csv_headers_are_rejected_for_every_supported_delimiter(
    client: TestClient,
    delimiter: str,
) -> None:
    content = f"name{delimiter}name\nAlpha{delimiter}Beta\n".encode("utf-8")

    response = _upload_csv(client, content, filename="duplicate-headers.csv")

    assert response.status_code == 422
    assert "dupliqu" in response.json()["detail"].casefold()


def test_csv_rejects_excel_sheet_parameter_without_replacing_active_dataset(
    client: TestClient,
    settings: Settings,
) -> None:
    before = client.app.state.dataset_store.get_active()
    retained_before = _retained_uploads(settings.uploads_dir)

    response = _upload_csv(
        client,
        b"name,amount\nAlpha,10\n",
        sheet_name="Sheet1",
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Le param\u00e8tre sheet_name est r\u00e9serv\u00e9 aux fichiers XLSX."
    )
    assert client.app.state.dataset_store.get_active().id == before.id
    assert _retained_uploads(settings.uploads_dir) == retained_before


def test_single_sheet_xlsx_remains_backward_compatible_without_selection(
    client: TestClient,
) -> None:
    workbook = _xlsx_bytes(
        {"Data": pd.DataFrame({"team": ["A", "B"], "amount": [10, 20]})}
    )

    response = _upload_xlsx(client, workbook, filename="single-sheet.xlsx")

    assert response.status_code == 200, response.text
    assert response.json()["dataset"]["rows"] == 2
    assert list(_active_frame(client).columns) == ["team", "amount"]


def test_multi_sheet_xlsx_requires_selection_and_lists_available_sheets(
    client: TestClient,
    settings: Settings,
) -> None:
    workbook = _xlsx_bytes(
        {
            "Summary": pd.DataFrame({"metric": ["revenue"], "value": [30]}),
            "Details": pd.DataFrame({"team": ["A", "B"], "amount": [10, 20]}),
        }
    )
    before = client.app.state.dataset_store.get_active()
    retained_before = _retained_uploads(settings.uploads_dir)

    response = _upload_xlsx(client, workbook, filename="multi-sheet.xlsx")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "sheet_selection_required"
    assert detail["sheets"] == ["Summary", "Details"]
    assert detail["message"]
    assert client.app.state.dataset_store.get_active().id == before.id
    assert _retained_uploads(settings.uploads_dir) == retained_before


def test_valid_sheet_name_activates_only_the_selected_worksheet(
    client: TestClient,
) -> None:
    workbook = _xlsx_bytes(
        {
            "Summary": pd.DataFrame({"metric": ["revenue"], "value": [60]}),
            "Details": pd.DataFrame(
                {"team": ["A", "B", "C"], "amount": [10, 20, 30]}
            ),
        }
    )

    response = _upload_xlsx(
        client,
        workbook,
        filename="multi-sheet.xlsx",
        sheet_name="Details",
    )

    assert response.status_code == 200, response.text
    assert response.json()["dataset"]["rows"] == 3
    assert response.json()["dataset"]["columns"] == 2
    frame = _active_frame(client)
    assert list(frame.columns) == ["team", "amount"]
    assert frame["team"].tolist() == ["A", "B", "C"]


def test_invalid_sheet_name_returns_structured_error_without_activation(
    client: TestClient,
    settings: Settings,
) -> None:
    workbook = _xlsx_bytes(
        {
            "Summary": pd.DataFrame({"metric": ["revenue"], "value": [30]}),
            "Details": pd.DataFrame({"team": ["A", "B"], "amount": [10, 20]}),
        }
    )
    before = client.app.state.dataset_store.get_active()
    retained_before = _retained_uploads(settings.uploads_dir)

    response = _upload_xlsx(
        client,
        workbook,
        filename="multi-sheet.xlsx",
        sheet_name="Unknown",
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_sheet_name"
    assert detail["sheets"] == ["Summary", "Details"]
    assert detail["message"]
    assert client.app.state.dataset_store.get_active().id == before.id
    assert _retained_uploads(settings.uploads_dir) == retained_before


def test_sheet_titles_are_exact_and_hidden_worksheets_remain_selectable(
    client: TestClient,
) -> None:
    workbook = _xlsx_bytes(
        {
            " Summary ": pd.DataFrame({"metric": ["revenue"], "value": [60]}),
            "Hidden Data": pd.DataFrame(
                {"team": ["Alpha", "Beta"], "amount": [10, 20]}
            ),
        },
        hidden_sheets=("Hidden Data",),
    )

    selection = _upload_xlsx(client, workbook)
    assert selection.status_code == 409
    assert selection.json()["detail"]["sheets"] == [" Summary ", "Hidden Data"]

    trimmed_title = _upload_xlsx(client, workbook, sheet_name="Summary")
    assert trimmed_title.status_code == 422
    assert trimmed_title.json()["detail"]["code"] == "invalid_sheet_name"

    exact_title = _upload_xlsx(client, workbook, sheet_name=" Summary ")
    assert exact_title.status_code == 200, exact_title.text
    assert exact_title.json()["dataset"]["selected_sheet"] == " Summary "

    hidden = _upload_xlsx(client, workbook, sheet_name="Hidden Data")
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["dataset"]["selected_sheet"] == "Hidden Data"
    assert hidden.json()["dataset"]["rows"] == 2


def test_chart_sheets_are_not_offered_as_tabular_data(client: TestClient) -> None:
    workbook = _xlsx_bytes(
        {
            "Summary": pd.DataFrame({"metric": ["revenue"], "value": [60]}),
            "Details": pd.DataFrame({"team": ["Alpha"], "amount": [10]}),
        },
        chart_sheets=("Dashboard",),
    )

    selection = _upload_xlsx(client, workbook)

    assert selection.status_code == 409
    assert selection.json()["detail"]["sheets"] == ["Summary", "Details"]


def test_sheet_name_length_is_bounded_before_activation(
    client: TestClient,
    settings: Settings,
) -> None:
    workbook = _xlsx_bytes(
        {"Data": pd.DataFrame({"team": ["A", "B"], "amount": [10, 20]})}
    )
    before = client.app.state.dataset_store.get_active()
    retained_before = _retained_uploads(settings.uploads_dir)

    response = _upload_xlsx(client, workbook, sheet_name="x" * 129)

    assert response.status_code == 422
    assert client.app.state.dataset_store.get_active().id == before.id
    assert _retained_uploads(settings.uploads_dir) == retained_before


def test_dataset_store_two_argument_upload_wrapper_remains_compatible(
    client: TestClient,
) -> None:
    snapshot = client.app.state.dataset_store.activate_upload(
        "legacy.csv",
        b"category,amount\nA,10\nB,20\n",
    )

    assert snapshot.metadata()["rows"] == 2
    assert snapshot.metadata()["columns"] == 2
    assert list(snapshot.dataframe.columns) == ["category", "amount"]

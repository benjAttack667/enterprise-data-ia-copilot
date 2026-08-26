"""Small runtime fixture builders used by the real-browser ingestion tests."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook


def create_multi_sheet_workbook(destination: str) -> str:
    """Create a deterministic workbook without committing a binary fixture."""

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    summary = workbook.active
    summary.title = "Summary"
    summary.append(["metric", "value"])
    summary.append(["revenue", 60])

    details = workbook.create_sheet("Details")
    details.append(["team", "amount"])
    details.append(["Alpha", 10])
    details.append(["Beta", 20])
    details.append(["Gamma", 30])

    workbook.save(path)
    workbook.close()
    return str(path)

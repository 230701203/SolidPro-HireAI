"""CSV / XLSX export helpers.

Spreadsheet formula injection: a cell that starts with = + - @ (or tab / CR) is executed as a formula by Excel and
friends, and resume-derived text is attacker-controlled. Every text cell is therefore prefixed with an apostrophe.
"""

import csv
import io
from datetime import datetime

from fastapi.responses import Response

DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value):
    if isinstance(value, str) and value.startswith(DANGEROUS):
        return "'" + value
    if isinstance(value, (list, tuple)):
        return safe_cell(", ".join(str(v) for v in value))
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return value


def to_csv(headers: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([safe_cell(h) for h in headers])
    for r in rows:
        w.writerow([safe_cell(c) for c in r])
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM so Excel reads UTF-8


def to_xlsx(headers: list[str], rows: list[list], sheet: str = "Export") -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = sheet[:31]
    ws.append([safe_cell(h) for h in headers])
    for r in rows:
        ws.append([safe_cell(c) for c in r])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def respond(fmt: str, filename: str, headers: list[str], rows: list[list], sheet: str = "Export") -> Response:
    if fmt == "xlsx":
        return Response(
            to_xlsx(headers, rows, sheet), headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"', "Cache-Control": "no-store"},
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    return Response(
        to_csv(headers, rows), headers={"Content-Disposition": f'attachment; filename="{filename}.csv"', "Cache-Control": "no-store"},
        media_type="text/csv; charset=utf-8",
    )

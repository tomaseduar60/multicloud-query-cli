"""Formatos de salida: tabla para leer, json y csv para encadenar con otras herramientas."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from .runner import RegionResult


def _flatten(results: list[RegionResult]) -> list[dict[str, Any]]:
    return [{"region": r.region, **row} for r in results if r.ok for row in r.rows]


def to_json(results: list[RegionResult]) -> str:
    payload = [
        {"region": r.region, "ok": r.ok, "error": r.error, "elapsed_ms": r.elapsed_ms,
         "rows": r.rows}
        for r in results
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def to_csv(results: list[RegionResult]) -> str:
    rows = _flatten(results)
    columns: list[str] = []
    for row in rows:
        columns += [c for c in row if c not in columns]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def to_table(results: list[RegionResult], max_width: int = 40) -> str:
    rows = _flatten(results)
    lines: list[str] = []
    if rows:
        columns: list[str] = []
        for row in rows:
            columns += [c for c in row if c not in columns]
        cells = [[_cell(row.get(c), max_width) for c in columns] for row in rows]
        widths = [max(len(c), *(len(r[i]) for r in cells)) for i, c in enumerate(columns)]
        lines.append("  ".join(c.ljust(w) for c, w in zip(columns, widths, strict=True)))
        lines.append("  ".join("-" * w for w in widths))
        lines += ["  ".join(v.ljust(w) for v, w in zip(r, widths, strict=True)) for r in cells]
        lines.append("")
    for r in results:
        status = f"{len(r.rows)} filas" if r.ok else f"ERROR {r.error}"
        lines.append(f"[{r.region}] {status} ({r.elapsed_ms} ms)")
    return "\n".join(lines)


def _cell(value: Any, max_width: int) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str) if isinstance(
        value, dict | list
    ) else "" if value is None else str(value)
    return text if len(text) <= max_width else text[: max_width - 1] + "…"


FORMATTERS = {"table": to_table, "json": to_json, "csv": to_csv}

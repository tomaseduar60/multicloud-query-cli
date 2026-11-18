"""Ejecuta una query en una o varias regiones en paralelo.

Una región que falla no corta a las demás: cada resultado trae sus filas o su error.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from .engines import get_engine
from .engines.base import Rows
from .errors import QueryCliError, WriteNotAllowedError
from .queries import Query
from .regions import Region
from .render import render


@dataclass
class RegionResult:
    region: str
    rows: Rows = field(default_factory=list)
    error: str | None = None
    elapsed_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.error is None


def _run_one(
    query: Query, rendered: Any, region: Region, environ: dict[str, str] | None
) -> RegionResult:
    start = time.monotonic()
    try:
        credentials = region.credentials(query.engine, environ)
        rows = get_engine(query.engine).execute(query, rendered, credentials)
        result = RegionResult(region=region.name, rows=rows)
    except QueryCliError as exc:
        result = RegionResult(region=region.name, error=str(exc))
    except Exception as exc:  # errores del driver: se reportan por región
        result = RegionResult(region=region.name, error=f"{type(exc).__name__}: {exc}")
    result.elapsed_ms = int((time.monotonic() - start) * 1000)
    return result


def run(
    query: Query,
    params: dict[str, Any],
    regions: list[Region],
    *,
    allow_write: bool = False,
    environ: dict[str, str] | None = None,
    max_workers: int = 8,
) -> list[RegionResult]:
    if query.is_write and not allow_write:
        raise WriteNotAllowedError(
            f"'{query.name}' modifica datos ({query.operation}). Usá --allow-write para ejecutarla."
        )
    resolved = query.resolve_params(params)
    rendered = render(query, resolved)
    with ThreadPoolExecutor(max_workers=min(max_workers, len(regions) or 1)) as pool:
        futures = [pool.submit(_run_one, query, rendered, r, environ) for r in regions]
        return [f.result() for f in futures]

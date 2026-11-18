from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest

from query_cli.engines import register_engine
from query_cli.queries import Query
from query_cli.regions import Credentials

ROOT = Path(__file__).resolve().parents[1]


class FakeEngine:
    """Engine en memoria: devuelve lo que recibió para poder inspeccionarlo."""

    calls: ClassVar[list[tuple[str, Any, Credentials]]] = []
    fail_on: ClassVar[set[str]] = set()

    def execute(
        self, query: Query, rendered: Any, credentials: Credentials
    ) -> list[dict[str, Any]]:
        FakeEngine.calls.append((query.name, rendered, credentials))
        marker = next(iter(credentials.values.values()))
        if marker in FakeEngine.fail_on:
            raise RuntimeError("connection refused")
        return [{"source": marker, "n": 1}]


@pytest.fixture(autouse=True)
def fake_engines() -> FakeEngine:
    FakeEngine.calls = []
    FakeEngine.fail_on = set()
    register_engine("mongo", FakeEngine)
    register_engine("couchbase", FakeEngine)
    return FakeEngine()


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    values = {}
    for region in ("CAS", "CARIB", "SA"):
        values[f"MONGO_URI_{region}"] = f"mongo-{region.lower()}"
        values[f"COUCHBASE_CONNSTR_{region}"] = f"cb-{region.lower()}"
        values[f"COUCHBASE_USER_{region}"] = "user"
        values[f"COUCHBASE_PASSWORD_{region}"] = "secret"
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    return values


@pytest.fixture
def root() -> Path:
    return ROOT

from pathlib import Path

import pytest

from query_cli.errors import ConfigError, ParamError
from query_cli.queries import Param, load_queries, parse_query
from query_cli.render import render


def test_carga_todas_las_queries_de_ejemplo(root: Path) -> None:
    queries = load_queries(root / "queries")
    assert {"orders_by_status", "daily_sales", "cancel_stale_orders", "customer_profile",
            "sessions_by_app_version"} <= set(queries)
    assert queries["cancel_stale_orders"].is_write
    assert not queries["orders_by_status"].is_write


def test_todas_las_queries_renderizan_con_defaults(root: Path) -> None:
    samples = {"status": "PAID", "from": "2024-01-01", "to": "2024-01-31", "customer_id": "c-1"}
    for q in load_queries(root / "queries").values():
        given = {k: v for k, v in samples.items() if k in q.params}
        assert render(q, q.resolve_params(given)) is not None


def test_render_mongo(root: Path) -> None:
    q = load_queries(root / "queries")["orders_by_status"]
    out = render(q, q.resolve_params({"status": "PAID", "days": "3"}))
    assert out["filter"]["status"] == "PAID"
    assert out["filter"]["$expr"]["$gte"][1]["$dateSubtract"]["amount"] == 3
    assert out["limit"] == 100


def test_render_couchbase_usa_parametros_con_nombre(root: Path) -> None:
    q = load_queries(root / "queries")["customer_profile"]
    out = render(q, q.resolve_params({"customer_id": "abc"}))
    assert "$customer_id" in out["statement"]
    assert out["params"] == {"customer_id": "abc"}


def test_inyeccion_queda_como_string(root: Path) -> None:
    q = load_queries(root / "queries")["customer_profile"]
    evil = 'x", "admin": true, "y": "'
    out = render(q, q.resolve_params({"customer_id": evil}))
    assert out["params"] == {"customer_id": evil}


def test_lista_desde_texto(root: Path) -> None:
    q = load_queries(root / "queries")["daily_sales"]
    params = q.resolve_params({"from": "2024-01-01", "to": "2024-01-02", "channels": "app, pos"})
    out = render(q, params)
    assert out["pipeline"][0]["$match"]["channel"] == {"$in": ["app", "pos"]}


@pytest.mark.parametrize(
    ("kind", "raw", "expected"),
    [("int", "5", 5), ("float", "1.5", 1.5), ("bool", "sí", True), ("bool", "0", False),
     ("bool", True, True), ("date", "2024-02-03", "2024-02-03"), ("list", ["a"], ["a"]),
     ("str", 7, "7")],
)
def test_coercion(kind: str, raw: object, expected: object) -> None:
    assert Param(name="p", type=kind).coerce(raw) == expected


def test_errores_de_parametros(root: Path) -> None:
    q = load_queries(root / "queries")["orders_by_status"]
    with pytest.raises(ParamError, match="obligatorio"):
        q.resolve_params({})
    with pytest.raises(ParamError, match="uno de"):
        q.resolve_params({"status": "LOST"})
    with pytest.raises(ParamError, match="int"):
        q.resolve_params({"status": "PAID", "days": "siete"})
    with pytest.raises(ParamError, match="desconocidos"):
        q.resolve_params({"status": "PAID", "color": "rojo"})
    with pytest.raises(ParamError):
        Param(name="b", type="bool").coerce("quizás")


def test_definiciones_invalidas(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="engine"):
        parse_query("q", {"engine": "redis", "template": "x"})
    with pytest.raises(ConfigError, match="operación"):
        parse_query("q", {"engine": "mongo", "operation": "drop", "template": "x"})
    with pytest.raises(ConfigError, match="template"):
        parse_query("q", {"engine": "mongo"})
    with pytest.raises(ConfigError, match="Tipo"):
        parse_query("q", {"engine": "mongo", "template": "x", "params": {"a": "uuid"}})
    with pytest.raises(ConfigError):
        load_queries(tmp_path / "nada")


def test_plantilla_rota() -> None:
    q = parse_query("q", {"engine": "mongo", "template": "filter: {{ falta }}"})
    with pytest.raises(ConfigError, match="plantilla"):
        render(q, {})
    q2 = parse_query("q", {"engine": "mongo", "template": "a: [1, 2"})
    with pytest.raises(ConfigError, match="YAML"):
        render(q2, {})

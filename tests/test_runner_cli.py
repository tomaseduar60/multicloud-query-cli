import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from conftest import FakeEngine

from query_cli.cli import cli
from query_cli.errors import WriteNotAllowedError
from query_cli.output import to_csv, to_json, to_table
from query_cli.queries import load_queries
from query_cli.regions import load_regions, select_regions
from query_cli.runner import RegionResult, run


def _args(root: Path, *rest: str) -> list[str]:
    return [
        "--queries",
        str(root / "queries"),
        "--regions",
        str(root / "regions.yaml"),
        "--env-file",
        str(root / "no-env"),
        *rest,
    ]


def test_corre_en_cada_region_con_sus_credenciales(root: Path, env: dict[str, str]) -> None:
    q = load_queries(root / "queries")["orders_by_status"]
    regions = select_regions(load_regions(root / "regions.yaml"), ["all"])
    results = run(q, {"status": "PAID"}, regions)
    assert [r.region for r in results] == ["cas", "carib", "sa"]
    assert [r.rows[0]["source"] for r in results] == ["mongo-cas", "mongo-carib", "mongo-sa"]
    assert all(r.ok for r in results)


def test_una_region_caida_no_corta_las_demas(root: Path, env: dict[str, str]) -> None:
    FakeEngine.fail_on = {"mongo-carib"}
    q = load_queries(root / "queries")["orders_by_status"]
    regions = select_regions(load_regions(root / "regions.yaml"), ["all"])
    results = {r.region: r for r in run(q, {"status": "PAID"}, regions)}
    assert results["cas"].ok and results["sa"].ok
    assert results["carib"].error == "RuntimeError: connection refused"


def test_region_sin_credenciales_reporta_error(root: Path) -> None:
    q = load_queries(root / "queries")["orders_by_status"]
    regions = select_regions(load_regions(root / "regions.yaml"), ["cas"])
    [result] = run(q, {"status": "PAID"}, regions, environ={})
    assert not result.ok and "MONGO_URI_CAS" in (result.error or "")


def test_escritura_bloqueada_sin_flag(root: Path, env: dict[str, str]) -> None:
    q = load_queries(root / "queries")["cancel_stale_orders"]
    regions = select_regions(load_regions(root / "regions.yaml"), ["cas"])
    with pytest.raises(WriteNotAllowedError):
        run(q, {}, regions)
    assert run(q, {}, regions, allow_write=True)[0].ok


def test_formatos() -> None:
    results = [
        RegionResult("cas", [{"id": 1, "tags": ["a"]}], elapsed_ms=5),
        RegionResult("sa", error="timeout"),
    ]
    table = to_table(results)
    assert "region" in table and '["a"]' in table and "[sa] ERROR timeout" in table
    assert to_csv(results).splitlines()[0] == "region,id,tags"
    data = json.loads(to_json(results))
    assert data[1] == {"region": "sa", "ok": False, "error": "timeout", "elapsed_ms": 0, "rows": []}
    long = to_table([RegionResult("x", [{"v": "z" * 100}])], max_width=10)
    assert "zzzzzzzzz…" in long


def test_cli_list_y_show(root: Path) -> None:
    runner = CliRunner()
    out = runner.invoke(cli, _args(root, "list"))
    assert (
        out.exit_code == 0 and "cancel_stale_orders" in out.output and "[escritura]" in out.output
    )
    out = runner.invoke(cli, _args(root, "show", "orders_by_status"))
    assert out.exit_code == 0 and "-p status=<str>" in out.output and "PAID" in out.output


def test_cli_dry_run(root: Path) -> None:
    out = CliRunner().invoke(
        cli, _args(root, "run", "customer_profile", "--dry-run", "-p", "customer_id=42")
    )
    assert out.exit_code == 0
    assert json.loads(out.output)["params"] == {"customer_id": "42"}


def test_cli_run_multiregion_json(root: Path, env: dict[str, str]) -> None:
    out = CliRunner().invoke(
        cli,
        _args(
            root,
            "run",
            "customer_profile",
            "-r",
            "cas",
            "-r",
            "sa",
            "-p",
            "customer_id=1",
            "-o",
            "json",
        ),
    )
    assert out.exit_code == 0
    assert [r["region"] for r in json.loads(out.output)] == ["cas", "sa"]


def test_cli_run_con_error_sale_con_2(root: Path, env: dict[str, str]) -> None:
    FakeEngine.fail_on = {"mongo-sa"}
    out = CliRunner().invoke(
        cli, _args(root, "run", "orders_by_status", "-r", "sa", "-p", "status=PAID")
    )
    assert out.exit_code == 2 and "[sa] ERROR" in out.output


def test_cli_escritura_pide_confirmacion(root: Path, env: dict[str, str]) -> None:
    args = _args(root, "run", "cancel_stale_orders", "-r", "cas", "--allow-write")
    assert CliRunner().invoke(cli, args, input="n\n").exit_code == 1
    assert FakeEngine.calls == []
    assert CliRunner().invoke(cli, args, input="y\n").exit_code == 0
    assert len(FakeEngine.calls) == 1


def test_cli_param_mal_formado_y_query_inexistente(root: Path) -> None:
    out = CliRunner().invoke(cli, _args(root, "run", "customer_profile", "-p", "sinigual"))
    assert out.exit_code != 0 and "clave=valor" in out.output
    out = CliRunner().invoke(cli, _args(root, "show", "no_existe"))
    assert out.exit_code != 0

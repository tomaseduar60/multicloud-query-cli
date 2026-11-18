from pathlib import Path

import pytest

from query_cli.errors import ConfigError
from query_cli.regions import Region, load_regions, select_regions


def test_carga_las_tres_regiones(root: Path) -> None:
    regions = load_regions(root / "regions.yaml")
    assert list(regions) == ["cas", "carib", "sa"]
    assert regions["carib"].env_refs["mongo"] == {"uri": "MONGO_URI_CARIB"}


def test_cada_region_usa_sus_propias_credenciales(root: Path, env: dict[str, str]) -> None:
    regions = load_regions(root / "regions.yaml")
    assert regions["cas"].credentials("mongo").values == {"uri": "mongo-cas"}
    assert regions["sa"].credentials("mongo").values == {"uri": "mongo-sa"}
    cb = regions["carib"].credentials("couchbase").values
    assert cb == {"connstr": "cb-carib", "username": "user", "password": "secret"}


def test_falta_variable_dice_cual(root: Path) -> None:
    region = load_regions(root / "regions.yaml")["cas"]
    with pytest.raises(ConfigError, match="MONGO_URI_CAS"):
        region.credentials("mongo", environ={})


def test_engine_no_configurado() -> None:
    region = Region(name="x", env_refs={"mongo": {"uri": "X"}})
    with pytest.raises(ConfigError, match="couchbase"):
        region.credentials("couchbase", environ={"X": "1"})


def test_repr_no_expone_secretos(root: Path, env: dict[str, str]) -> None:
    creds = load_regions(root / "regions.yaml")["cas"].credentials("couchbase")
    assert "secret" not in repr(creds)


def test_select_all_y_desconocida(root: Path) -> None:
    regions = load_regions(root / "regions.yaml")
    assert [r.name for r in select_regions(regions, ["all"])] == ["cas", "carib", "sa"]
    assert [r.name for r in select_regions(regions, [])] == ["cas", "carib", "sa"]
    assert [r.name for r in select_regions(regions, ["sa"])] == ["sa"]
    with pytest.raises(ConfigError, match="mx"):
        select_regions(regions, ["mx"])


def test_archivo_invalido(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_regions(tmp_path / "no-existe.yaml")
    bad = tmp_path / "r.yaml"
    bad.write_text("regions: {}\n")
    with pytest.raises(ConfigError):
        load_regions(bad)
    bad.write_text("regions:\n  x:\n    description: sin engines\n")
    with pytest.raises(ConfigError, match="ningún engine"):
        load_regions(bad)
    bad.write_text("regions:\n  x:\n    mongo: [1, 2]\n")
    with pytest.raises(ConfigError, match="mapa"):
        load_regions(bad)

"""Regiones y sus credenciales.

Cada región apunta a sus propios clusters, con credenciales distintas. El archivo
regions.yaml solo guarda *nombres de variables de entorno*; los valores viven en el
entorno (o en un .env local que nunca se commitea). Así la configuración se puede
versionar y compartir sin exponer nada.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError

ENGINES = ("mongo", "couchbase")


@dataclass(frozen=True)
class Credentials:
    """Credenciales ya resueltas para un engine en una región."""

    engine: str
    values: dict[str, str]

    def __repr__(self) -> str:  # nunca imprimir secretos en logs ni tracebacks
        return f"Credentials(engine={self.engine!r}, keys={sorted(self.values)})"


@dataclass(frozen=True)
class Region:
    name: str
    description: str = ""
    # engine -> { campo: NOMBRE_DE_VARIABLE_DE_ENTORNO }
    env_refs: dict[str, dict[str, str]] = field(default_factory=dict)

    def credentials(self, engine: str, environ: dict[str, str] | None = None) -> Credentials:
        env = os.environ if environ is None else environ
        refs = self.env_refs.get(engine)
        if refs is None:
            raise ConfigError(f"La región '{self.name}' no tiene configurado {engine}.")

        missing = [var for var in refs.values() if not env.get(var)]
        if missing:
            raise ConfigError(
                f"Faltan variables para {engine} en '{self.name}': {', '.join(missing)}. "
                "Revisá tu .env (ver .env.example)."
            )
        return Credentials(engine=engine, values={key: env[var] for key, var in refs.items()})


def _parse_region(name: str, raw: dict[str, Any]) -> Region:
    env_refs: dict[str, dict[str, str]] = {}
    for engine in ENGINES:
        section = raw.get(engine)
        if section is None:
            continue
        if not isinstance(section, dict) or not all(isinstance(v, str) for v in section.values()):
            raise ConfigError(f"regions.{name}.{engine} debe ser un mapa campo -> variable.")
        env_refs[engine] = {key.removesuffix("_env"): var for key, var in section.items()}
    if not env_refs:
        raise ConfigError(f"La región '{name}' no tiene ningún engine configurado.")
    return Region(name=name, description=str(raw.get("description", "")), env_refs=env_refs)


def load_regions(path: Path) -> dict[str, Region]:
    """Lee regions.yaml y devuelve un diccionario nombre -> Region."""
    if not path.exists():
        raise ConfigError(f"No existe {path}.")
    data = yaml.safe_load(path.read_text()) or {}
    raw_regions = data.get("regions")
    if not isinstance(raw_regions, dict) or not raw_regions:
        raise ConfigError(f"{path} no define ninguna región en 'regions'.")
    return {name: _parse_region(name, cfg) for name, cfg in raw_regions.items()}


def select_regions(regions: dict[str, Region], wanted: list[str]) -> list[Region]:
    """Resuelve --region (repetible) o 'all'."""
    if not wanted or wanted == ["all"]:
        return list(regions.values())
    unknown = [r for r in wanted if r not in regions]
    if unknown:
        raise ConfigError(
            f"Región desconocida: {', '.join(unknown)}. Disponibles: {', '.join(regions)}."
        )
    return [regions[r] for r in wanted]

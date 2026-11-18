"""Definición de queries en YAML.

Una query declara su engine, sus parámetros tipados y una plantilla Jinja2. Los
parámetros se validan y convierten antes de renderizar, y se insertan en la plantilla
siempre serializados como JSON: nunca como texto libre.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError, ParamError

READ_OPERATIONS = {"find", "aggregate", "count_documents", "distinct", "query"}
WRITE_OPERATIONS = {"update_many", "delete_many"}
PARAM_TYPES = {"str", "int", "float", "bool", "date", "list"}


@dataclass(frozen=True)
class Param:
    name: str
    type: str = "str"
    required: bool = False
    default: Any = None
    choices: tuple[Any, ...] = ()
    description: str = ""

    def coerce(self, raw: Any) -> Any:
        if raw is None:
            if self.required and self.default is None:
                raise ParamError(f"Falta el parámetro obligatorio '{self.name}'.")
            return self.default
        try:
            value = _convert(self.type, raw)
        except (TypeError, ValueError) as exc:
            raise ParamError(f"'{self.name}' debe ser {self.type}: {raw!r}") from exc
        if self.choices and value not in self.choices:
            options = ", ".join(map(str, self.choices))
            raise ParamError(f"'{self.name}' debe ser uno de: {options}.")
        return value


def _convert(kind: str, raw: Any) -> Any:
    if kind == "str":
        return str(raw)
    if kind == "int":
        return int(raw)
    if kind == "float":
        return float(raw)
    if kind == "bool":
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in {"true", "1", "yes", "si", "sí"}:
            return True
        if text in {"false", "0", "no"}:
            return False
        raise ValueError(raw)
    if kind == "date":
        return raw if isinstance(raw, date) else date.fromisoformat(str(raw)).isoformat()
    if kind == "list":
        if isinstance(raw, list):
            return raw
        return [item.strip() for item in str(raw).split(",") if item.strip()]
    raise ValueError(kind)


@dataclass(frozen=True)
class Query:
    name: str
    engine: str
    operation: str
    template: str
    description: str = ""
    params: dict[str, Param] = field(default_factory=dict)
    target: dict[str, str] = field(default_factory=dict)  # database/collection o bucket/scope

    @property
    def is_write(self) -> bool:
        return self.operation in WRITE_OPERATIONS

    def resolve_params(self, given: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(given) - set(self.params))
        if unknown:
            raise ParamError(f"Parámetros desconocidos para '{self.name}': {', '.join(unknown)}.")
        return {name: p.coerce(given.get(name)) for name, p in self.params.items()}


def _parse_param(name: str, raw: Any) -> Param:
    spec = raw if isinstance(raw, dict) else {"type": raw}
    kind = spec.get("type", "str")
    if kind not in PARAM_TYPES:
        raise ConfigError(f"Tipo de parámetro inválido en '{name}': {kind}.")
    return Param(
        name=name,
        type=kind,
        required=bool(spec.get("required", False)),
        default=spec.get("default"),
        choices=tuple(spec.get("choices", ())),
        description=str(spec.get("description", "")),
    )


def parse_query(name: str, data: dict[str, Any]) -> Query:
    engine = data.get("engine")
    if engine not in {"mongo", "couchbase"}:
        raise ConfigError(f"Query '{name}': engine debe ser mongo o couchbase.")
    operation = data.get("operation", "find" if engine == "mongo" else "query")
    if operation not in READ_OPERATIONS | WRITE_OPERATIONS:
        raise ConfigError(f"Query '{name}': operación no soportada '{operation}'.")
    template = data.get("template")
    if not isinstance(template, str) or not template.strip():
        raise ConfigError(f"Query '{name}': falta 'template'.")
    params = {p: _parse_param(p, spec) for p, spec in (data.get("params") or {}).items()}
    return Query(
        name=name,
        engine=engine,
        operation=operation,
        template=template,
        description=str(data.get("description", "")),
        params=params,
        target={k: str(v) for k, v in (data.get("target") or {}).items()},
    )


def load_queries(directory: Path) -> dict[str, Query]:
    """Carga queries/<engine>/*.yaml. El nombre de la query es el nombre del archivo."""
    if not directory.is_dir():
        raise ConfigError(f"No existe el directorio de queries {directory}.")
    queries: dict[str, Query] = {}
    for path in sorted(directory.rglob("*.yaml")):
        data = yaml.safe_load(path.read_text()) or {}
        query = parse_query(path.stem, data)
        if query.name in queries:
            raise ConfigError(f"Query duplicada: {query.name}.")
        queries[query.name] = query
    return queries

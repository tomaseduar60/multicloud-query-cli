"""Render de plantillas con Jinja2 en sandbox.

Todo lo que se imprime con {{ ... }} pasa por json.dumps (finalize), así un parámetro
nunca puede cambiar la estructura de la query: no hay inyección vía comillas o llaves,
y no depende de que quien escribe la plantilla se acuerde de escapar.
"""

from __future__ import annotations

import json
from typing import Any

import yaml
from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment

from .errors import ConfigError
from .queries import Query


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


_env = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False, finalize=_to_json)


def render(query: Query, params: dict[str, Any]) -> Any:
    """Devuelve la query lista para el engine (dict/list para Mongo, dict para Couchbase)."""
    try:
        text = _env.from_string(query.template).render(**params)
    except TemplateError as exc:
        raise ConfigError(f"Error en la plantilla de '{query.name}': {exc}") from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"La plantilla de '{query.name}' no genera YAML válido: {exc}") from exc

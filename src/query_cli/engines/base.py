"""Interfaz común de engines y registro por nombre.

Cada engine recibe la query ya renderizada y las credenciales de UNA región. El registro
permite cambiar la implementación en tests sin tocar el resto del código.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from ..errors import ConfigError
from ..queries import Query
from ..regions import Credentials

Rows = list[dict[str, Any]]


class Engine(Protocol):
    def execute(self, query: Query, rendered: Any, credentials: Credentials) -> Rows: ...


_factories: dict[str, Callable[[], Engine]] = {}


def register_engine(name: str, factory: Callable[[], Engine]) -> None:
    _factories[name] = factory


def get_engine(name: str) -> Engine:
    if name not in _factories:
        # Import diferido: el driver solo se necesita si se usa ese engine.
        if name == "mongo":
            from .mongo import MongoEngine

            register_engine("mongo", MongoEngine)
        elif name == "couchbase":
            from .couchbase import CouchbaseEngine

            register_engine("couchbase", CouchbaseEngine)
        else:
            raise ConfigError(f"Engine desconocido: {name}.")
    return _factories[name]()

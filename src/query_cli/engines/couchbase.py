"""Couchbase (SQL++) con el SDK oficial. Credenciales: connstr, username, password.

La plantilla genera {statement, params}: los valores viajan como parámetros con nombre
del SDK, no concatenados en el SQL.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from ..errors import ConfigError
from ..queries import Query
from ..regions import Credentials
from .base import Rows


class CouchbaseEngine:
    def execute(self, query: Query, rendered: Any, credentials: Credentials) -> Rows:
        try:
            from couchbase.auth import PasswordAuthenticator
            from couchbase.cluster import Cluster
            from couchbase.options import ClusterOptions, QueryOptions
        except ImportError as exc:  # pragma: no cover
            raise ConfigError(
                "Falta el SDK: pip install 'multicloud-query-cli[couchbase]'"
            ) from exc

        spec = rendered or {}
        statement = spec.get("statement")
        if not statement:
            raise ConfigError(f"'{query.name}' debe generar 'statement'.")

        auth = PasswordAuthenticator(credentials.values["username"], credentials.values["password"])
        cluster = Cluster(credentials.values["connstr"], ClusterOptions(auth))
        cluster.wait_until_ready(timedelta(seconds=10))
        try:
            result = cluster.query(
                statement,
                QueryOptions(named_parameters=spec.get("params", {}), readonly=not query.is_write),
            )
            return [row if isinstance(row, dict) else {"value": row} for row in result.rows()]
        finally:
            cluster.close()

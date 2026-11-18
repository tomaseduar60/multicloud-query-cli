"""MongoDB con pymongo. Credencial esperada: uri."""

from __future__ import annotations

from typing import Any

from ..errors import ConfigError
from ..queries import Query
from ..regions import Credentials
from .base import Rows

DEFAULT_LIMIT = 1000


class MongoEngine:
    def execute(self, query: Query, rendered: Any, credentials: Credentials) -> Rows:
        try:
            from pymongo import MongoClient
        except ImportError as exc:  # pragma: no cover
            raise ConfigError("Falta pymongo: pip install 'multicloud-query-cli[mongo]'") from exc

        spec = rendered or {}
        database = query.target.get("database")
        collection = query.target.get("collection")
        if not database or not collection:
            raise ConfigError(f"'{query.name}' necesita target.database y target.collection.")

        with MongoClient(credentials.values["uri"], serverSelectionTimeoutMS=10_000) as client:
            coll = client[database][collection]
            op = query.operation
            if op == "find":
                cursor = coll.find(spec.get("filter", {}), spec.get("projection"))
                if spec.get("sort"):
                    cursor = cursor.sort(list(spec["sort"].items()))
                return [_clean(d) for d in cursor.limit(int(spec.get("limit", DEFAULT_LIMIT)))]
            if op == "aggregate":
                return [_clean(d) for d in coll.aggregate(spec.get("pipeline", []))]
            if op == "count_documents":
                return [{"count": coll.count_documents(spec.get("filter", {}))}]
            if op == "distinct":
                values = coll.distinct(spec["field"], spec.get("filter", {}))
                return [{spec["field"]: v} for v in values]
            if op == "update_many":
                res = coll.update_many(spec["filter"], spec["update"])
                return [{"matched": res.matched_count, "modified": res.modified_count}]
            if op == "delete_many":
                return [{"deleted": coll.delete_many(spec["filter"]).deleted_count}]
        raise ConfigError(f"Operación no soportada en mongo: {query.operation}.")


def _clean(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if k == "_id" else v) for k, v in doc.items()}

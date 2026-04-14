"""Local JSON storage backend that duck-types google.cloud.firestore.Client.

Stores data in a flat dict keyed by collection path:
    {"users": {"alice": {...}}, "users/alice/sessions": {"s1": {...}}, ...}

Supports enough of the Firestore API (get, list, query, set, batch, Increment)
to run the full seerai app without GCP credentials.
"""

from __future__ import annotations

import atexit
import copy
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _is_increment(val: Any) -> bool:
    return type(val).__name__ in ("Increment", "_Increment")


def _serialize(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    return obj


def _apply_field(target: dict, key: str, value: Any) -> None:
    """Set a field, handling Firestore dotted-key notation and Increment."""
    parts = key.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    leaf = parts[-1]
    if _is_increment(value):
        target[leaf] = (target.get(leaf) or 0) + value.value
    else:
        target[leaf] = _serialize(value)


class DocumentSnapshot:
    def __init__(self, data: dict | None, doc_id: str):
        self._data = data
        self.id = doc_id
        self.exists = data is not None

    def to_dict(self) -> dict | None:
        return copy.deepcopy(self._data) if self._data else None


class DocumentRef:
    def __init__(self, store: LocalStore, collection_path: str, doc_id: str):
        self._store = store
        self._collection_path = collection_path
        self._doc_id = doc_id
        self.path = f"{collection_path}/{doc_id}"

    def get(self) -> DocumentSnapshot:
        coll = self._store.data.get(self._collection_path, {})
        return DocumentSnapshot(coll.get(self._doc_id), self._doc_id)

    def set(self, data: dict, merge: bool = False) -> None:
        coll = self._store.data.setdefault(self._collection_path, {})
        if merge and self._doc_id in coll:
            existing = coll[self._doc_id]
            for k, v in data.items():
                _apply_field(existing, k, v)
        else:
            coll[self._doc_id] = _serialize(data)
        self._store._dirty = True

    def update(self, data: dict) -> None:
        coll = self._store.data.setdefault(self._collection_path, {})
        existing = coll.setdefault(self._doc_id, {})
        for k, v in data.items():
            _apply_field(existing, k, v)
        self._store._dirty = True

    def delete(self) -> None:
        coll = self._store.data.get(self._collection_path, {})
        coll.pop(self._doc_id, None)
        self._store._dirty = True

    def collection(self, name: str) -> CollectionRef:
        return CollectionRef(self._store, f"{self.path}/{name}")


class CollectionRef:
    def __init__(
        self,
        store: LocalStore,
        path: str,
        filters: list[tuple[str, str, Any]] | None = None,
        order_field: str | None = None,
        order_dir: str = "ASCENDING",
        limit_n: int = 0,
    ):
        self._store = store
        self._path = path
        self._filters = filters or []
        self._order_field = order_field
        self._order_dir = order_dir
        self._limit = limit_n

    def _clone(self, **overrides) -> CollectionRef:
        kw = dict(
            store=self._store,
            path=self._path,
            filters=list(self._filters),
            order_field=self._order_field,
            order_dir=self._order_dir,
            limit_n=self._limit,
        )
        kw.update(overrides)
        return CollectionRef(**kw)

    def document(self, doc_id: str) -> DocumentRef:
        return DocumentRef(self._store, self._path, doc_id)

    def where(self, field: str, op: str, value: Any) -> CollectionRef:
        return self._clone(filters=self._filters + [(field, op, value)])

    def order_by(self, field: str, direction: str = "ASCENDING") -> CollectionRef:
        return self._clone(order_field=field, order_dir=direction)

    def limit(self, n: int) -> CollectionRef:
        return self._clone(limit_n=n)

    def stream(self):
        coll = self._store.data.get(self._path, {})
        docs = list(coll.items())

        for field, op, value in self._filters:
            docs = [(did, d) for did, d in docs if _match(d.get(field), op, value)]

        if self._order_field:
            reverse = self._order_dir == "DESCENDING"
            docs.sort(key=lambda x: x[1].get(self._order_field) or "", reverse=reverse)

        if self._limit:
            docs = docs[: self._limit]

        return iter([DocumentSnapshot(d, did) for did, d in docs])


def _match(field_val: Any, op: str, value: Any) -> bool:
    if op == "==":
        return field_val == value
    if op == "in":
        return field_val in value
    if op == "array_contains":
        return isinstance(field_val, list) and value in field_val
    if op == ">=":
        return field_val is not None and field_val >= value
    if op == "<=":
        return field_val is not None and field_val <= value
    return False


class WriteBatch:
    def __init__(self, store: LocalStore):
        self._store = store
        self._ops: list[tuple[DocumentRef, dict, bool]] = []

    def set(self, ref: DocumentRef, data: dict, merge: bool = False) -> None:
        self._ops.append((ref, data, merge))

    def commit(self) -> None:
        for ref, data, merge in self._ops:
            ref.set(data, merge=merge)
        self._ops.clear()
        self._store.save()


class LocalStore:
    """In-memory store backed by a JSON file. Duck-types google.cloud.firestore.Client."""

    def __init__(self, path: Path):
        self._path = path
        self._dirty = False
        if path.exists():
            self.data: dict[str, dict[str, dict]] = json.loads(path.read_text())
        else:
            self.data = {}
        atexit.register(self.save)

    def save(self) -> None:
        if not self._dirty:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self.data, indent=2, default=str))
        self._dirty = False

    def collection(self, name: str) -> CollectionRef:
        return CollectionRef(self, name)

    def document(self, path: str) -> DocumentRef:
        parts = path.rstrip("/").split("/")
        collection_path = "/".join(parts[:-1])
        doc_id = parts[-1]
        return DocumentRef(self, collection_path, doc_id)

    def batch(self) -> WriteBatch:
        return WriteBatch(self)

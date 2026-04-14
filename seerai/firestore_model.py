"""Base class for Firestore document models, inspired by overseer's SupabaseModel.

Each entity type declares its collection name and ID field. The base class provides
get/list/save/delete operations that serialize through Pydantic validation, ensuring
the Python types are always the single source of truth for document shape.

Subcollections (sessions under users, events under sessions) use `parent_path`
to specify the Firestore document path of the parent.

Dirty tracking: after a model is loaded from Firestore (via get/list/query), its
state is snapshotted. `sync()` compares the current state to the snapshot and only
writes changed fields. This minimizes bandwidth and avoids clobbering concurrent
writes to other fields.
"""

from __future__ import annotations

from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, PrivateAttr

from seerai.firestore_client import get_firestore_client


class FirestoreModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    __collection__: ClassVar[str]
    __id_field__: ClassVar[str]

    _snapshot: dict[str, Any] = PrivateAttr(default_factory=dict)
    _parent_path: str | None = PrivateAttr(default=None)

    def _take_snapshot(self) -> None:
        self._snapshot = self.model_dump()

    def _get_changes(self) -> dict[str, Any]:
        current = self.model_dump()
        return {k: v for k, v in current.items() if v != self._snapshot.get(k)}

    @classmethod
    def _collection_ref(cls, db, parent_path: str | None = None):
        if parent_path:
            return db.document(parent_path).collection(cls.__collection__)
        return db.collection(cls.__collection__)

    @classmethod
    def _doc_ref(cls, db, doc_id: str, parent_path: str | None = None):
        return cls._collection_ref(db, parent_path).document(doc_id)

    def doc_id(self) -> str:
        return getattr(self, self.__id_field__)

    # --- CRUD ---

    @classmethod
    def get(cls, doc_id: str, *, parent_path: str | None = None) -> Self | None:
        db = get_firestore_client()
        doc = cls._doc_ref(db, doc_id, parent_path).get()
        if not doc.exists:
            return None
        instance = cls.model_validate(doc.to_dict())
        instance._parent_path = parent_path
        instance._take_snapshot()
        return instance

    @classmethod
    def list(
        cls,
        *,
        parent_path: str | None = None,
        order_by: str | None = None,
        direction: str = "DESCENDING",
        limit: int = 100,
        filters: dict[str, Any] | None = None,
    ) -> list[Self]:
        db = get_firestore_client()
        ref = cls._collection_ref(db, parent_path)
        for field, value in (filters or {}).items():
            ref = ref.where(field, "==", value)
        if order_by:
            ref = ref.order_by(order_by, direction=direction)
        if limit:
            ref = ref.limit(limit)
        results = []
        for doc in ref.stream():
            instance = cls.model_validate(doc.to_dict())
            instance._parent_path = parent_path
            instance._take_snapshot()
            results.append(instance)
        return results

    @classmethod
    def query(
        cls,
        field: str,
        op: str,
        value: Any,
        *,
        parent_path: str | None = None,
    ) -> list[Self]:
        """Single-filter query with arbitrary operator (==, in, array_contains, etc.)."""
        db = get_firestore_client()
        ref = cls._collection_ref(db, parent_path)
        results = []
        for doc in ref.where(field, op, value).stream():
            instance = cls.model_validate(doc.to_dict())
            instance._parent_path = parent_path
            instance._take_snapshot()
            results.append(instance)
        return results

    def save(self, *, parent_path: str | None = None, merge: bool = True) -> Self:
        """Write the full document to Firestore."""
        pp = parent_path or self._parent_path
        db = get_firestore_client()
        ref = self._doc_ref(db, self.doc_id(), pp)
        ref.set(self.model_dump(), merge=merge)
        self._parent_path = pp
        self._take_snapshot()
        return self

    def sync(self, *, parent_path: str | None = None) -> dict[str, Any] | None:
        """Write only changed fields to Firestore. Returns changes dict, or None if clean."""
        changes = self._get_changes()
        if not changes:
            return None
        pp = parent_path or self._parent_path
        db = get_firestore_client()
        ref = self._doc_ref(db, self.doc_id(), pp)
        ref.update(changes)
        self._parent_path = pp
        self._take_snapshot()
        return changes

    def delete(self, *, parent_path: str | None = None) -> None:
        pp = parent_path or self._parent_path
        db = get_firestore_client()
        self._doc_ref(db, self.doc_id(), pp).delete()

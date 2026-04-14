"""Base class for Firestore document models, inspired by overseer's SupabaseModel.

Each entity type declares its collection name and ID field. The base class provides
get/list/save/delete operations that serialize through Pydantic validation, ensuring
the Python types are always the single source of truth for document shape.

Subcollections (sessions under users, events under sessions) use `parent_path`
to specify the Firestore document path of the parent.
"""

from __future__ import annotations

from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict

from seerai.firestore_client import get_firestore_client


class FirestoreModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    __collection__: ClassVar[str]
    __id_field__: ClassVar[str]

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
        return cls.model_validate(doc.to_dict())

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
        return [cls.model_validate(doc.to_dict()) for doc in ref.stream()]

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
        return [
            cls.model_validate(doc.to_dict())
            for doc in ref.where(field, op, value).stream()
        ]

    def save(self, *, parent_path: str | None = None, merge: bool = True) -> Self:
        db = get_firestore_client()
        ref = self._doc_ref(db, self.doc_id(), parent_path)
        ref.set(self.model_dump(), merge=merge)
        return self

    def delete(self, *, parent_path: str | None = None) -> None:
        db = get_firestore_client()
        self._doc_ref(db, self.doc_id(), parent_path).delete()

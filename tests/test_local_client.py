"""Tests for the local JSON storage backend.

Verifies that LocalStore duck-types the Firestore Client API correctly:
- Document get/set/update/delete with merge and dotted keys
- Collection queries with where/order_by/limit
- Batch writes with Increment support
- Persistence to/from JSON file
"""

import pytest

from seerai.local_client import (
    LocalStore,
)


@pytest.fixture
def store(tmp_path):
    return LocalStore(tmp_path / "test.json")


class TestDocumentCRUD:
    def test_get_missing_doc(self, store):
        """Getting a nonexistent doc returns snapshot with exists=False."""
        snap = store.collection("users").document("ghost").get()
        assert not snap.exists
        assert snap.to_dict() is None

    def test_set_and_get(self, store):
        """Set then get returns the same data."""
        store.collection("users").document("alice").set({"name": "Alice", "score": 10})
        snap = store.collection("users").document("alice").get()
        assert snap.exists
        assert snap.to_dict()["name"] == "Alice"

    def test_set_merge(self, store):
        """Merge preserves existing fields and updates specified ones."""
        ref = store.collection("users").document("bob")
        ref.set({"name": "Bob", "score": 5, "role": "user"})
        ref.set({"score": 10, "org": "eng"}, merge=True)
        data = ref.get().to_dict()
        assert data["name"] == "Bob"  # preserved
        assert data["score"] == 10  # updated
        assert data["org"] == "eng"  # added
        assert data["role"] == "user"  # preserved

    def test_update(self, store):
        """Update modifies specific fields without replacing the doc."""
        ref = store.collection("users").document("carol")
        ref.set({"name": "Carol", "level": 1})
        ref.update({"level": 2})
        assert ref.get().to_dict()["name"] == "Carol"
        assert ref.get().to_dict()["level"] == 2

    def test_delete(self, store):
        """Delete removes the document."""
        ref = store.collection("users").document("dave")
        ref.set({"name": "Dave"})
        assert ref.get().exists
        ref.delete()
        assert not ref.get().exists

    def test_dotted_key_creates_nested_dict(self, store):
        """Firestore dotted-key notation like 'a.b' sets nested fields."""
        ref = store.collection("sessions").document("s1")
        ref.set({"id": "s1"})
        ref.set({"token_usage.claude": 100}, merge=True)
        data = ref.get().to_dict()
        assert data["token_usage"]["claude"] == 100

    def test_dotted_key_preserves_siblings(self, store):
        """Multiple dotted-key writes to the same parent don't clobber each other."""
        ref = store.collection("sessions").document("s1")
        ref.set({"id": "s1", "token_usage": {"gpt4": 50}})
        ref.set({"token_usage.claude": 100}, merge=True)
        data = ref.get().to_dict()
        assert data["token_usage"]["gpt4"] == 50
        assert data["token_usage"]["claude"] == 100


class TestIncrement:
    def test_increment_on_set_merge(self, store):
        """Increment adds to existing value on merge set."""
        from google.cloud.firestore_v1 import Increment

        ref = store.collection("sessions").document("s1")
        ref.set({"count": 3})
        ref.set({"count": Increment(1)}, merge=True)
        assert ref.get().to_dict()["count"] == 4

    def test_increment_on_missing_field(self, store):
        """Increment on a nonexistent field starts from 0."""
        from google.cloud.firestore_v1 import Increment

        ref = store.collection("sessions").document("s2")
        ref.set({"id": "s2"})
        ref.set({"count": Increment(5)}, merge=True)
        assert ref.get().to_dict()["count"] == 5

    def test_increment_with_dotted_key(self, store):
        """Increment works through dotted-key nested paths."""
        from google.cloud.firestore_v1 import Increment

        ref = store.collection("sessions").document("s3")
        ref.set({"id": "s3", "token_usage": {"claude": 10}})
        ref.set({"token_usage.claude": Increment(5)}, merge=True)
        assert ref.get().to_dict()["token_usage"]["claude"] == 15


class TestCollectionQuery:
    @pytest.fixture(autouse=True)
    def seed(self, store):
        coll = store.collection("items")
        coll.document("a").set({"name": "alpha", "score": 3, "tags": ["x", "y"]})
        coll.document("b").set({"name": "beta", "score": 1, "tags": ["y"]})
        coll.document("c").set({"name": "gamma", "score": 2, "tags": ["x"]})

    def test_stream_all(self, store):
        """Stream without filters returns all docs."""
        docs = list(store.collection("items").stream())
        assert len(docs) == 3

    def test_where_equals(self, store):
        """Equality filter returns matching docs."""
        docs = list(store.collection("items").where("name", "==", "beta").stream())
        assert len(docs) == 1
        assert docs[0].to_dict()["name"] == "beta"

    def test_where_in(self, store):
        """'in' filter matches values in a list."""
        docs = list(
            store.collection("items").where("name", "in", ["alpha", "gamma"]).stream()
        )
        assert len(docs) == 2

    def test_where_array_contains(self, store):
        """'array_contains' matches docs whose list field contains the value."""
        docs = list(
            store.collection("items").where("tags", "array_contains", "x").stream()
        )
        names = {d.to_dict()["name"] for d in docs}
        assert names == {"alpha", "gamma"}

    def test_order_by_ascending(self, store):
        """order_by sorts ascending by default."""
        docs = list(store.collection("items").order_by("score").stream())
        scores = [d.to_dict()["score"] for d in docs]
        assert scores == [1, 2, 3]

    def test_order_by_descending(self, store):
        docs = list(
            store.collection("items").order_by("score", direction="DESCENDING").stream()
        )
        scores = [d.to_dict()["score"] for d in docs]
        assert scores == [3, 2, 1]

    def test_limit(self, store):
        docs = list(store.collection("items").order_by("score").limit(2).stream())
        assert len(docs) == 2

    def test_chained_where_and_order(self, store):
        """Multiple filters + ordering compose correctly."""
        docs = list(
            store.collection("items")
            .where("tags", "array_contains", "x")
            .order_by("score", direction="DESCENDING")
            .stream()
        )
        names = [d.to_dict()["name"] for d in docs]
        assert names == ["alpha", "gamma"]


class TestSubcollections:
    def test_doc_then_collection(self, store):
        """document().collection() navigates subcollections correctly."""
        store.document("users/alice").collection("sessions").document("s1").set(
            {"id": "s1"}
        )
        snap = store.document("users/alice").collection("sessions").document("s1").get()
        assert snap.exists
        assert snap.to_dict()["id"] == "s1"
        # Stored under the correct collection path
        assert "users/alice/sessions" in store.data


class TestBatch:
    def test_batch_set_and_commit(self, store):
        """Batch collects writes and applies them on commit."""
        batch = store.batch()
        batch.set(store.collection("x").document("1"), {"v": 1})
        batch.set(store.collection("x").document("2"), {"v": 2})
        # Not yet visible
        assert not store.collection("x").document("1").get().exists
        batch.commit()
        assert store.collection("x").document("1").get().to_dict()["v"] == 1
        assert store.collection("x").document("2").get().to_dict()["v"] == 2


class TestPersistence:
    def test_save_and_reload(self, tmp_path):
        """Data survives save + reload from disk."""
        path = tmp_path / "db.json"
        s1 = LocalStore(path)
        s1.collection("users").document("alice").set({"name": "Alice"})
        s1.save()

        s2 = LocalStore(path)
        assert (
            s2.collection("users").document("alice").get().to_dict()["name"] == "Alice"
        )

    def test_batch_commit_triggers_save(self, tmp_path):
        """Batch commit auto-saves to disk."""
        path = tmp_path / "db.json"
        s1 = LocalStore(path)
        batch = s1.batch()
        batch.set(s1.collection("things").document("t1"), {"ok": True})
        batch.commit()

        s2 = LocalStore(path)
        assert s2.collection("things").document("t1").get().exists

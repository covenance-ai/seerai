"""Tests for the data source switching logic.

Verifies the firestore default, env-var override, explicit switching,
and that the client singleton resets on switch.
"""

from unittest.mock import patch

import pytest

from seerai import firestore_client as fc


@pytest.fixture(autouse=True)
def reset_state():
    """Reset module-level state between tests."""
    fc._client = None
    fc._source = None
    yield
    fc._client = None
    fc._source = None


class TestDefaults:
    def test_defaults_to_firestore(self):
        """Without DATA_SOURCE set, default is firestore regardless of
        whether a snapshot file exists on disk."""
        with patch.dict("os.environ", {}, clear=True):
            assert fc.get_datasource() == "firestore"

    def test_env_var_local_opt_in(self):
        """DATA_SOURCE=local opts into the snapshot-backed LocalStore."""
        with patch.dict("os.environ", {"DATA_SOURCE": "local"}):
            assert fc.get_datasource() == "local"

    def test_env_var_firestore_explicit(self):
        """DATA_SOURCE=firestore is also accepted (explicit)."""
        with patch.dict("os.environ", {"DATA_SOURCE": "firestore"}):
            assert fc.get_datasource() == "firestore"


class TestExplicitSwitch:
    def test_set_datasource_overrides_auto_detect(self):
        """Explicit set_datasource overrides all auto-detection."""
        fc.set_datasource("firestore")
        assert fc.get_datasource() == "firestore"
        fc.set_datasource("local")
        assert fc.get_datasource() == "local"

    def test_set_datasource_resets_client(self, tmp_path):
        """Switching datasource clears the client singleton."""
        snap = tmp_path / "db.json"
        snap.write_text("{}")
        with patch.object(fc, "SNAPSHOT_PATH", snap):
            fc.set_datasource("local")
            client1 = fc.get_firestore_client()
            fc.set_datasource("local")
            client2 = fc.get_firestore_client()
            assert client1 is not client2

    def test_client_is_local_store_when_local(self, tmp_path):
        snap = tmp_path / "db.json"
        snap.write_text("{}")
        with patch.object(fc, "SNAPSHOT_PATH", snap):
            fc.set_datasource("local")
            client = fc.get_firestore_client()
            from seerai.local_client import LocalStore

            assert isinstance(client, LocalStore)

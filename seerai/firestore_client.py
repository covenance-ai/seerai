import os
from pathlib import Path

_client = None
_source: str | None = None  # None = auto-detect

SNAPSHOT_PATH = Path(__file__).parent.parent / "data" / "snapshot.json"


def snapshot_exists() -> bool:
    path = Path(os.getenv("LOCAL_DATA_PATH", str(SNAPSHOT_PATH)))
    return path.exists()


def get_datasource() -> str:
    """Return current data source: 'local' or 'firestore'."""
    if _source:
        return _source
    env = os.getenv("DATA_SOURCE")
    if env:
        return env
    return "local" if snapshot_exists() else "firestore"


def set_datasource(source: str) -> None:
    """Switch data source at runtime. Resets the client singleton."""
    global _client, _source
    _source = source
    _client = None


def get_firestore_client():
    global _client
    if _client is None:
        source = get_datasource()
        if source == "local":
            from seerai.local_client import LocalStore

            path = Path(os.getenv("LOCAL_DATA_PATH", str(SNAPSHOT_PATH)))
            _client = LocalStore(path)
        else:
            from google.cloud.firestore import Client

            project = os.getenv("GCP_PROJECT", "covenance-469421")
            database = os.getenv("FIRESTORE_DATABASE", "seerai")
            _client = Client(project=project, database=database)
    return _client

import os
from pathlib import Path

_client = None


def get_firestore_client():
    global _client
    if _client is None:
        if os.getenv("DATA_SOURCE") == "local":
            from seerai.local_client import LocalStore

            path = Path(
                os.getenv(
                    "LOCAL_DATA_PATH",
                    str(Path(__file__).parent.parent / "data" / "snapshot.json"),
                )
            )
            _client = LocalStore(path)
        else:
            from google.cloud.firestore import Client

            project = os.getenv("GCP_PROJECT", "covenance-469421")
            database = os.getenv("FIRESTORE_DATABASE", "seerai")
            _client = Client(project=project, database=database)
    return _client

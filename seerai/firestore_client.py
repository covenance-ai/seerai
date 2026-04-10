import os

from google.cloud.firestore import Client

_client: Client | None = None


def get_firestore_client() -> Client:
    global _client
    if _client is None:
        project = os.getenv("GCP_PROJECT", "covenance-469421")
        _client = Client(project=project)
    return _client

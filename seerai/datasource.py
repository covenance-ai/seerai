"""Data source management — switch between Firestore and local JSON at runtime."""

from fastapi import APIRouter
from pydantic import BaseModel

from seerai.firestore_client import (
    available_langs,
    get_datasource,
    set_datasource,
    snapshot_exists,
    snapshot_path_for,
)
from seerai.privacy import Visibility, privacy_surface

router = APIRouter(tags=["datasource"])


class DataSourceInfo(BaseModel):
    source: str
    local_available: bool
    # Languages for which a local snapshot file exists. The frontend shows
    # only these in its language menu when the source is "local".
    local_langs: list[str] = []


def _build_info() -> DataSourceInfo:
    return DataSourceInfo(
        source=get_datasource(),
        local_available=snapshot_exists(),
        local_langs=available_langs(),
    )


@router.get("/datasource")
@privacy_surface(Visibility.PUBLIC)
def info() -> DataSourceInfo:
    return _build_info()


@router.post("/datasource")
@privacy_surface(Visibility.PUBLIC)
def switch(body: DataSourceInfo) -> DataSourceInfo:
    set_datasource(body.source)
    return _build_info()


@router.post("/datasource/download")
@privacy_surface(Visibility.PUBLIC)
def download_snapshot() -> dict:
    """Download Firestore data to local snapshot (English), then switch to local."""
    from seerai.snapshot import download

    counts = download(snapshot_path_for("en"))
    set_datasource("local")
    return {"counts": counts, "source": "local"}

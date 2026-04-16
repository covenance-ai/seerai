"""Data source management — switch between Firestore and local JSON at runtime."""

from fastapi import APIRouter
from pydantic import BaseModel

from seerai.firestore_client import (
    SNAPSHOT_PATH,
    get_datasource,
    set_datasource,
    snapshot_exists,
)
from seerai.privacy import Visibility, privacy_surface

router = APIRouter(tags=["datasource"])


class DataSourceInfo(BaseModel):
    source: str
    local_available: bool


@router.get("/datasource")
@privacy_surface(Visibility.PUBLIC)
def info() -> DataSourceInfo:
    return DataSourceInfo(source=get_datasource(), local_available=snapshot_exists())


@router.post("/datasource")
@privacy_surface(Visibility.PUBLIC)
def switch(body: DataSourceInfo) -> DataSourceInfo:
    set_datasource(body.source)
    return DataSourceInfo(source=get_datasource(), local_available=snapshot_exists())


@router.post("/datasource/download")
@privacy_surface(Visibility.PUBLIC)
def download_snapshot() -> dict:
    """Download Firestore data to local snapshot, then switch to local."""
    from seerai.snapshot import download

    counts = download(SNAPSHOT_PATH)
    set_datasource("local")
    return {"counts": counts, "source": "local"}

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO)

role = os.getenv("SERVICE_ROLE", "local")
if role != "local":
    import google.cloud.logging

    client = google.cloud.logging.Client()
    client.setup_logging()

from seerai.cost.endpoint import router as cost_router
from seerai.dashboard.endpoint import router as dashboard_router
from seerai.datasource import router as datasource_router
from seerai.ingest.endpoint import router as ingest_router
from seerai.insights.endpoint import router as insights_router
from seerai.org.endpoint import router as org_router
from seerai.query.endpoint import router as query_router
from seerai.subscriptions.endpoint import router as subscriptions_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from seerai.firestore_client import get_firestore_client

    get_firestore_client()
    yield


app = FastAPI(lifespan=lifespan, title="seerai", description="LLM chat observer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest_router, prefix="/api")
app.include_router(query_router, prefix="/api")
app.include_router(org_router, prefix="/api")
app.include_router(subscriptions_router, prefix="/api")
app.include_router(cost_router, prefix="/api")
app.include_router(insights_router, prefix="/api")
app.include_router(datasource_router, prefix="/api")
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "seerai" / "static"),
    name="static",
)
app.include_router(dashboard_router)

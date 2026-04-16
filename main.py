import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from seerai.firestore_client import SUPPORTED_LANGS, current_lang

logging.basicConfig(level=logging.INFO)

role = os.getenv("SERVICE_ROLE", "local")
if role != "local":
    import google.cloud.logging

    client = google.cloud.logging.Client()
    client.setup_logging()

from seerai.analytics.endpoint import router as analytics_router
from seerai.coach.endpoint import router as coach_router
from seerai.cost.endpoint import router as cost_router
from seerai.dashboard.endpoint import router as dashboard_router
from seerai.datasource import router as datasource_router
from seerai.ingest.endpoint import router as ingest_router
from seerai.insights.endpoint import router as insights_router
from seerai.org.endpoint import router as org_router
from seerai.privacy import context_router as privacy_router
from seerai.privacy import install_privacy_guard
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


@app.middleware("http")
async def set_locale(request: Request, call_next):
    """Bind the requested locale to a ContextVar so the data layer can read
    it. The client sends ``X-Seerai-Lang`` via the fetch interceptor in
    i18n.js; falls back to English for direct API callers.

    Also disables browser caching for ``/static/*`` so dev iterations on
    the fetch interceptor / sidebar don't get shadowed by a stale copy.
    The bundles are small and cache-busting them is cheap for local dev.
    """
    lang = request.headers.get("x-seerai-lang", "").lower()
    if lang not in SUPPORTED_LANGS:
        lang = "en"
    token = current_lang.set(lang)
    try:
        response = await call_next(request)
    finally:
        current_lang.reset(token)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

app.include_router(ingest_router, prefix="/api")
app.include_router(query_router, prefix="/api")
app.include_router(org_router, prefix="/api")
app.include_router(subscriptions_router, prefix="/api")
app.include_router(cost_router, prefix="/api")
app.include_router(insights_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(coach_router, prefix="/api")
app.include_router(datasource_router, prefix="/api")
app.include_router(privacy_router, prefix="/api")
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "seerai" / "static"),
    name="static",
)
# Explainer assets (SVG diagrams, etc.) referenced by the FAQ page live in
# /docs at the repo root. Mounted under /assets/docs/ to avoid the /docs path
# that FastAPI uses for its Swagger UI.
app.mount(
    "/assets/docs",
    StaticFiles(directory=Path(__file__).parent / "docs"),
    name="docs_assets",
)
app.include_router(dashboard_router)

# Install the privacy guard after all routers are included — it introspects
# every APIRoute for a @privacy_surface policy and wraps the route handler.
install_privacy_guard(app)

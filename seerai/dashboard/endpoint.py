from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from seerai.privacy import Visibility, privacy_surface

router = APIRouter(tags=["dashboard"])

_PAGES = Path(__file__).parent / "pages"


# HTML pages are PUBLIC — privacy hiding happens client-side via
# seerai/static/privacy.js reading GET /api/privacy/context. The data APIs the
# pages then call enforce the real gate.


@router.get("/", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def index():
    return HTMLResponse(_PAGES.joinpath("index.html").read_text())


@router.get("/sessions/{user_id}", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def sessions_page(user_id: str):
    return HTMLResponse(_PAGES.joinpath("sessions.html").read_text())


@router.get("/session/{user_id}/{session_id}", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def session_detail_page(user_id: str, session_id: str):
    return HTMLResponse(_PAGES.joinpath("session_detail.html").read_text())


@router.get("/exec", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def org_index():
    return HTMLResponse(_PAGES.joinpath("org_index.html").read_text())


@router.get("/exec/costs", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def cost_page():
    return HTMLResponse(_PAGES.joinpath("cost.html").read_text())


@router.get("/exec/insights", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def insights_page():
    return HTMLResponse(_PAGES.joinpath("insights.html").read_text())


@router.get("/exec/analytics", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def analytics_page():
    return HTMLResponse(_PAGES.joinpath("analytics.html").read_text())


@router.get("/exec/coach", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def coach_page():
    return HTMLResponse(_PAGES.joinpath("coach.html").read_text())


@router.get("/exec/{org_id}", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def org_detail_page(org_id: str):
    return HTMLResponse(_PAGES.joinpath("org_detail.html").read_text())


@router.get("/my/{user_id}", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def my_sessions_page(user_id: str):
    return HTMLResponse(_PAGES.joinpath("my_sessions.html").read_text())


@router.get("/my/{user_id}/{session_id}", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def my_session_detail_page(user_id: str, session_id: str):
    return HTMLResponse(_PAGES.joinpath("my_session_detail.html").read_text())


@router.get("/admin/privacy", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def admin_privacy_page():
    return HTMLResponse(_PAGES.joinpath("admin.html").read_text())

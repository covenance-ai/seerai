from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])

_PAGES = Path(__file__).parent / "pages"


@router.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(_PAGES.joinpath("index.html").read_text())


@router.get("/sessions/{user_id}", response_class=HTMLResponse)
def sessions_page(user_id: str):
    return HTMLResponse(_PAGES.joinpath("sessions.html").read_text())


@router.get("/session/{user_id}/{session_id}", response_class=HTMLResponse)
def session_detail_page(user_id: str, session_id: str):
    return HTMLResponse(_PAGES.joinpath("session_detail.html").read_text())


@router.get("/exec", response_class=HTMLResponse)
def org_index():
    return HTMLResponse(_PAGES.joinpath("org_index.html").read_text())


@router.get("/exec/costs", response_class=HTMLResponse)
def cost_page():
    return HTMLResponse(_PAGES.joinpath("cost.html").read_text())


@router.get("/exec/{org_id}", response_class=HTMLResponse)
def org_detail_page(org_id: str):
    return HTMLResponse(_PAGES.joinpath("org_detail.html").read_text())


@router.get("/my/{user_id}", response_class=HTMLResponse)
def my_sessions_page(user_id: str):
    return HTMLResponse(_PAGES.joinpath("my_sessions.html").read_text())


@router.get("/my/{user_id}/{session_id}", response_class=HTMLResponse)
def my_session_detail_page(user_id: str, session_id: str):
    return HTMLResponse(_PAGES.joinpath("my_session_detail.html").read_text())

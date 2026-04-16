from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from seerai.privacy import Visibility, privacy_surface

router = APIRouter(tags=["dashboard"])

_PAGES = Path(__file__).parent / "pages"
_STATIC = Path(__file__).parent.parent / "static"


def _static_version(filename: str) -> str:
    """Return an mtime-based version tag for a static asset.

    Appended as a query string on `<script src=...>` tags so browsers see a
    fresh URL whenever i18n.js / nav.js change — side-steps the aggressive
    in-memory cache that some embedded Chromium previews use even when the
    server sends ``Cache-Control: no-store``.
    """
    try:
        return str(int((_STATIC / filename).stat().st_mtime))
    except OSError:
        return "0"


def _render(page: str) -> HTMLResponse:
    """Read an HTML page and inject cache-busting ?v=<mtime> on our scripts."""
    html = _PAGES.joinpath(page).read_text()
    html = html.replace(
        'src="/static/i18n.js"',
        f'src="/static/i18n.js?v={_static_version("i18n.js")}"',
    )
    html = html.replace(
        'src="/static/nav.js"',
        f'src="/static/nav.js?v={_static_version("nav.js")}"',
    )
    return HTMLResponse(html)


# HTML pages are PUBLIC — privacy hiding happens client-side via
# seerai/static/privacy.js reading GET /api/privacy/context. The data APIs the
# pages then call enforce the real gate.


@router.get("/", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def index():
    return _render("index.html")


@router.get("/sessions/{user_id}", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def sessions_page(user_id: str):
    return _render("sessions.html")


@router.get("/session/{user_id}/{session_id}", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def session_detail_page(user_id: str, session_id: str):
    return _render("session_detail.html")


@router.get("/exec", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def org_index():
    return _render("org_index.html")


@router.get("/exec/costs", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def cost_page():
    return _render("cost.html")


@router.get("/exec/insights", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def insights_page():
    return _render("insights.html")


@router.get("/exec/analytics", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def analytics_page():
    return _render("analytics.html")


@router.get("/exec/coach", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def coach_page():
    return _render("coach.html")


@router.get("/exec/{org_id}", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def org_detail_page(org_id: str):
    return _render("org_detail.html")


@router.get("/my/{user_id}", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def my_sessions_page(user_id: str):
    return _render("my_sessions.html")


@router.get("/my/{user_id}/{session_id}", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def my_session_detail_page(user_id: str, session_id: str):
    return _render("my_session_detail.html")


@router.get("/admin/privacy", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def admin_privacy_page():
    return _render("admin.html")


@router.get("/faq", response_class=HTMLResponse)
@privacy_surface(Visibility.PUBLIC)
def faq_page():
    return _render("faq.html")

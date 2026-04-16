"""Org privacy mode — one declaration per surface, enforced at the route layer.

Principle: every privacy-sensitive FastAPI endpoint is annotated with
`@privacy_surface(...)` which attaches a `SurfacePolicy` to the endpoint
function. `install_privacy_guard(app)` (called from main.py after all routers
are included) wraps each such route to read the policy and apply it at
request time:

  - INDIVIDUAL surfaces deny when caller != subject in a privacy-on org; they
    also deny cross-user enumeration (no subject resolvable) when any org has
    privacy on.
  - AGGREGATE surfaces keep rollups but null-out declared `strip` fields and
    suppress dept rows whose `user_count` is below `min_cohort_size`.
  - INSIGHT surfaces drop personal-kind insights whose subject belongs to a
    privacy-on org.
  - PUBLIC surfaces are untouched.

Caller identification is demo-level — `X-Caller-User-Id` header or `?caller=`
query param. When real auth lands, replace `_caller_from_request` and leave
the rest intact.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from fastapi.routing import APIRoute, request_response

from seerai.entities import OrgNode, User

log = logging.getLogger(__name__)


class Visibility(StrEnum):
    PUBLIC = "public"
    AGGREGATE = "aggregate"
    INDIVIDUAL = "individual"
    INSIGHT = "insight"


# Insight kinds that expose individual-level data. Only kinds NOT listed here
# may surface from a privacy-mode org.
PERSONAL_INSIGHT_KINDS: frozenset[str] = frozenset(
    {
        "cross_department_interest",
        "above_paygrade",
        "below_paygrade",
        "negative_roi_pattern",
    }
)

# Keys on an aggregate row that identify the row (kept intact under
# k-anonymity suppression so the UI can still render the row shell).
_PRESERVE_KEYS: frozenset[str] = frozenset(
    {"org_id", "name", "parent_id", "depth", "user_count", "user_id"}
)


@dataclass(frozen=True)
class SurfacePolicy:
    visibility: Visibility
    subject: Callable[..., str | None] = lambda **_: None
    strip: tuple[str, ...] = ()


@dataclass(frozen=True)
class Caller:
    user_id: str | None
    role: str | None
    org_id: str | None
    root_org_id: str | None


@dataclass
class Decision:
    allowed: bool
    transform: Callable[[Any], Any] | None = None
    reason: str = ""


# ---------- public API: decorator ----------


def privacy_surface(
    visibility: Visibility,
    *,
    subject: Callable[..., str | None] = (lambda **_: None),
    strip: tuple[str, ...] = (),
):
    """Declare the privacy class of a FastAPI endpoint.

    ``subject`` is called with the request's path+query params and returns the
    user_id the endpoint is about (or None). For INDIVIDUAL endpoints, the
    caller must equal this subject when the target org has privacy on.

    ``strip`` lists top-level response fields that are nulled-out on AGGREGATE
    responses from privacy-on orgs (e.g. the per-user leaderboard inside an
    otherwise-aggregate analytics payload).
    """
    policy = SurfacePolicy(visibility=visibility, subject=subject, strip=strip)

    def deco(fn):
        fn.__privacy__ = policy
        return fn

    return deco


# ---------- core decision ----------


def decide(
    policy: SurfacePolicy,
    caller: Caller,
    kwargs: dict,
    target_org: OrgNode | None,
) -> Decision:
    """Pure function: policy + caller + target-org → Decision.

    Does no I/O beyond what the caller passes in, so it's the unit under test
    for all property-style invariants.
    """
    if policy.visibility is Visibility.PUBLIC:
        return Decision(allowed=True)

    target_privacy = bool(target_org and target_org.privacy_mode)

    if policy.visibility is Visibility.INDIVIDUAL:
        subject = policy.subject(**kwargs) if policy.subject else None
        if subject is None:
            # Cross-user enumeration (e.g. list-all-users, flagged-sessions).
            # Forbidden if any org has privacy on — we can't tell which rows
            # are safe without per-row work, so deny outright.
            if _any_privacy_on():
                return Decision(allowed=False, reason="cross-user-blocked")
            return Decision(allowed=True)
        if not target_privacy:
            return Decision(allowed=True)
        if caller.user_id is not None and caller.user_id == subject:
            return Decision(allowed=True)
        return Decision(allowed=False, reason="individual-blocked")

    if policy.visibility is Visibility.AGGREGATE:
        if not target_privacy:
            return Decision(allowed=True)
        min_size = target_org.min_cohort_size
        strip = policy.strip

        def transform(resp: Any) -> Any:
            if isinstance(resp, dict):
                _strip_fields(resp, strip)
                _suppress_small_groups(resp, min_size)
            return resp

        return Decision(allowed=True, transform=transform)

    if policy.visibility is Visibility.INSIGHT:

        def transform(resp: Any) -> Any:
            if not isinstance(resp, list):
                return resp
            return [i for i in resp if _insight_allowed(i)]

        return Decision(allowed=True, transform=transform)

    return Decision(allowed=True)


# ---------- helpers ----------


def _strip_fields(obj: dict, names: tuple[str, ...]) -> None:
    """Null-out named top-level fields. List→[], dict→{}, other→None."""
    for k in names:
        if k not in obj:
            continue
        v = obj[k]
        if isinstance(v, list):
            obj[k] = []
        elif isinstance(v, dict):
            obj[k] = {}
        else:
            obj[k] = None


def _suppress_small_groups(obj: Any, min_size: int) -> None:
    """Walk response JSON and blank aggregate rows where user_count<min_size.

    A row is any dict carrying integer ``user_count``. Identifier keys
    (``org_id``, ``name``, ``parent_id``, ``depth``, ``user_count``, ``user_id``)
    are preserved so the UI still knows the row exists; everything else is set
    to None and ``suppressed: True`` is added.
    """
    if isinstance(obj, list):
        for item in obj:
            _suppress_small_groups(item, min_size)
        return
    if not isinstance(obj, dict):
        return
    uc = obj.get("user_count")
    if isinstance(uc, int) and uc < min_size:
        for k in list(obj.keys()):
            if k not in _PRESERVE_KEYS:
                obj[k] = None
        obj["suppressed"] = True
        return
    for v in obj.values():
        _suppress_small_groups(v, min_size)


def _insight_allowed(item: Any) -> bool:
    """True iff this insight row may surface under privacy rules."""
    if not isinstance(item, dict):
        return True
    kind = item.get("kind")
    if kind not in PERSONAL_INSIGHT_KINDS:
        return True
    ins_org_id = item.get("org_id")
    if not ins_org_id:
        return True
    root = _root_org_of(ins_org_id)
    return not (root and root.privacy_mode)


def _root_org_of(org_id: str | None) -> OrgNode | None:
    if not org_id:
        return None
    try:
        org = OrgNode.get(org_id)
    except Exception:  # e.g. mocked firestore in tests
        return None
    if org is None or not getattr(org, "path", None):
        return None
    if org.path[0] == org.org_id:
        return org
    try:
        return OrgNode.get(org.path[0])
    except Exception:
        return None


def _target_org_for(subject_user_id: str | None, kwargs: dict) -> OrgNode | None:
    """Root org whose privacy settings govern the request.

    Looks at ``org_id`` first (the endpoint is explicitly about an org), then
    at ``user_id`` / the resolved subject (the endpoint is about a person).
    Any lookup failure (e.g. mocked datasource in tests) returns None — the
    guard treats that as "no privacy-mode target", letting non-privacy flows
    pass through unchanged.
    """
    org_id = kwargs.get("org_id")
    if org_id:
        return _root_org_of(org_id)
    uid = subject_user_id or kwargs.get("user_id")
    if uid:
        try:
            user = User.get(uid)
        except Exception:
            return None
        if user and user.org_id:
            return _root_org_of(user.org_id)
    return None


def _any_privacy_on() -> bool:
    """True iff any root org currently has privacy_mode=True.

    Returns False on lookup failure so tests with mocked datasources work
    without needing to stub every guard-path query.
    """
    try:
        roots = OrgNode.query("depth", "==", 0)
    except Exception:
        return False
    try:
        return any(getattr(n, "privacy_mode", False) for n in roots)
    except Exception:
        return False


def _caller_from_request(request: Request) -> Caller:
    """Demo identification — X-Caller-User-Id header or ?caller= query param.

    Replace this when real auth lands; the rest of the module is auth-agnostic.
    """
    uid = request.headers.get("X-Caller-User-Id") or request.query_params.get("caller")
    if not uid:
        return Caller(user_id=None, role=None, org_id=None, root_org_id=None)
    user = User.get(uid)
    if user is None:
        return Caller(user_id=uid, role=None, org_id=None, root_org_id=None)
    root = None
    if user.org_id:
        org = OrgNode.get(user.org_id)
        if org and org.path:
            root = org.path[0]
    return Caller(
        user_id=user.user_id,
        role=user.role,
        org_id=user.org_id,
        root_org_id=root,
    )


# ---------- middleware installation ----------


def install_privacy_guard(app: FastAPI) -> None:
    """Wrap every APIRoute whose endpoint carries a @privacy_surface policy.

    Call once in main.py after all routers are included. The wrapper runs
    per-request: reads caller, resolves target org, calls decide(), 403s on
    deny, and rewrites the JSON response body for transforms.
    """
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        policy = getattr(route.endpoint, "__privacy__", None)
        if policy is None:
            continue
        original_handler = route.get_route_handler()
        route.app = request_response(_wrap_handler(original_handler, policy))


def _wrap_handler(original_handler, policy: SurfacePolicy):
    async def handler(request: Request) -> Response:
        caller = _caller_from_request(request)
        kwargs = {**request.path_params, **dict(request.query_params)}
        subject = policy.subject(**kwargs) if policy.subject else None
        target_org = _target_org_for(subject, kwargs)
        decision = decide(policy, caller, kwargs, target_org)
        if not decision.allowed:
            raise HTTPException(status_code=403, detail=decision.reason or "forbidden")

        response = await original_handler(request)

        if decision.transform is None:
            return response
        if not isinstance(response, Response):
            return response
        body = getattr(response, "body", None)
        if not body:
            return response
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return response
        data = decision.transform(data)
        new_body = json.dumps(data, default=str).encode()
        return Response(
            content=new_body,
            status_code=response.status_code,
            media_type="application/json",
            headers={
                k: v
                for k, v in response.headers.items()
                if k.lower() not in ("content-length", "content-type")
            },
        )

    return handler


# ---------- completeness meta-helpers (for tests) ----------


def registered_policies(app: FastAPI) -> dict[str, SurfacePolicy]:
    """Every registered route → its SurfacePolicy (for meta-tests)."""
    out: dict[str, SurfacePolicy] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        pol = getattr(route.endpoint, "__privacy__", None)
        if pol is None:
            continue
        for method in sorted(route.methods or []):
            out[f"{method} {route.path}"] = pol
    return out


def unclassified_routes(app: FastAPI) -> list[str]:
    """Routes with no @privacy_surface — a new route forgot to declare."""
    missing: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if getattr(route.endpoint, "__privacy__", None) is None:
            for method in sorted(route.methods or []):
                missing.append(f"{method} {route.path}")
    return missing


# ---------- context endpoint (used by the client-side hider) ----------

from fastapi import APIRouter  # noqa: E402
from pydantic import BaseModel  # noqa: E402


class PrivacyContext(BaseModel):
    privacy_mode: bool
    min_cohort_size: int
    viewer_user_id: str | None
    viewer_role: str | None
    viewer_root_org_id: str | None
    personal_insight_kinds: list[str]
    any_privacy_on: bool


context_router = APIRouter(tags=["privacy"])


@context_router.get("/privacy/context")
@privacy_surface(Visibility.PUBLIC)
def privacy_context(request: Request) -> PrivacyContext:
    caller = _caller_from_request(request)
    priv_on = False
    min_size = 3
    if caller.root_org_id:
        root = OrgNode.get(caller.root_org_id)
        if root:
            priv_on = root.privacy_mode
            min_size = root.min_cohort_size
    return PrivacyContext(
        privacy_mode=priv_on,
        min_cohort_size=min_size,
        viewer_user_id=caller.user_id,
        viewer_role=caller.role,
        viewer_root_org_id=caller.root_org_id,
        personal_insight_kinds=sorted(PERSONAL_INSIGHT_KINDS),
        any_privacy_on=_any_privacy_on(),
    )

"""Org-wide analytics endpoint — aggregated slices for the /exec/analytics dashboard.

Everything is computed over the same trailing WINDOW_DAYS as the cost endpoint
so values, subscriptions, and ROI are apples-to-apples.

The response bundles every slice the dashboard needs (department rollups,
per-user rows, weekly trend, hour×weekday heatmap, provider mix) so the page
does one fetch instead of N.
"""

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from seerai.cost.endpoint import (
    WINDOW_DAYS,
    UtilityBreakdown,
    _window_cutoff,
    session_value,
)
from seerai.entities import OrgNode, Session, Subscription, User
from seerai.privacy import Visibility, privacy_surface

router = APIRouter(tags=["analytics"])

# Weeks of history for the trend chart — ~a quarter.
TREND_WEEKS = 13


class DepartmentStats(BaseModel):
    """One row of the department rollup charts.

    A "department" is an org node that sits directly under the requested root
    — e.g. when called on `acme`, the three departments are Engineering,
    Product, Sales. Users in sub-departments (like `acme-eng-backend`) are
    aggregated up to their depth-1 ancestor.
    """

    org_id: str
    name: str
    user_count: int
    active_user_count: int  # users with ≥1 session in the window
    session_count: int
    message_count: int
    subscription_cost: float  # $/mo
    estimated_value: float  # $/window
    roi: float | None
    utility: UtilityBreakdown
    provider_counts: dict[str, int]


class UserStat(BaseModel):
    """Per-user row for the leaderboard and scatter charts."""

    user_id: str
    org_id: str | None
    dept_id: str | None  # depth-1 ancestor — used to color scatter points
    dept_name: str | None
    hourly_rate: float | None
    session_count: int
    useful_count: int
    harmful_count: int
    estimated_value: float
    subscription_cost: float
    roi: float | None
    primary_provider: str | None
    utility: UtilityBreakdown


class WeeklyBucket(BaseModel):
    """One bar in the weekly trend chart."""

    week_start: str  # ISO date (Monday)
    non_work: int = 0
    trivial: int = 0
    useful: int = 0
    harmful: int = 0
    unclassified: int = 0

    @property
    def total(self) -> int:
        return (
            self.non_work
            + self.trivial
            + self.useful
            + self.harmful
            + self.unclassified
        )


class AnalyticsResponse(BaseModel):
    org_id: str
    org_name: str
    window_days: int
    user_count: int
    active_user_count: int
    session_count: int
    message_count: int
    total_subscription_cost: float
    total_estimated_value: float
    roi: float | None
    utility: UtilityBreakdown
    provider_totals: dict[str, int]
    departments: list[DepartmentStats]
    users: list[UserStat]
    weekly: list[WeeklyBucket]
    # hour_weekday[weekday][hour] — weekday 0=Mon..6=Sun, UTC.
    hour_weekday: list[list[int]]


def _add_utility(u: UtilityBreakdown, label: str | None) -> None:
    if label == "non_work":
        u.non_work += 1
    elif label == "trivial":
        u.trivial += 1
    elif label == "useful":
        u.useful += 1
    elif label == "harmful":
        u.harmful += 1
    else:
        u.unclassified += 1


def _week_start(d: date) -> date:
    """Monday of the ISO week containing d."""
    return d - timedelta(days=d.weekday())


@router.get("/analytics/org/{org_id}")
@privacy_surface(Visibility.AGGREGATE, strip=("users",))
def org_analytics(org_id: str) -> AnalyticsResponse:
    """Aggregated slices for the analytics dashboard.

    Scope is the requested org and all descendants. Departments are the
    immediate children (depth = org.depth+1); users in deeper sub-orgs roll
    up to their nearest department ancestor.
    """
    descendants = OrgNode.query("path", "array_contains", org_id)
    root = next((n for n in descendants if n.org_id == org_id), None)
    if root is None:
        raise HTTPException(404, "Org not found")

    by_id = {n.org_id: n for n in descendants}
    dept_depth = root.depth + 1

    def dept_ancestor(org_node: OrgNode) -> OrgNode:
        """Depth-1 ancestor under the requested root (or the node itself if leaf)."""
        if org_node.depth <= dept_depth:
            return org_node
        # Walk path: path is ordered root→leaf. The entry at index dept_depth is
        # the department for this node.
        return by_id[org_node.path[dept_depth]]

    # Departments: either immediate children, or — if root has no children —
    # the root itself so the page still renders a single-row bar.
    dept_nodes = [n for n in descendants if n.parent_id == org_id]
    if not dept_nodes:
        dept_nodes = [root]

    # Load all users under the root (batch in 30s — Firestore 'in' limit).
    org_ids = list(by_id.keys())
    users: list[User] = []
    for i in range(0, len(org_ids), 30):
        users.extend(User.query("org_id", "in", org_ids[i : i + 30]))
    user_ids = {u.user_id for u in users}

    # Load active subscriptions once, bucket by user.
    subs_by_user: dict[str, list[Subscription]] = defaultdict(list)
    for s in Subscription.list(order_by=None, limit=0):
        if s.user_id in user_ids and s.ended_at is None:
            subs_by_user[s.user_id].append(s)

    # Pre-compute department assignment for every user.
    user_dept: dict[str, OrgNode] = {}
    for u in users:
        if u.org_id and u.org_id in by_id:
            user_dept[u.user_id] = dept_ancestor(by_id[u.org_id])

    cutoff = _window_cutoff()
    # Weekly trend covers TREND_WEEKS ending with the current week — this is
    # wider than the 30-day value window on purpose: 30 days is ~4 weeks,
    # which isn't enough to show a trend.
    this_week = _week_start(datetime.now(UTC).date())
    trend_start = this_week - timedelta(weeks=TREND_WEEKS - 1)
    trend_cutoff = datetime.combine(trend_start, datetime.min.time(), tzinfo=UTC)
    week_keys = [
        (trend_start + timedelta(weeks=i)).isoformat() for i in range(TREND_WEEKS)
    ]
    weekly_map: dict[str, WeeklyBucket] = {
        k: WeeklyBucket(week_start=k) for k in week_keys
    }

    # 7×24 grid of session counts — UTC for now (no per-user timezone yet).
    hour_weekday: list[list[int]] = [[0] * 24 for _ in range(7)]

    # Department + user accumulators.
    dept_acc: dict[str, dict] = {
        d.org_id: {
            "user_count": 0,
            "active_users": set(),
            "sessions": 0,
            "messages": 0,
            "subscription": 0.0,
            "value": 0.0,
            "utility": UtilityBreakdown(),
            "providers": Counter(),
        }
        for d in dept_nodes
    }
    user_stats: list[UserStat] = []
    utility_totals = UtilityBreakdown()
    provider_totals: Counter[str] = Counter()

    active_user_count = 0
    total_sessions = 0
    total_messages = 0
    total_value = 0.0
    total_subscription = 0.0

    # Single pass over users → sessions.
    for u in users:
        dept = user_dept.get(u.user_id)
        dept_id = dept.org_id if dept else None
        if dept_id and dept_id in dept_acc:
            dept_acc[dept_id]["user_count"] += 1

        subs = subs_by_user.get(u.user_id, [])
        sub_cost = sum(s.monthly_cost_cents for s in subs) / 100.0
        total_subscription += sub_cost
        if dept_id and dept_id in dept_acc:
            dept_acc[dept_id]["subscription"] += sub_cost

        sessions = Session.for_user(u.user_id, order_by="last_event_at", limit=0)

        if any(s.last_event_at >= cutoff for s in sessions):
            active_user_count += 1
            if dept_id and dept_id in dept_acc:
                dept_acc[dept_id]["active_users"].add(u.user_id)

        rate = u.hourly_rate or 0.0
        u_value = 0.0
        u_util = UtilityBreakdown()
        u_providers: Counter[str] = Counter()
        u_messages = 0
        u_useful = 0
        u_harmful = 0
        u_sessions_30d = 0

        for s in sessions:
            in_roi_window = s.last_event_at >= cutoff
            in_trend_window = s.last_event_at >= trend_cutoff

            # ROI / value / utility / provider rollups use the 30-day window so
            # they match subscription billing and the /api/cost endpoint.
            if in_roi_window:
                u_sessions_30d += 1
                u_messages += s.event_count
                _add_utility(u_util, s.utility)
                _add_utility(utility_totals, s.utility)
                if s.utility == "useful":
                    u_useful += 1
                elif s.utility == "harmful":
                    u_harmful += 1
                u_value += session_value(rate, s.event_count, s.utility)

                if s.provider:
                    u_providers[s.provider] += 1
                    provider_totals[s.provider] += 1
                if dept_id and dept_id in dept_acc:
                    dept_acc[dept_id]["sessions"] += 1
                    dept_acc[dept_id]["messages"] += s.event_count
                    _add_utility(dept_acc[dept_id]["utility"], s.utility)
                    if s.provider:
                        dept_acc[dept_id]["providers"][s.provider] += 1

                # Hour × weekday only uses recent data (current cultural signal,
                # not historical).
                ts = s.last_event_at
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                hour_weekday[ts.weekday()][ts.hour] += 1

            # Weekly trend uses the wider 13-week window so the chart actually
            # shows a trend rather than 4 near-identical bars.
            if in_trend_window:
                wk = _week_start(s.last_event_at.date()).isoformat()
                if wk in weekly_map:
                    bucket = weekly_map[wk]
                    if s.utility == "non_work":
                        bucket.non_work += 1
                    elif s.utility == "trivial":
                        bucket.trivial += 1
                    elif s.utility == "useful":
                        bucket.useful += 1
                    elif s.utility == "harmful":
                        bucket.harmful += 1
                    else:
                        bucket.unclassified += 1

        total_sessions += u_sessions_30d
        total_messages += u_messages
        total_value += u_value
        if dept_id and dept_id in dept_acc:
            dept_acc[dept_id]["value"] += u_value

        primary_provider = u_providers.most_common(1)[0][0] if u_providers else None
        user_roi = u_value / sub_cost if sub_cost > 0 else None
        user_stats.append(
            UserStat(
                user_id=u.user_id,
                org_id=u.org_id,
                dept_id=dept_id,
                dept_name=dept.name if dept else None,
                hourly_rate=u.hourly_rate,
                session_count=u_sessions_30d,
                useful_count=u_useful,
                harmful_count=u_harmful,
                estimated_value=round(u_value, 2),
                subscription_cost=round(sub_cost, 2),
                roi=round(user_roi, 2) if user_roi is not None else None,
                primary_provider=primary_provider,
                utility=u_util,
            )
        )

    # Sort leaderboard by value desc — the most interesting row is on top.
    user_stats.sort(key=lambda x: x.estimated_value, reverse=True)

    # Build department rows in the order they appear under the root.
    departments: list[DepartmentStats] = []
    for d in dept_nodes:
        acc = dept_acc[d.org_id]
        sub = acc["subscription"]
        value = acc["value"]
        roi = value / sub if sub > 0 else None
        departments.append(
            DepartmentStats(
                org_id=d.org_id,
                name=d.name,
                user_count=acc["user_count"],
                active_user_count=len(acc["active_users"]),
                session_count=acc["sessions"],
                message_count=acc["messages"],
                subscription_cost=round(sub, 2),
                estimated_value=round(value, 2),
                roi=round(roi, 2) if roi is not None else None,
                utility=acc["utility"],
                provider_counts=dict(acc["providers"]),
            )
        )
    # Order departments by value desc so the most valuable dept is first —
    # matches how the frontend charts want to display them.
    departments.sort(key=lambda d: d.estimated_value, reverse=True)

    overall_roi = total_value / total_subscription if total_subscription > 0 else None

    return AnalyticsResponse(
        org_id=org_id,
        org_name=root.name,
        window_days=WINDOW_DAYS,
        user_count=len(users),
        active_user_count=active_user_count,
        session_count=total_sessions,
        message_count=total_messages,
        total_subscription_cost=round(total_subscription, 2),
        total_estimated_value=round(total_value, 2),
        roi=round(overall_roi, 2) if overall_roi is not None else None,
        utility=utility_totals,
        provider_totals=dict(provider_totals),
        departments=departments,
        users=user_stats,
        weekly=[weekly_map[k] for k in week_keys],
        hour_weekday=hour_weekday,
    )


@router.get("/analytics")
@privacy_surface(Visibility.AGGREGATE, strip=("users",))
def analytics_for_user(user_id: str | None = None) -> AnalyticsResponse:
    """Convenience route — returns analytics for the requesting user's root org.

    Called by the dashboard when the exec user doesn't pick a specific org.
    Admins (no org) get a 400 here; the frontend handles admin separately
    by iterating root orgs.
    """
    if not user_id:
        raise HTTPException(400, "user_id required")
    u = User.get(user_id)
    if not u or not u.org_id:
        raise HTTPException(404, "User or org not found")
    org = OrgNode.get(u.org_id)
    if not org:
        raise HTTPException(404, "Org not found")
    root_id = org.path[0]
    return org_analytics(root_id)

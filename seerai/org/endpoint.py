from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from seerai.entities import OrgNode, Session, User
from seerai.models import OrgNodeStats
from seerai.privacy import (
    Visibility,
    _caller_from_request,
    privacy_surface,
)

router = APIRouter(tags=["org"])


class CreateOrgRequest(BaseModel):
    org_id: str
    name: str
    parent_id: str | None = None


class AssignOrgRequest(BaseModel):
    org_id: str


class PrivacySettings(BaseModel):
    privacy_mode: bool
    min_cohort_size: int


@router.post("/orgs")
@privacy_surface(Visibility.PUBLIC)
def create_org(req: CreateOrgRequest) -> OrgNode:
    if req.parent_id:
        parent = OrgNode.get(req.parent_id)
        if not parent:
            raise HTTPException(404, "Parent org not found")
        path = parent.path + [req.org_id]
        depth = parent.depth + 1
    else:
        path = [req.org_id]
        depth = 0

    node = OrgNode(
        org_id=req.org_id,
        name=req.name,
        parent_id=req.parent_id,
        path=path,
        depth=depth,
    )
    node.save(merge=False)
    return node


@router.get("/orgs")
@privacy_surface(Visibility.PUBLIC)
def list_root_orgs() -> list[OrgNode]:
    return OrgNode.query("depth", "==", 0)


@router.get("/orgs/{org_id}")
@privacy_surface(Visibility.PUBLIC)
def get_org(org_id: str) -> OrgNode:
    node = OrgNode.get(org_id)
    if not node:
        raise HTTPException(404, "Org not found")
    return node


def _get_descendants(org_id: str) -> list[OrgNode]:
    """All org nodes that have org_id in their path (includes the node itself)."""
    return OrgNode.query("path", "array_contains", org_id)


def _compute_stats(descendants: list[OrgNode]) -> dict[str, OrgNodeStats]:
    """Compute aggregate stats for each org node from its descendant users/sessions."""
    org_ids = {n.org_id for n in descendants}

    # Build parent->children map
    children_map: dict[str | None, list[str]] = defaultdict(list)
    for n in descendants:
        children_map[n.parent_id].append(n.org_id)

    # Load users for all org_ids — Firestore 'in' limited to 30
    users_by_org: dict[str, list[User]] = defaultdict(list)
    org_id_list = list(org_ids)
    for i in range(0, len(org_id_list), 30):
        batch = org_id_list[i : i + 30]
        for u in User.query("org_id", "in", batch):
            users_by_org[u.org_id].append(u)

    # Load session stats per user
    user_stats: dict[str, tuple[int, int, int]] = {}
    for org_users in users_by_org.values():
        for u in org_users:
            if u.user_id in user_stats:
                continue
            sessions = Session.for_user(u.user_id, order_by="last_event_at", limit=0)
            s_count, m_count, e_count = 0, 0, 0
            for s in sessions:
                s_count += 1
                m_count += s.event_count
                e_count += s.error_count
            user_stats[u.user_id] = (s_count, m_count, e_count)

    # Direct stats per org node
    direct: dict[str, OrgNodeStats] = {}
    for n in descendants:
        u_count, s_count, m_count, e_count = 0, 0, 0, 0
        for u in users_by_org.get(n.org_id, []):
            u_count += 1
            us, um, ue = user_stats.get(u.user_id, (0, 0, 0))
            s_count += us
            m_count += um
            e_count += ue
        direct[n.org_id] = OrgNodeStats(
            org_id=n.org_id,
            name=n.name,
            parent_id=n.parent_id,
            depth=n.depth,
            user_count=u_count,
            session_count=s_count,
            message_count=m_count,
            error_count=e_count,
        )

    # Bottom-up aggregation
    by_depth = sorted(descendants, key=lambda n: n.depth, reverse=True)
    aggregated = {oid: OrgNodeStats(**s.model_dump()) for oid, s in direct.items()}

    for n in by_depth:
        for child_id in children_map.get(n.org_id, []):
            child = aggregated[child_id]
            parent = aggregated[n.org_id]
            aggregated[n.org_id] = OrgNodeStats(
                org_id=parent.org_id,
                name=parent.name,
                parent_id=parent.parent_id,
                depth=parent.depth,
                user_count=parent.user_count + child.user_count,
                session_count=parent.session_count + child.session_count,
                message_count=parent.message_count + child.message_count,
                error_count=parent.error_count + child.error_count,
            )

    return aggregated


class OrgTreeNode(BaseModel):
    node: OrgNodeStats
    children: list["OrgTreeNode"]


@router.get("/orgs/{org_id}/tree")
@privacy_surface(Visibility.AGGREGATE)
def get_org_tree(org_id: str) -> OrgTreeNode:
    descendants = _get_descendants(org_id)
    if not any(n.org_id == org_id for n in descendants):
        raise HTTPException(404, "Org not found")

    stats = _compute_stats(descendants)

    children_map: dict[str | None, list[OrgNode]] = defaultdict(list)
    for n in descendants:
        if n.org_id != org_id:
            children_map[n.parent_id].append(n)

    def build(oid: str) -> OrgTreeNode:
        return OrgTreeNode(
            node=stats[oid],
            children=[build(c.org_id) for c in children_map.get(oid, [])],
        )

    return build(org_id)


@router.get("/orgs/{org_id}/children")
@privacy_surface(Visibility.AGGREGATE)
def get_org_children(org_id: str) -> list[OrgNodeStats]:
    if not OrgNode.get(org_id):
        raise HTTPException(404, "Org not found")

    descendants = _get_descendants(org_id)
    stats = _compute_stats(descendants)
    return [stats[n.org_id] for n in descendants if n.parent_id == org_id]


@router.get("/orgs/{org_id}/users")
@privacy_surface(Visibility.INDIVIDUAL)
def get_org_users(org_id: str) -> list[User]:
    descendants = _get_descendants(org_id)
    if not any(n.org_id == org_id for n in descendants):
        raise HTTPException(404, "Org not found")

    org_ids = [n.org_id for n in descendants]
    users: list[User] = []
    for i in range(0, len(org_ids), 30):
        batch = org_ids[i : i + 30]
        users.extend(User.query("org_id", "in", batch))
    return sorted(users, key=lambda u: u.last_active, reverse=True)


@router.put("/users/{user_id}/org")
@privacy_surface(Visibility.PUBLIC)
def assign_user_org(user_id: str, req: AssignOrgRequest) -> User:
    if not OrgNode.get(req.org_id):
        raise HTTPException(404, "Org not found")

    user = User.get(user_id)
    if not user:
        raise HTTPException(404, "User not found")

    user.org_id = req.org_id
    user.sync()
    return user


# ---------- privacy settings (admin-gated PUT) ----------


@router.get("/orgs/{org_id}/privacy")
@privacy_surface(Visibility.PUBLIC)
def get_privacy_settings(org_id: str) -> PrivacySettings:
    node = OrgNode.get(org_id)
    if not node:
        raise HTTPException(404, "Org not found")
    root = OrgNode.get(node.path[0]) if node.path else node
    return PrivacySettings(
        privacy_mode=root.privacy_mode,
        min_cohort_size=root.min_cohort_size,
    )


@router.put("/orgs/{org_id}/privacy")
@privacy_surface(Visibility.PUBLIC)
def put_privacy_settings(
    org_id: str, req: PrivacySettings, request: Request
) -> PrivacySettings:
    """Set privacy mode on the org's root. Platform admin or same-company exec."""
    node = OrgNode.get(org_id)
    if not node:
        raise HTTPException(404, "Org not found")
    root_id = node.path[0] if node.path else node.org_id
    root = OrgNode.get(root_id)
    if not root:
        raise HTTPException(404, "Root org not found")

    caller = _caller_from_request(request)
    allowed = caller.role == "admin" or (
        caller.role == "exec" and caller.root_org_id == root_id
    )
    if not allowed:
        raise HTTPException(
            403, "Only platform admin or same-company exec can change privacy"
        )

    if req.min_cohort_size < 2:
        raise HTTPException(400, "min_cohort_size must be >= 2")

    root.privacy_mode = bool(req.privacy_mode)
    root.min_cohort_size = int(req.min_cohort_size)
    root.sync()
    return PrivacySettings(
        privacy_mode=root.privacy_mode,
        min_cohort_size=root.min_cohort_size,
    )

from collections import defaultdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from seerai.firestore_client import get_firestore_client
from seerai.models import OrgNode, OrgNodeStats, UserSummary

router = APIRouter(tags=["org"])


class CreateOrgRequest(BaseModel):
    org_id: str
    name: str
    parent_id: str | None = None


class AssignOrgRequest(BaseModel):
    org_id: str


@router.post("/orgs")
def create_org(req: CreateOrgRequest) -> OrgNode:
    db = get_firestore_client()

    if req.parent_id:
        parent_doc = db.collection("orgs").document(req.parent_id).get()
        if not parent_doc.exists:
            raise HTTPException(404, "Parent org not found")
        parent = parent_doc.to_dict()
        path = parent["path"] + [req.org_id]
        depth = parent["depth"] + 1
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
    db.collection("orgs").document(req.org_id).set(node.model_dump())
    return node


@router.get("/orgs")
def list_root_orgs() -> list[OrgNode]:
    db = get_firestore_client()
    docs = db.collection("orgs").where("depth", "==", 0).stream()
    return [OrgNode(**doc.to_dict()) for doc in docs]


@router.get("/orgs/{org_id}")
def get_org(org_id: str) -> OrgNode:
    db = get_firestore_client()
    doc = db.collection("orgs").document(org_id).get()
    if not doc.exists:
        raise HTTPException(404, "Org not found")
    return OrgNode(**doc.to_dict())


def _get_descendants(db, org_id: str) -> list[OrgNode]:
    """All org nodes that have org_id in their path (includes the node itself)."""
    docs = db.collection("orgs").where("path", "array_contains", org_id).stream()
    return [OrgNode(**doc.to_dict()) for doc in docs]


def _compute_stats(db, nodes: list[OrgNode]) -> dict[str, OrgNodeStats]:
    """Compute aggregate stats for each org node from its descendant users/sessions."""
    org_ids = {n.org_id for n in nodes}

    # Build parent→children map for bottom-up aggregation
    children_map: dict[str | None, list[str]] = defaultdict(list)
    for n in nodes:
        children_map[n.parent_id].append(n.org_id)

    # Load users for all org_ids — Firestore 'in' limited to 30
    users_by_org: dict[str, list[dict]] = defaultdict(list)
    org_id_list = list(org_ids)
    for i in range(0, len(org_id_list), 30):
        batch = org_id_list[i : i + 30]
        docs = db.collection("users").where("org_id", "in", batch).stream()
        for doc in docs:
            d = doc.to_dict()
            users_by_org[d["org_id"]].append(d)

    # Load session stats per user
    user_stats: dict[
        str, tuple[int, int, int]
    ] = {}  # uid → (sessions, messages, errors)
    for org_users in users_by_org.values():
        for u in org_users:
            uid = u["user_id"]
            if uid in user_stats:
                continue
            sessions = (
                db.collection("users").document(uid).collection("sessions").stream()
            )
            s_count, m_count, e_count = 0, 0, 0
            for s in sessions:
                sd = s.to_dict()
                s_count += 1
                m_count += sd.get("event_count", 0)
                e_count += sd.get("error_count", 0)
            user_stats[uid] = (s_count, m_count, e_count)

    # Direct stats per org node (only its directly assigned users)
    direct: dict[str, OrgNodeStats] = {}
    for n in nodes:
        u_count, s_count, m_count, e_count = 0, 0, 0, 0
        for u in users_by_org.get(n.org_id, []):
            uid = u["user_id"]
            u_count += 1
            us, um, ue = user_stats.get(uid, (0, 0, 0))
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

    # Bottom-up aggregation: add children's stats to parent
    # Process deepest nodes first
    by_depth = sorted(nodes, key=lambda n: n.depth, reverse=True)
    aggregated: dict[str, OrgNodeStats] = {
        oid: OrgNodeStats(**s.model_dump()) for oid, s in direct.items()
    }

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
def get_org_tree(org_id: str) -> OrgTreeNode:
    db = get_firestore_client()
    descendants = _get_descendants(db, org_id)
    if not any(n.org_id == org_id for n in descendants):
        raise HTTPException(404, "Org not found")

    stats = _compute_stats(db, descendants)

    # Build tree recursively
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
def get_org_children(org_id: str) -> list[OrgNodeStats]:
    db = get_firestore_client()
    # Verify parent exists
    parent_doc = db.collection("orgs").document(org_id).get()
    if not parent_doc.exists:
        raise HTTPException(404, "Org not found")

    descendants = _get_descendants(db, org_id)
    stats = _compute_stats(db, descendants)
    return [stats[n.org_id] for n in descendants if n.parent_id == org_id]


@router.get("/orgs/{org_id}/users")
def get_org_users(org_id: str) -> list[UserSummary]:
    db = get_firestore_client()
    descendants = _get_descendants(db, org_id)
    if not any(n.org_id == org_id for n in descendants):
        raise HTTPException(404, "Org not found")

    org_ids = [n.org_id for n in descendants]
    users = []
    for i in range(0, len(org_ids), 30):
        batch = org_ids[i : i + 30]
        docs = db.collection("users").where("org_id", "in", batch).stream()
        for doc in docs:
            d = doc.to_dict()
            users.append(
                UserSummary(
                    user_id=d["user_id"],
                    last_active=d["last_active"],
                    org_id=d.get("org_id"),
                )
            )
    return sorted(users, key=lambda u: u.last_active, reverse=True)


@router.put("/users/{user_id}/org")
def assign_user_org(user_id: str, req: AssignOrgRequest) -> UserSummary:
    db = get_firestore_client()

    # Verify org exists
    org_doc = db.collection("orgs").document(req.org_id).get()
    if not org_doc.exists:
        raise HTTPException(404, "Org not found")

    # Verify user exists
    user_ref = db.collection("users").document(user_id)
    user_doc = user_ref.get()
    if not user_doc.exists:
        raise HTTPException(404, "User not found")

    user_ref.update({"org_id": req.org_id})
    updated = user_ref.get().to_dict()
    return UserSummary(**updated)

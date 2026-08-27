from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from ..config import settings


def _id(p: str) -> str:
    return f"{p}_{uuid.uuid4().hex[:10]}"


# role -> allowed permission verbs ("*" = all)
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": {"*"},
    "admin": {"leads:*", "agents:*", "campaigns:*", "calls:*", "billing:read",
              "reports:read", "team:manage"},
    "manager": {"leads:*", "campaigns:*", "calls:*", "reports:read"},
    "agent": {"leads:read", "calls:create", "calls:read", "calls:turn"},
    "viewer": {"leads:read", "calls:read", "reports:read"},
}


@dataclass
class Team:
    org_id: str
    name: str
    id: str = field(default_factory=lambda: _id("team"))
    members: dict = field(default_factory=dict)  # user_id -> role


class RBACError(Exception):
    pass


class TeamService:
    def __init__(self) -> None:
        self.teams: dict[str, Team] = {}

    def create(self, org_id: str, name: str) -> Team:
        team = Team(org_id=org_id, name=name)
        self.teams[team.id] = team
        return team

    def add_member(self, team_id: str, user_id: str, role: str = "agent") -> dict:
        team = self.teams.get(team_id)
        if not team:
            return {"ok": False, "error": "unknown_team"}
        if role not in ROLE_PERMISSIONS:
            return {"ok": False, "error": f"unknown_role:{role}"}
        team.members[user_id] = role
        return {"ok": True, "team_id": team_id, "user_id": user_id, "role": role}

    def role_of(self, team_id: str, user_id: str) -> str | None:
        team = self.teams.get(team_id)
        return team.members.get(user_id) if team else None


def permitted(role: str, permission: str) -> bool:
    """True if `role` may perform `permission` (e.g. 'calls:create')."""
    perms = ROLE_PERMISSIONS.get(role, set())
    if "*" in perms or permission in perms:
        return True
    resource = permission.split(":", 1)[0]
    return f"{resource}:*" in perms


def enforce(role: str, permission: str) -> None:
    if not settings.rbac_enabled:
        return  # RBAC off in local dev; flip RBAC_ENABLED=1 to turn on.
    if not permitted(role, permission):
        raise RBACError(f"forbidden:{role}:{permission}")


teams = TeamService()

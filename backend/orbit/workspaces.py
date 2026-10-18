"""An owner's workspace: chosen sector, one business profile per sector, one action list per sector.

Validation lives here (raising ClientError) so the routes only deal with HTTP: cookies, JSON bodies, status codes.
"""

from __future__ import annotations

import math
import secrets
from enum import StrEnum
from typing import Any

from sqlalchemy import delete, select

from .errors import ClientError, NotFoundError
from .extensions import db
from .models import ActionTask, BusinessProfile, Workspace
from .pipeline.lexicon import INDUSTRIES

MAX_TASKS = 500
MAX_NUMBER = 1e9
TEXT_LIMITS = {'company': 160, 'industry': 160, 'location': 160}
PROFILE_NUMBERS = ('revenue', 'margin', 'passThrough', 'loans', 'materials', 'freight', 'power', 'imports', 'exports')
PERCENT_FIELDS = ('passThrough', 'materials', 'freight', 'power', 'imports', 'exports')
COST_SHARE_FIELDS = ('materials', 'freight', 'power')
TOKEN_LENGTH = range(16, 65)


class ResetPart(StrEnum):
    PROFILE = 'profile'
    TASKS = 'tasks'
    ALL = 'all'


# --------------------------------------------------------------------------- validation


def validate_sector(value: Any) -> str:
    if value not in INDUSTRIES:
        raise NotFoundError(f'Unknown sector. Choose one of: {", ".join(INDUSTRIES)}')
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ClientError(f'{name} must be a number')
    if abs(value) > MAX_NUMBER:
        raise ClientError(f'{name} is out of range')
    return value


def clean_profile(body: Any) -> dict[str, Any]:
    """Keep only known fields, with text trimmed and numbers range-checked."""
    if not isinstance(body, dict):
        raise ClientError('Profile must be an object')
    profile: dict[str, Any] = {}
    for key, limit in TEXT_LIMITS.items():
        if key in body:
            if not isinstance(body[key], str):
                raise ClientError(f'{key} must be text')
            profile[key] = body[key].strip()[:limit]
    for key in PROFILE_NUMBERS:
        if key in body:
            profile[key] = _number(body[key], key)
    if profile.get('revenue', 1) <= 0 or not 0 < profile.get('margin', 1) <= 80:
        raise ClientError('Revenue must be positive and margin between 0 and 80')
    for key in PERCENT_FIELDS:
        if not 0 <= profile.get(key, 0) <= 100:
            raise ClientError(f'{key} must be between 0 and 100')
    if sum(profile.get(key, 0) for key in COST_SHARE_FIELDS) > 100:
        raise ClientError('Cost shares must total no more than 100')
    return profile


def clean_tasks(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, list):
        raise ClientError('Tasks must be a list')
    if len(body) > MAX_TASKS:
        raise ClientError(f'At most {MAX_TASKS} tasks')
    seen: set[str] = set()
    tasks: list[dict[str, Any]] = []
    for position, raw in enumerate(body):
        title = raw.get('title') if isinstance(raw, dict) else None
        if not isinstance(title, str) or not title.strip():
            raise ClientError(f'Task {position + 1} needs a title')
        client_id = str(raw.get('id') or f'srv{position}')[:64]
        if client_id in seen:
            raise ClientError(f'Duplicate task id {client_id}')
        seen.add(client_id)
        tasks.append(
            {
                'id': client_id,
                'title': title.strip()[:300],
                'owner': str(raw.get('owner') or '')[:120],
                'due': str(raw.get('due') or '')[:60],
                'signal': str(raw.get('signal') or '')[:64],
                'done': bool(raw.get('done')),
            }
        )
    return tasks


# --------------------------------------------------------------------------- persistence


def find_workspace(token: str) -> Workspace | None:
    if len(token) not in TOKEN_LENGTH:
        return None
    return db.session.scalar(select(Workspace).where(Workspace.token == token))


def create_workspace() -> Workspace:
    workspace = Workspace(token=secrets.token_urlsafe(32))
    db.session.add(workspace)
    db.session.commit()
    return workspace


def snapshot(workspace: Workspace) -> dict[str, Any]:
    profiles = {
        p.sector: p.data
        for p in db.session.scalars(select(BusinessProfile).where(BusinessProfile.workspace_id == workspace.id))
    }
    tasks: dict[str, list[dict[str, Any]]] = {}
    rows = db.session.scalars(
        select(ActionTask)
        .where(ActionTask.workspace_id == workspace.id)
        .order_by(ActionTask.sector, ActionTask.position)
    )
    for task in rows:
        tasks.setdefault(task.sector, []).append(task.to_dict())
    return {'sector': workspace.sector, 'profiles': profiles, 'tasks': tasks}


def set_sector(workspace: Workspace, sector: Any) -> str:
    workspace.sector = validate_sector(sector)
    db.session.commit()
    return workspace.sector


def save_profile(workspace: Workspace, sector: str, body: Any) -> dict[str, Any]:
    sector = validate_sector(sector)
    data = clean_profile(body)
    row = db.session.scalar(
        select(BusinessProfile).where(BusinessProfile.workspace_id == workspace.id, BusinessProfile.sector == sector)
    )
    if row is None:
        db.session.add(BusinessProfile(workspace_id=workspace.id, sector=sector, data=data))
    else:
        row.data = data
    db.session.commit()
    return data


def replace_tasks(workspace: Workspace, sector: str, body: Any) -> list[dict[str, Any]]:
    """Replace this sector's task list. The frontend always sends the whole checklist."""
    sector = validate_sector(sector)
    tasks = clean_tasks(body)
    db.session.execute(delete(ActionTask).where(ActionTask.workspace_id == workspace.id, ActionTask.sector == sector))
    db.session.add_all(
        ActionTask(
            workspace_id=workspace.id,
            sector=sector,
            client_id=task['id'],
            position=position,
            title=task['title'],
            owner=task['owner'],
            due=task['due'],
            signal=task['signal'],
            done=task['done'],
        )
        for position, task in enumerate(tasks)
    )
    db.session.commit()
    return tasks


def reset(workspace: Workspace, sector: str, part: str) -> None:
    """Back to the preset profile and/or no saved actions for one sector."""
    sector = validate_sector(sector)
    try:
        part = ResetPart(part)
    except ValueError:
        raise ClientError('part must be profile, tasks or all') from None
    if part in (ResetPart.PROFILE, ResetPart.ALL):
        db.session.execute(
            delete(BusinessProfile).where(
                BusinessProfile.workspace_id == workspace.id, BusinessProfile.sector == sector
            )
        )
    if part in (ResetPart.TASKS, ResetPart.ALL):
        db.session.execute(
            delete(ActionTask).where(ActionTask.workspace_id == workspace.id, ActionTask.sector == sector)
        )
    db.session.commit()

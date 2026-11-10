from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog, User


def log_action(
    db: Session,
    action: str,
    *,
    actor: User | None = None,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    details: dict | None = None,
    request: Request | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=details,
        ip_address=request.client.host if request is not None and request.client else None,
    )
    db.add(entry)
    return entry

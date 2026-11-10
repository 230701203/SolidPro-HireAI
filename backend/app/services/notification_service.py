from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AccountStatus, Notification, Role, User
from app.services import email_service


def notify(
    db: Session, user_id: int, type_: str, title: str, message: str, link: str | None = None
) -> Notification:
    n = Notification(user_id=user_id, type=type_, title=title, message=message, link=link)
    db.add(n)
    return n


def active_admins(db: Session) -> list[User]:
    return list(
        db.scalars(select(User).where(User.role == Role.ADMIN, User.status == AccountStatus.ACTIVE)).all()
    )


def notify_admins(
    db: Session,
    background: BackgroundTasks | None,
    *,
    type_: str,
    title: str,
    message: str,
    link: str | None = None,
    email_subject: str | None = None,
    email_button: tuple[str, str] | None = None,
) -> None:
    """In-app notification for every active admin, plus an email when email_subject is given."""
    for admin in active_admins(db):
        notify(db, admin.id, type_, title, message, link)
        if email_subject:
            email_service.queue_email(
                db,
                background,
                to_email=admin.email,
                subject=email_subject,
                template=type_,
                title=title,
                paragraphs=[message],
                button=email_button,
                user_id=admin.id,
            )

"""Reminders for evaluations that have waited too long in review."""

# ruff: noqa: F811
from datetime import timedelta

from sqlalchemy import select, update

from app.database import SessionLocal
from app.models import EvaluationResult, Notification
from app.models.base import utcnow
from app.services import evaluation_service
from tests.conftest import recruiter, user_id
from tests.test_evaluation import case, eval_id, marker, take  # noqa: F401


def _reminders(uid: int):
    with SessionLocal() as db:
        return db.scalars(select(Notification).where(Notification.user_id == uid, Notification.type == "review_reminder")).all()


def _sweep() -> int:
    with SessionLocal() as db:
        return evaluation_service.remind_reviewers(db)


def _age(hours: int):
    with SessionLocal() as db:
        db.execute(update(EvaluationResult).values(created_at=utcnow() - timedelta(hours=hours)))
        db.commit()


def test_recent_drafts_and_nothing_waiting_send_no_reminder(admin, case):
    o, ap, a, dd, s = case
    assert _sweep() == 0  # no evaluation yet
    take(admin, ap, dd, s, speak=lambda i, sent: marker(sent))
    assert _sweep() == 0  # draft exists but is fresh
    assert _reminders(user_id(admin)) == []


def test_only_people_who_can_review_that_opening_are_reminded_once_per_period(admin, case):
    o, ap, a, dd, s = case
    take(admin, ap, dd, s, speak=lambda i, sent: marker(sent))
    mine = recruiter(admin, "rev1@solidpro-test.com", perms=("review_results",))
    unassigned = recruiter(admin, "rev2@solidpro-test.com", perms=("review_results",))
    noperm = recruiter(admin, "rev3@solidpro-test.com", perms=("review_applications",))
    admin.patch(f"/api/job-openings/{o['id']}", json={"assigned_employee_ids": [user_id(mine), user_id(noperm)]})
    _age(30)

    assert _sweep() == 2  # the admin and the assigned reviewer
    adm = _reminders(user_id(admin))
    assert len(adm) == 1 and adm[0].link == "/results?filter=draft" and "1 assessment result has been waiting" in adm[0].message
    assert len(_reminders(user_id(mine))) == 1
    assert _reminders(user_id(unassigned)) == [] and _reminders(user_id(noperm)) == []
    # no candidate name or email in the text
    assert "Jane" not in adm[0].message and "@" not in adm[0].message

    assert _sweep() == 0  # not again within the period
    with SessionLocal() as db:
        db.execute(update(Notification).where(Notification.type == "review_reminder").values(created_at=utcnow() - timedelta(hours=25)))
        db.commit()
    assert _sweep() == 2  # a new period, still waiting
    assert len(_reminders(user_id(admin))) == 2


def test_approved_evaluations_are_not_reminded(admin, case):
    o, ap, a, dd, s = case
    take(admin, ap, dd, s, speak=lambda i, sent: marker(sent))
    assert admin.post(f"/api/evaluations/{eval_id(admin, s)}/finalize").status_code in (200, 201)
    _age(48)
    assert _sweep() == 0


def test_sweeper_pass_reports_reminders(admin, case):
    o, ap, a, dd, s = case
    take(admin, ap, dd, s, speak=lambda i, sent: marker(sent))
    _age(30)
    with SessionLocal() as db:
        assert evaluation_service.sweep(db)["review_reminders"] == 1

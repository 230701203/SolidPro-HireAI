"""Recruitment analytics. Every figure is computed from database rows, restricted to what the viewer may see.

Definitions (also returned in `notes` so the UI can show them next to the numbers):
* pending      = submitted + under review + info requested (current status).
* decided      = approved + shortlisted + selected + rejected (current status). Withdrawn is excluded.
* approval rate / rejection rate use `decided` as the denominator.
* funnel stages count applications that *ever* reached the stage (from status history / schedules / evaluations).
* shortlisting rate = ever shortlisted / evaluations finalised; selection rate = ever selected / ever shortlisted.
* attendance rate = attended / (attended + missed). Future and cancelled schedules are excluded.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    ApplicationStatus,
    ApplicationStatusHistory,
    AnalysisStatus,
    AssessmentSchedule,
    AttemptStatus,
    CandidateProfile,
    EmployeeAssignment,
    EvaluationItem,
    EvaluationResult,
    EvaluationStatus,
    JobApplication,
    JobCategory,
    JobOpening,
    ResumeAnalysisReport,
    Role,
    ScheduleStatus,
    TestAttempt,
    User,
)
from app.models.base import utcnow
from app.services import access

AS = ApplicationStatus
PENDING = (AS.SUBMITTED, AS.UNDER_REVIEW, AS.INFO_REQUESTED)
PASSED_SCREEN = (AS.APPROVED, AS.SHORTLISTED, AS.SELECTED)
DECIDED = (*PASSED_SCREEN, AS.REJECTED)
BUCKETS = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 101)]

NOTES = [
    "Pending = submitted, under review or info requested.",
    "Approval and rejection rates use decided applications (approved, shortlisted, selected, rejected) as the denominator; withdrawn is excluded.",
    "Funnel stages count applications that ever reached the stage.",
    "Shortlisting rate = shortlisted / evaluations finalised. Selection rate = selected / shortlisted.",
    "Attendance rate = attended / (attended + missed); cancelled and upcoming schedules are excluded.",
    "Match scores are advisory AI/mock scores (reviewer override used where present). Small samples are not meaningful.",
]


@dataclass
class Filters:
    date_from: date | None = None
    date_to: date | None = None
    opening_id: int | None = None
    category_id: int | None = None
    employee_id: int | None = None


def require(db: Session, user: User) -> None:
    if user.role not in (Role.ADMIN, Role.EMPLOYEE):
        raise AppError(404, "not_found", "Not found.")
    access.require_perm(db, user, "view_analytics")


def _pct(n: int, d: int) -> float | None:
    return round(100 * n / d, 1) if d else None


def _avg(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 1) if xs else None


def _opening_ids(db: Session, user: User, f: Filters) -> list[int]:
    stmt = select(JobOpening.id)
    scope = access.staff_scope(db, user)
    if scope is not None:
        stmt = stmt.where(JobOpening.id.in_(scope))
    if f.opening_id:
        stmt = stmt.where(JobOpening.id == f.opening_id)
    if f.category_id:
        stmt = stmt.where(JobOpening.category_id == f.category_id)
    if f.employee_id:
        if user.role != Role.ADMIN:
            raise AppError(403, "forbidden", "Only an administrator can filter by employee.")
        stmt = stmt.where(JobOpening.id.in_(select(EmployeeAssignment.opening_id).where(EmployeeAssignment.employee_id == f.employee_id)))
    return list(db.scalars(stmt).all())


def _month(d: datetime) -> str:
    return d.strftime("%Y-%m")


def recruitment(db: Session, user: User, f: Filters) -> dict:
    ids = _opening_ids(db, user, f)
    stmt = select(JobApplication).where(JobApplication.opening_id.in_(ids))
    if f.date_from:
        stmt = stmt.where(JobApplication.submitted_at >= datetime.combine(f.date_from, time.min, tzinfo=UTC))
    if f.date_to:
        stmt = stmt.where(JobApplication.submitted_at <= datetime.combine(f.date_to, time.max, tzinfo=UTC))
    apps = db.scalars(stmt).all() if ids else []
    app_ids = [a.id for a in apps]
    by_status = Counter(a.status for a in apps)
    total = len(apps)
    decided = sum(by_status[s] for s in DECIDED)

    # ---- per opening / category / month
    openings = {o.id: o for o in db.scalars(select(JobOpening).where(JobOpening.id.in_(ids))).all()} if ids else {}
    cats = {c.id: c.name for c in db.scalars(select(JobCategory)).all()}
    per_opening: dict[int, Counter] = defaultdict(Counter)
    per_cat: dict[int, Counter] = defaultdict(Counter)
    per_month: Counter = Counter()
    for a in apps:
        o = openings[a.opening_id]
        for bucket in (per_opening[o.id], per_cat[o.category_id]):
            bucket["applications"] += 1
            if a.status in PASSED_SCREEN:
                bucket["approved"] += 1
            if a.status == AS.REJECTED:
                bucket["rejected"] += 1
            if a.status == AS.SHORTLISTED:
                bucket["shortlisted"] += 1
            if a.status == AS.SELECTED:
                bucket["selected"] += 1
        per_month[_month(a.submitted_at)] += 1

    # ---- history -> funnel and stage durations
    first: dict[tuple[int, ApplicationStatus], datetime] = {}
    if app_ids:
        for aid, to, at in db.execute(
            select(ApplicationStatusHistory.application_id, ApplicationStatusHistory.to_status, ApplicationStatusHistory.created_at)
            .where(ApplicationStatusHistory.application_id.in_(app_ids), ApplicationStatusHistory.to_status.in_(DECIDED))
            .order_by(ApplicationStatusHistory.created_at)
        ).all():
            first.setdefault((aid, to), at)
    ever = lambda st: {aid for (aid, s) in first if s == st}  # noqa: E731
    ever_approved = ever(AS.APPROVED) | {a.id for a in apps if a.status in PASSED_SCREEN}
    ever_shortlisted = ever(AS.SHORTLISTED) | {a.id for a in apps if a.status in (AS.SHORTLISTED, AS.SELECTED)}
    ever_selected = ever(AS.SELECTED) | {a.id for a in apps if a.status == AS.SELECTED}

    sched_rows = (
        db.execute(
            select(AssessmentSchedule.id, AssessmentSchedule.application_id, AssessmentSchedule.status, AssessmentSchedule.created_at)
            .where(AssessmentSchedule.application_id.in_(app_ids))
        ).all()
        if app_ids else []
    )
    scheduled_apps = {r.application_id for r in sched_rows if r.status != ScheduleStatus.CANCELLED}
    attended = sum(1 for r in sched_rows if r.status in (ScheduleStatus.IN_PROGRESS, ScheduleStatus.COMPLETED))
    missed = sum(1 for r in sched_rows if r.status == ScheduleStatus.EXPIRED)
    completed_apps = (
        set(db.scalars(
            select(AssessmentSchedule.application_id).join(TestAttempt, TestAttempt.schedule_id == AssessmentSchedule.id)
            .where(AssessmentSchedule.application_id.in_(app_ids), TestAttempt.status == AttemptStatus.SUBMITTED)
        ).all())
        if app_ids else set()
    )
    evals = (
        db.execute(
            select(EvaluationResult.application_id, EvaluationResult.percentage, EvaluationResult.created_at)
            .where(EvaluationResult.application_id.in_(app_ids), EvaluationResult.status == EvaluationStatus.FINAL)
        ).all()
        if app_ids else []
    )
    evaluated_apps = {e.application_id for e in evals}
    pcts = [e.percentage for e in evals if e.percentage is not None]
    dist = [{"range": f"{lo}-{min(hi, 100)}", "count": sum(1 for p in pcts if lo <= p < hi)} for lo, hi in BUCKETS]
    perf_month: dict[str, list[float]] = defaultdict(list)
    for e in evals:
        if e.percentage is not None:
            perf_month[_month(e.created_at)].append(e.percentage)

    funnel = [
        {"stage": "Applied", "count": total},
        {"stage": "Approved for assessment", "count": len(ever_approved)},
        {"stage": "Test scheduled", "count": len(scheduled_apps)},
        {"stage": "Test completed", "count": len(completed_apps)},
        {"stage": "Evaluation finalised", "count": len(evaluated_apps)},
        {"stage": "Shortlisted", "count": len(ever_shortlisted)},
        {"stage": "Selected", "count": len(ever_selected)},
    ]

    def days(a_to: ApplicationStatus | None, b_to: ApplicationStatus, subs: dict[int, datetime] | None = None) -> float | None:
        out = []
        for a in apps:
            end = first.get((a.id, b_to))
            start = a.submitted_at if a_to is None else first.get((a.id, a_to))
            if start and end and end >= start:
                out.append((end - start).total_seconds() / 86400)
        return _avg(out)

    durations = [
        {"stage": "Applied → approved", "avg_days": days(None, AS.APPROVED), "sample": sum(1 for a in apps if (a.id, AS.APPROVED) in first)},
        {"stage": "Approved → shortlisted", "avg_days": days(AS.APPROVED, AS.SHORTLISTED), "sample": len(ever(AS.SHORTLISTED))},
        {"stage": "Shortlisted → selected", "avg_days": days(AS.SHORTLISTED, AS.SELECTED), "sample": len(ever(AS.SELECTED))},
    ]

    # ---- AI match scores and skills (latest completed report per application)
    latest: dict[int, ResumeAnalysisReport] = {}
    if app_ids:
        for r in db.scalars(
            select(ResumeAnalysisReport).where(ResumeAnalysisReport.application_id.in_(app_ids), ResumeAnalysisReport.status == AnalysisStatus.COMPLETED)
            .order_by(ResumeAnalysisReport.id)
        ).all():
            latest[r.application_id] = r
    eff = {aid: (r.override_score if r.override_score is not None else r.ai_score) for aid, r in latest.items()}
    scores = [v for v in eff.values() if v is not None]
    matched, missing = Counter(), Counter()
    match_month: dict[str, list[float]] = defaultdict(list)
    for aid, r in latest.items():
        for s in (r.report or {}).get("matched_required_skills", []):
            matched[s] += 1
        for s in (r.report or {}).get("missing_required_skills", []):
            missing[s] += 1
        if eff[aid] is not None:
            match_month[_month(r.created_at)].append(eff[aid])

    def rows(c: dict, names) -> list[dict]:
        return [
            {"id": k, "name": names(k), "applications": v["applications"], "approved": v["approved"], "rejected": v["rejected"],
             "shortlisted": v["shortlisted"], "selected": v["selected"]}
            for k, v in sorted(c.items(), key=lambda kv: -kv[1]["applications"])
        ]

    return {
        "generated_at": utcnow(),
        "filters": {"date_from": f.date_from, "date_to": f.date_to, "opening_id": f.opening_id, "category_id": f.category_id, "employee_id": f.employee_id},
        "totals": {
            "applications": total, "pending": sum(by_status[s] for s in PENDING), "approved": len(ever_approved),
            "rejected": by_status[AS.REJECTED], "withdrawn": by_status[AS.WITHDRAWN], "shortlisted": len(ever_shortlisted),
            "selected": len(ever_selected), "openings_in_scope": len(ids), "decided": decided,
        },
        "rates": {
            "approval_rate": _pct(sum(by_status[s] for s in PASSED_SCREEN), decided),
            "rejection_rate": _pct(by_status[AS.REJECTED], decided),
            "completion_rate": _pct(len(completed_apps), len(scheduled_apps)),
            "attendance_rate": _pct(attended, attended + missed),
            "shortlisting_rate": _pct(len(ever_shortlisted), len(evaluated_apps)),
            "selection_rate": _pct(len(ever_selected), len(ever_shortlisted)),
        },
        "denominators": {
            "decided": decided, "scheduled": len(scheduled_apps), "attended_or_missed": attended + missed,
            "evaluated": len(evaluated_apps), "shortlisted": len(ever_shortlisted),
        },
        "status_distribution": [{"status": s.value, "count": by_status[s]} for s in AS if by_status[s]],
        "funnel": funnel,
        "per_opening": rows(per_opening, lambda k: openings[k].title),
        "per_category": rows(per_cat, lambda k: cats.get(k, str(k))),
        "applications_by_month": [{"month": m, "count": n} for m, n in sorted(per_month.items())],
        "scores": {
            "evaluated_candidates": len(pcts), "average_percentage": _avg(pcts), "distribution": dist,
            "performance_trend": [{"month": m, "average": _avg(v), "count": len(v)} for m, v in sorted(perf_month.items())],
        },
        "match_scores": {
            "analysed": len(scores), "average": _avg(scores),
            "trend": [{"month": m, "average": _avg(v), "count": len(v)} for m, v in sorted(match_month.items())],
            "top_matched_skills": [{"skill": k, "count": v} for k, v in matched.most_common(10)],
            "top_missing_skills": [{"skill": k, "count": v} for k, v in missing.most_common(10)],
        },
        "stage_durations": durations,
        "notes": NOTES,
    }


def compare(db: Session, user: User, application_ids: list[int]) -> list[dict]:
    """Side-by-side view of 2-5 candidates. Needs analytics AND application-review permission (it shows names)."""
    require(db, user)
    access.require_perm(db, user, "review_applications")
    ids = list(dict.fromkeys(application_ids))
    if not 2 <= len(ids) <= 5:
        raise AppError(422, "invalid_selection", "Choose between 2 and 5 applications to compare.")
    out = []
    for aid in ids:
        app = db.get(JobApplication, aid)
        if app is None:
            raise AppError(404, "not_found", "Application not found.")
        access.require_opening_access(db, user, app.opening_id)  # 404 hides applications outside the viewer's scope
        cp = db.get(CandidateProfile, app.candidate_id)
        u = db.get(User, cp.user_id)
        rep = db.scalars(
            select(ResumeAnalysisReport).where(ResumeAnalysisReport.application_id == aid, ResumeAnalysisReport.status == AnalysisStatus.COMPLETED)
            .order_by(ResumeAnalysisReport.id.desc()).limit(1)
        ).first()
        ev = db.scalars(
            select(EvaluationResult).where(EvaluationResult.application_id == aid, EvaluationResult.status == EvaluationStatus.FINAL)
            .order_by(EvaluationResult.id.desc()).limit(1)
        ).first()
        sections = []
        if ev:
            for sec, got, mx in db.execute(
                select(EvaluationItem.section, func.sum(EvaluationItem.final_marks), func.sum(EvaluationItem.max_marks))
                .where(EvaluationItem.evaluation_id == ev.id).group_by(EvaluationItem.section)
            ).all():
                sections.append({"section": sec, "obtained": float(got or 0), "total": float(mx or 0)})
        r = rep.report if rep and rep.report else {}
        out.append({
            "application_id": aid, "candidate_name": u.full_name, "opening_title": app.opening.title, "status": app.status.value,
            "experience_years": float(cp.total_experience_years) if cp.total_experience_years is not None else None,
            "match_score": (rep.override_score if rep.override_score is not None else rep.ai_score) if rep else None,
            "match_is_mock": rep.is_mock if rep else None,
            "matched_required_skills": r.get("matched_required_skills", []), "missing_required_skills": r.get("missing_required_skills", []),
            "evaluation_percentage": ev.percentage if ev else None, "sections": sections,
        })
    return out


def export_rows(data: dict, report: str) -> tuple[list[str], list[list]]:
    if report == "monthly":
        return ["Month", "Applications"], [[r["month"], r["count"]] for r in data["applications_by_month"]]
    if report == "funnel":
        return ["Stage", "Applications"], [[r["stage"], r["count"]] for r in data["funnel"]]
    if report == "categories":
        return ["Category", "Applications", "Approved", "Rejected", "Shortlisted", "Selected"], [
            [r["name"], r["applications"], r["approved"], r["rejected"], r["shortlisted"], r["selected"]] for r in data["per_category"]]
    return ["Opening", "Applications", "Approved", "Rejected", "Shortlisted", "Selected"], [
        [r["name"], r["applications"], r["approved"], r["rejected"], r["shortlisted"], r["selected"]] for r in data["per_opening"]]

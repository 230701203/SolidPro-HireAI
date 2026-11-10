# Implementation checklist

Status legend: ✅ done and tested · 🟡 partial · ⬜ not started

## Phase 1 — Foundation, authentication, RBAC ✅

| Feature | Status | Verified by |
|---|---|---|
| Backend (FastAPI, SQLAlchemy 2, Alembic) + PostgreSQL | ✅ | 53 backend tests run against real Postgres; migration up/down/up + `alembic check` (no drift) |
| Frontend (React, TS, Tailwind, Router, Query, RHF/Zod) | ✅ | 9 component tests, typecheck, production build |
| Default admin via `python -m app.cli bootstrap` (random password if none set; never in source) | ✅ | tests + live run |
| Forced password change at first admin login (server-enforced) | ✅ | backend test + browser test |
| Applicant registration + email verification + login | ✅ | backend + browser |
| Employee registration: company-domain allowlist → verify email → `Pending Approval` | ✅ | backend + browser |
| Admin approve / reject (with reason) / assign permissions; admin + employee notified | ✅ | backend + browser |
| Company email alone never grants access; pending / rejected / suspended users blocked on every API call | ✅ | backend tests |
| Admin inherits all employee permissions | ✅ | `require_permission` test |
| Suspend / deactivate / reactivate (live sessions revoked immediately), unlock, admin-initiated password reset | ✅ | backend + browser |
| Forgot / reset / change password (single-use, hashed, expiring tokens; sessions revoked) | ✅ | backend tests |
| Argon2 hashing, httpOnly cookie sessions, account lockout, rate limiting, security headers | ✅ | backend tests |
| Role-based navigation and route guards | ✅ | component + browser tests |
| In-app notifications (read/unread, mark all) | ✅ | backend + browser |
| Audit log (filterable) | ✅ | backend tests |
| Email logs with delivery status and retry | ✅ | backend tests |
| Admin dashboard with real DB numbers; employee / applicant dashboards | 🟡 | Account metrics only; job / application / assessment metrics arrive with their modules |

### Known limitations (honest notes)
* **Email**: with `SMTP_HOST` empty, emails are only written to the server log and shown as *Logged (dev)*. Run Mailpit (`docker compose up`) or configure real SMTP to deliver mail. Delivery has been verified only up to the SMTP call, not against a live mail server.
* **Rate limiter** is in-memory (per process); use Redis when running several workers.
* **Consent** is recorded as a timestamp at registration; the actual privacy-notice text and retention policy must be supplied by SolidPro legal.

## Phase 2 — Recruitment management ⬜
Job categories (CAD, Digital Transform, Intern + dynamic), openings, assignments, candidate profiles, versioned resume upload, applications, tracking, employee review.

## Phase 3 — AI resume analysis ⬜
## Phase 4 — AI assessment generation + mandatory approval ⬜
## Phase 5 — Scheduling and online testing ⬜
## Phase 6 — Evaluation, results, interviews ⬜
## Phase 7 — Bulk upload, analytics, reports, deployment ⬜

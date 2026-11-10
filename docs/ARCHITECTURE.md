# SolidPro HireAI — Architecture

## 1. Stack (as implemented)

| Layer | Choice |
|---|---|
| Frontend | React 19 + TypeScript, Vite, Tailwind CSS 4, React Router, Axios, TanStack Query, React Hook Form + Zod, Recharts, Lucide |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.0 (sync), Alembic, Pydantic v2 |
| Database | PostgreSQL 14+ (psycopg 3) |
| Auth | JWT in an httpOnly, SameSite=Lax cookie (Bearer header also accepted), Argon2 password hashing, RBAC + permission codes |
| Email | SMTP (Mailpit in dev). With no SMTP configured in development, emails are stored in `email_logs` and printed to the server log with status `dev_logged` |
| Later phases | Redis + worker (bulk resume / AI / STT), LLM API, speech-to-text, S3/Azure Blob storage |

### Why sync SQLAlchemy
Simpler to reason about and test. FastAPI runs sync routes in a thread pool, which is more than sufficient for an internal HR tool. Long-running AI work will go to a background worker in Phase 3+, not into request handlers.

## 2. Request flow

```
Browser ──(cookie)──▶ FastAPI router ──▶ dependencies (auth → status → role/permission)
                                      └▶ service layer (business rules, audit, notifications, emails)
                                          └▶ SQLAlchemy models ──▶ PostgreSQL
```

* **Routes** are thin: parse input, call a service, commit, return a schema.
* **Services** hold business rules (registration, approval, token issuing).
* **Dependencies** enforce authentication, account status, `must_change_password`, roles and permissions on the server for every request.

## 3. Account model

Account **types** (`users.role`): `admin`, `employee`, `applicant`. These are separate from recruitment **categories** (CAD, Digital Transform, Intern — Phase 2).

Account **status** (`users.status`):

```
pending_email_verification ──verify──▶ applicant: active
                                   └▶ employee:  pending_approval ──approve──▶ active
                                                                  └─reject──▶ rejected
active ◀──▶ suspended / deactivated   (admin action)
```

Rules enforced in code:
* A SolidPro-domain address never grants privileges by itself — it only routes the user into the **approval queue**. Domains come from the `company_email_domains` table (admin-editable), not from the email provider.
* Only `active` accounts pass authentication on API calls. Pending, rejected, suspended and deactivated users are blocked server-side, even with a previously issued token.
* Admin inherits every Employee operation (`require_permission` passes for admins).
* Employees need an explicit permission code (e.g. `manage_job_openings`) granted by an admin.
* The seeded admin must change the initial password before any other API call succeeds.

## 4. ER diagram — Phase 1 (implemented)

```mermaid
erDiagram
    users ||--o| employee_profiles : has
    users ||--o| candidate_profiles : has
    users ||--o{ employee_approvals : "is decided in"
    users ||--o{ employee_permissions : granted
    permissions ||--o{ employee_permissions : in
    users ||--o{ email_verification_tokens : owns
    users ||--o{ password_reset_tokens : owns
    users ||--o{ notifications : receives
    users ||--o{ audit_logs : "acts in"
    users ||--o{ email_logs : "addressed to"
    users ||--o{ company_email_domains : "created by"

    users {
        int id PK
        string email UK
        string password_hash
        string full_name
        string mobile
        enum role "admin|employee|applicant"
        enum status
        bool must_change_password
        timestamptz email_verified_at
        timestamptz last_login_at
        int token_version
        int failed_login_attempts
        timestamptz locked_until
        timestamptz consent_accepted_at
    }
    employee_profiles { int id PK; int user_id FK_UK; string department; string designation }
    candidate_profiles { int id PK; int user_id FK_UK }
    employee_approvals { int id PK; int employee_id FK; int decided_by FK; enum decision; text reason; jsonb permissions_granted; timestamptz decided_at }
    permissions { int id PK; string code UK; string description; string category }
    employee_permissions { int user_id PK_FK; int permission_id PK_FK; int granted_by FK; timestamptz granted_at }
    email_verification_tokens { int id PK; int user_id FK; string token_hash UK; timestamptz expires_at; timestamptz used_at }
    password_reset_tokens { int id PK; int user_id FK; string token_hash UK; timestamptz expires_at; timestamptz used_at }
    company_email_domains { int id PK; string domain UK; bool is_active; int created_by FK }
    notifications { int id PK; int user_id FK; string type; string title; text message; string link; bool is_read }
    email_logs { int id PK; int user_id FK; string to_email; string subject; string template; enum status; int attempts; text error }
    audit_logs { int id PK; int actor_id FK; string action; string entity_type; string entity_id; jsonb details; string ip_address }
```

Raw verification / reset tokens are never stored — only their SHA-256 hash.

## 5. Planned schema for later phases

Added by Alembic migrations phase by phase (names follow the specification):

* **Phase 2** — `job_categories`, `job_openings`, `employee_assignments`, `candidate_resumes` (versioned), `candidate_education`, `candidate_skills`, `candidate_experience`, `job_applications` (unique per candidate + opening), `application_status_history`.
* **Phase 3** — `resume_analysis_reports` (JSONB report, model + prompt version recorded, reviewer overrides).
* **Phase 4** — `question_banks`, `questions`, `question_options`, `assessments`, `assessment_sections`, `assessment_versions` (JSONB immutable snapshot), `assessment_questions`, `assessment_approvals`.
* **Phase 5** — `assessment_invitations` (hashed single-use tokens), `test_schedules`, `reschedule_requests`, `test_attempts`, `candidate_answers`, `audio_recordings`.
* **Phase 6** — `evaluation_results`, `evaluation_reviews` (score-override history), `interviews`, `interview_feedback`.
* **Phase 7** — bulk upload jobs, analytics views, configurable email templates.

Key invariants to carry forward: candidate profile ≠ application; one application per (candidate, opening); resume versions preserved; approved assessments are immutable snapshots; no schedule without an approved version.

## 6. API conventions

* Base path `/api`; interactive docs at `/api/docs`.
* Errors: `{"error": {"code": "...", "message": "...", "fields": {...}?}}`.
* Lists: `{"items": [...], "total": n, "page": 1, "page_size": 20, "pages": k}`.
* Sensitive endpoints (login, register, forgot/reset password, resend verification) are rate-limited (in-memory per process; swap for Redis when running several workers).

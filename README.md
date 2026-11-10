# SolidPro HireAI

AI-assisted recruitment and assessment platform for SolidPro Engineering Support Pvt Ltd.
**Current status: Phase 1 of 7** (authentication, roles, employee approval). See [CHECKLIST.md](CHECKLIST.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (includes the ER diagram).

| Layer | Stack |
|---|---|
| Frontend | React + TypeScript, Vite, Tailwind CSS, React Router, TanStack Query, React Hook Form + Zod, Recharts |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 |
| Database | PostgreSQL 14+ |

## Prerequisites
Python 3.12+, Node 20+, and PostgreSQL (easiest via Docker Desktop: `docker compose up -d` starts Postgres and Mailpit).

## Setup

### 1. Database and mail (Docker)
```bash
docker compose up -d        # Postgres :5432 (hireai/hireai) and Mailpit inbox http://localhost:8025
```
Without Docker, create a database and user yourself and put the URL in `backend/.env`.

### 2. Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env
```
Edit `backend/.env`:
* `SECRET_KEY`: generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`
* `COMPANY_EMAIL_DOMAINS`: your real company domain(s), e.g. `solidpro.com`
* `ADMIN_EMAIL`: the first administrator's address

```bash
alembic upgrade head              # create the schema
python -m app.cli bootstrap       # permissions, company domains, first admin
uvicorn app.main:app --reload     # API on http://localhost:8000  (docs: /api/docs)
```
`bootstrap` prints a **generated one-time admin password** (or uses `ADMIN_INITIAL_PASSWORD` if you set it). The admin must change it at first sign-in. It is safe to re-run; it never overwrites an existing admin.

Optional dev data: `python -m app.cli seed-dev` creates sample accounts with random passwords printed once.

### 3. Frontend
```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173 (proxies /api to :8000)
```

## Try the main flow
1. Sign in as the admin → change the password.
2. Open `/register`, register with an address on your company domain, open the verification link (see Mailpit at :8025, or **Admin → Email Delivery** / the API log when SMTP is not configured).
3. Admin → **Employee Management** → Approve, tick the permissions to grant.
4. The employee can now sign in. Registering with any other address creates an applicant.

## Tests
```bash
cd backend && pytest              # needs TEST_DATABASE_URL (default: postgresql+psycopg://postgres@localhost:5433/hireai_test)
cd frontend && npm test && npm run build
```
Backend tests run the real Alembic migrations on a real PostgreSQL database and **truncate it**, so never point `TEST_DATABASE_URL` at data you care about. With the Docker setup above use:
`postgresql+psycopg://hireai:hireai@localhost:5432/hireai_test`

## Security summary
Argon2 password hashes · httpOnly SameSite cookie sessions (tokens never readable by JS) · hashed single-use verification/reset tokens · account lockout + rate limiting on sensitive endpoints · server-side role/permission checks on every request · sessions revoked on password change/suspension · audit log of security events · no secrets in source (`.env` is git-ignored).
In production set `ENVIRONMENT=production`, `COOKIE_SECURE=true`, a strong `SECRET_KEY` (the app refuses to start otherwise), and serve over HTTPS.

## Push to GitHub
```bash
git add . && git commit -m "Phase 1: auth, RBAC, employee approval"
git remote add origin https://github.com/<you>/solidpro-hireai.git
git push -u origin main
```
Never commit `backend/.env`. CI (`.github/workflows/ci.yml`) runs lint, tests and the build on every push.

## Roadmap
Phases 2–7 (recruitment management, AI resume analysis, assessment generation with mandatory human approval, online testing with Repeat-the-Sentence, evaluation and interviews, bulk upload and analytics) are built one at a time, each with its own migration and tests.

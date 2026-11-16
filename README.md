# SolidPro HireAI

AI-assisted recruitment and assessment platform for SolidPro Engineering Support Pvt Ltd.
**Current status: Phase 7 of 7 complete** (authentication and roles, employee approval, recruitment management, advisory AI resume analysis, AI-drafted assessments with mandatory human approval, test scheduling and the online test with Repeat-the-Sentence recording, evaluation with human review and release, shortlisting and interviews, bulk resume screening, recruitment analytics and exports, and deployment files that still need a staging run). See [CHECKLIST.md](CHECKLIST.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (includes the ER diagram).

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

## AI configuration
Resume analysis runs in **mock mode by default** (keyword matching, labelled MOCK everywhere). To use real AI set in `backend/.env`:
```
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=<your key>      # never commit this
AI_MODEL=claude-sonnet-5-5
```
The same setting drives assessment generation. Online tests run in the applicant's browser (speech synthesis and MediaRecorder), so use a current Chrome, Edge or Safari; the sweeper settings are in `.env.example`. If `anthropic` is selected without a key, analysis returns an error; it never falls back to mock silently. AI output is advisory: it never approves or rejects anyone and applicants never see it.

## Security summary
Argon2 password hashes · httpOnly SameSite cookie sessions (tokens never readable by JS) · hashed single-use verification/reset tokens · account lockout + rate limiting on sensitive endpoints · server-side role/permission checks on every request · sessions revoked on password change/suspension · audit log of security events · no secrets in source (`.env` is git-ignored).
In production set `ENVIRONMENT=production`, `COOKIE_SECURE=true`, a strong `SECRET_KEY` (the app refuses to start otherwise), and serve over HTTPS.

## Push to GitHub
```bash
git add . && git commit -m "Phase 7: bulk screening, analytics, exports, deployment"
git remote add origin https://github.com/<you>/solidpro-hireai.git
git push -u origin main
```
Never commit `backend/.env`. CI (`.github/workflows/ci.yml`) runs lint, tests and the build on every push.

## Roadmap
All seven phases are built. What remains is listed honestly in [CHECKLIST.md](CHECKLIST.md): notably a staging run of the deployment files, live testing of the real AI and speech providers, and expert review of the starter aptitude questions.

## Phase 7 quick notes

* **Bulk screening:** sign in as an admin (or an employee with *Bulk resume upload* on an assigned opening) and open **Bulk Screening**. It ranks resumes against an opening; it never creates accounts or changes applicants.
* **Analytics:** **Analytics** (permission *View analytics*). Compare 2 to 5 candidates by ticking rows on **Results**.
* **Production:** see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) (`docker-compose.prod.yml`, `.env.production.example`). These files have not been run against a live Docker daemon.

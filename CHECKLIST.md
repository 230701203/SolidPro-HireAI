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

## Phase 2 — Recruitment management ✅

| Feature | Status | Verified by |
|---|---|---|
| Job categories (CAD, Digital Transform, Intern seeded; admin can add / edit / deactivate; internship flag) | ✅ | backend tests + browser |
| Job openings: draft → published → closed, edit, duplicate, delete (blocked when applications exist), deadline, skills, internship fields | ✅ | backend tests + browser |
| Publish validation (needs required skills, non-past deadline, active category) | ✅ | backend tests |
| Assign employees to openings; assignee notified; creator never locked out | ✅ | backend tests |
| Employees only see openings they are assigned to, and only those openings' applicants / resumes (404 hides existence) | ✅ | backend tests |
| Applicant profile (personal, education, experience / internships / projects, skills by kind) with completion % | ✅ | backend + browser |
| Resume upload: PDF / DOCX, extension + magic-byte check, size limit, corrupt / encrypted / image-only rejected, immutable versions | ✅ | 82 backend tests + browser |
| Private resume storage with opaque names, served only by an authorised endpoint, audited | ✅ | backend tests |
| Applying (one application per candidate + opening, resume version pinned, needs mobile + education + resume) | ✅ | backend + browser |
| Review workflow: start review, request info (applicant replies), approve, reject with reason; decisions are final | ✅ | backend + browser |
| Internal reviewer comments never visible to the applicant; reviewer identity shown as "Recruitment team" | ✅ | backend + browser leak check |
| Applicant tracking page with timeline; withdraw | ✅ | browser |
| Dashboards with real opening / application numbers (admin, employee, applicant) | ✅ | backend tests |
| Applicants cannot reach staff routes or other people's data | ✅ | backend tests + browser |

### Phase 2 known limitations (honest notes)
* **Scanned / image-only PDFs are rejected** (no OCR yet). Applicants are told to upload a text-based PDF or DOCX.
* **Resume files live on local disk** (`UPLOAD_DIR`). Fine for one server; use object storage for multi-server deployments.
* **No antivirus scan** of uploads; files are type-checked, size-limited and served with `nosniff` and a restrictive CSP.
* **No AI yet**: recruiters review manually. AI resume analysis is Phase 3 and will stay advisory only.
* Frontend has component tests from Phase 1 only; the Phase 2 pages are verified by the real-browser end-to-end run, not by unit tests.

## Phase 3 — AI resume analysis ✅

| Feature | Status | Verified by |
|---|---|---|
| Provider abstraction: `mock` (default) and `anthropic`; chosen by `AI_PROVIDER`, never a silent fallback | ✅ | backend tests |
| Mock mode clearly labelled (API field `is_mock`, `[MOCK]` summary, warning banner in the UI) | ✅ | backend + component + browser |
| Structured report: score 0-100, confidence, matched / missing skills, experience and education notes, strengths, gaps, things to verify, interview topics | ✅ | schema tests |
| Output validated and clamped; unusable provider output becomes a safe error, never a half-report | ✅ | backend tests |
| Every run stored with provider, model, prompt version and resume version; failures stored too; history kept | ✅ | backend + browser |
| Reviewer override sits beside the AI score (AI score never rewritten), needs a written reason, can be removed, audited | ✅ | backend + browser |
| Advisory only: a run never changes application status (high score does not approve, low score does not reject) | ✅ | backend tests |
| Staff only: applicants get 404 on every analysis endpoint and no score appears in their responses | ✅ | backend + browser |
| Permission `analyze_resumes` to run / override; `review_applications` can read; employees limited to assigned openings | ✅ | backend tests |
| Name, email, mobile, address, date of birth, links and institution names are not sent to the AI (only job data, years of experience, degree / department / year, skills and resume text) | ✅ | backend test |
| Prompt-injection hardening: resume is delimited as untrusted data, system prompt forbids following it, suspicious text is flagged for the reviewer and audited | ✅ | backend tests |
| Rate limit on runs (30 per hour per IP) and resume text cap (`AI_MAX_RESUME_CHARS`) | ✅ | config + code |
| Audit log: `resume_analysis.run`, `.overridden`, `.override_cleared` | ✅ | backend tests |

### Phase 3 known limitations (honest notes)
* **The Anthropic provider has not been run against the live API** (no key was available). It is tested with a mocked HTTP transport for success, bad key, rate limit, server error, malformed and invalid output. Run one real analysis with your key and review the result before relying on it.
* **Mock mode is only keyword matching**; it cannot judge depth, recency or context of skills.
* **The resume text itself still contains the applicant's name and contact details** (it is free text). Only the structured fields are stripped. Do not use AI analysis for decisions without human review; the system never lets it decide.
* **Prompt-injection detection is a heuristic** (a pattern list plus prompt design). It reduces risk but cannot guarantee a model will ignore every hidden instruction, which is why the score is advisory and the reviewer sees the resume.
* Scores are not shown in the applications list yet (sorting / filtering by score arrives with analytics in Phase 7).
* Reviewer corrections to *extracted data* (skills, years) are not built yet; the override applies to the score.

## Phase 4 — AI assessment generation + mandatory approval ✅

| Feature | Status | Verified by |
|---|---|---|
| Assessment draft created only for an application that was approved for assessment; one per application | ✅ | backend tests |
| Exactly three sections: MCQ, Aptitude, Repeat the Sentence (no coding section) | ✅ | backend + browser |
| AI writes MCQ and Repeat-the-Sentence items; aptitude comes only from the reusable bank, never invented by AI (shortfalls are reported, not filled) | ✅ | backend tests |
| MCQs filtered to the opening's skills and the candidate's listed skills; unrelated-skill questions are dropped and reported | ✅ | backend tests |
| Question bank: starter set (18 verified questions, 6 topics), banks and questions maintained by staff with `manage_question_bank` | ✅ | backend + browser |
| Per-question review: approve, reject (with reason), edit, regenerate, delete, add by hand, add from bank; any edit needs re-approval | ✅ | backend + browser |
| Placeholders (mock mode) can never be approved; bulk approve skips them | ✅ | backend + component tests |
| Whole-assessment approval blocked until every section has questions and none are pending | ✅ | backend + browser |
| Approval creates an immutable, versioned snapshot with SHA-256 fingerprint, approver, time, question ids, note and a diff of what changed | ✅ | backend + browser |
| Immutability enforced by a database trigger (UPDATE / DELETE rejected); only the publish columns may change | ✅ | backend test (raw SQL) |
| Editing an approved assessment reopens it as a draft; the approved version stays intact and a new approval makes the next version | ✅ | backend + browser |
| Bank edits never change an assessment or an approved version (questions are copied) | ✅ | backend test |
| Publish only the latest approved version (integrity re-checked) | ✅ | backend + browser |
| Applicants get 404 on every assessment and bank endpoint and never see questions or answer keys | ✅ | backend test |
| Permissions: `generate_assessments`, `approve_assessments`, `manage_question_bank`; employees limited to assigned openings | ✅ | backend tests |
| Audit log for generation, every review action, approval and publish | ✅ | backend test |
| Repeat-the-Sentence audio preview for reviewers (browser speech synthesis) | ✅ | browser only (no audio check) |

### Phase 4 known limitations (honest notes)
* **Real AI question generation has not been run against the live API** (no key). The Anthropic provider is tested with a mocked transport (valid items kept, malformed dropped, resume cannot close the prompt delimiter, sentence prompt never receives the resume). Generate a draft with your key and read every question before approving.
* **Mock mode** uses a small curated pool (Python, FastAPI, SQL, Git, Docker, JavaScript, REST) and labelled placeholders for other skills. It is for development only.
* **The starter aptitude bank must be reviewed by a person** before real use. Answer keys are checked by tests for internal consistency, not by a subject expert.
* **No four-eyes rule**: the person who generates may also approve. Say so if you need separation of duties.
* **The audio preview uses the reviewer's browser voice** (applicants hear the same kind of voice, see Phase 5 limitations).
* Assessment settings (counts, marks) are chosen at generation time; the screen lets you edit questions but not yet the repeat-sentence recording limits.

## Phase 5 — Scheduling and online testing ✅

| Feature | Status | Tested by |
|---|---|---|
| Schedule a test for an **approved** application from a **published** version (pinned; later edits never change it) | ✅ | backend tests, e2e |
| One active schedule per application; window / duration / expiry validation (timezone required) | ✅ | backend tests |
| Invitation by email + in-app notification; link token stored hashed; shown once; resend rotates it | ✅ | backend tests |
| Link only works for the invited, logged-in applicant (others get 404); expired link is 410 | ✅ | backend tests |
| Accept (idempotent), request reschedule, staff approve / decline (reason required) / suggest alternative, applicant accept or decline | ✅ | backend + frontend tests |
| Staff edit (re-invites), cancel with reason, resend; blocked once started | ✅ | backend tests |
| Online test: server-owned deadline, per-attempt shuffle of questions and options, answer keys never sent | ✅ | backend + frontend tests, e2e |
| Autosave (idempotent, sequence-ordered), offline banner with retry, mark for review, question navigator, submit confirmation, auto-submit at zero | ✅ | backend + frontend tests, e2e |
| One browser session owns an attempt; reopening elsewhere takes over and the old window is refused | ✅ | backend + frontend tests |
| Repeat the Sentence: server-counted plays, recording with mic-permission handling, countdown, upload retry, magic-byte audio check, size / length / attempt limits | ✅ | backend tests, e2e (fake microphone) |
| Private audio storage; staff playback is scoped to the opening, permission-checked and audited | ✅ | backend tests |
| Browser events (tab hidden, copy, paste, offline...) recorded for context only; whitelist, capped, never change status | ✅ | backend tests |
| Sweeper: auto-submits overdue attempts and expires missed windows (background task + lazy checks) | ✅ | backend tests |
| Staff pages (schedules list, detail with activity, reschedule handling, recording playback); applicant pages (My Tests, invitation, runner) | ✅ | frontend tests, e2e |

### Phase 5 known limitations (honest notes)
* **The sentence is spoken by the applicant's browser voice.** The server counts plays and only reveals the sentence text through the play endpoint, but a technical user could read it from that response. Server-generated or pre-recorded audio is not built. Voices and quality vary by browser and device.
* **Recording support depends on the browser** (MediaRecorder; Chrome, Edge, Firefox, recent Safari). Tested in headless Chromium with a fake microphone only; not on real phones, Safari or with real speech.
* **Speech-to-text and scoring were not part of Phase 5** (added in Phase 6, see below). Nothing in Phase 5 decides anything about an applicant.
* **Deadline = start time + duration**, even if that runs past the window end (the window controls when a test may be *started*). A short grace period (default 20 s) allows the final save.
* **Monitoring is deliberately light**: tab / copy / paste / connectivity events are logged only. There is no camera, screen capture, fullscreen lock or copy-paste blocking, and none of it triggers rejection.
* **Rate limiting and the sweeper run in the API process.** With several instances set `SWEEPER_ENABLED=false` on all but one (or run `attempt_service.sweep` from cron); rate limits are per process.
* **Unregistered candidates are not supported.** The specification's "direct link for a candidate uploaded by an employee" flow is not built: the applicant needs an account and an approved application.
* **No calendar (.ics) invite and no reminder emails** before the window; resend is manual.
* Staff can edit/cancel only before the attempt starts. There is no "grant a retake" or "extend time" action yet.
* Staff review of answers arrives with Phase 6 (see below).

## Phase 6 — Evaluation, results, interviews ✅

| Feature | Status | Tested by |
|---|---|---|
| Automatic objective scoring from the pinned snapshot keys (MCQ, aptitude); correct / incorrect / unanswered, no negative marking, time taken | ✅ | backend tests |
| Speech-to-text provider layer (mock + OpenAI-compatible); mock never invents a transcript | ✅ | backend tests (mocked HTTP) |
| Repeat the Sentence comparison: word accuracy, missing / substituted / extra words, order, near-matches treated as possible recognition errors (half credit), extra words not penalised | ✅ | backend tests |
| Uncertain speech (low confidence, empty, failed) is flagged, left unscored until a person confirms or overrides, and blocks approval | ✅ | backend + frontend tests, e2e |
| Reviewer: view every response and recording, override a score with reason, comments, re-run speech, approve (final) / reopen | ✅ | backend + frontend tests, e2e |
| Override history: reviewer, time, original, revised, reason | ✅ | backend tests |
| Release to applicant (scores + optional feedback only) and withdraw release; unreleased results look non-existent to applicants (404) | ✅ | backend + frontend tests, e2e |
| Human decisions: shortlist (needs a final evaluation) → select, or reject with a reason; applicant notified, timeline kept | ✅ | backend tests |
| Interviews: schedule (type, mode, link / location, instructions), reschedule, cancel, complete; internal feedback with recommendation; applicant sees only time, mode, link and instructions | ✅ | backend + frontend tests, e2e |
| Results and interview lists, applicant "My results" and "My interviews", dashboard counts for shortlisted | ✅ | frontend tests, e2e |
| Backfill of evaluations for tests submitted before this phase | ✅ | backend tests |

### Phase 6 known limitations (honest notes)
* **The real speech provider has not been run live.** The OpenAI-compatible provider is tested with a mocked HTTP transport only. With the default mock provider every real recording is flagged and a person must score it. Recognisers can silently "correct" a wrong or missing word, hiding omissions, so transcripts are advisory and reviewers can always play the audio.
* **Speech scoring is a simple, explainable word alignment**, not a pronunciation or fluency model. No clarity score is produced (the specification allows it only where reliably measurable). It is not validated on non-native or accented speech: reviewers should listen, and a speech score must never be the sole basis for a decision.
* **No AI-written evaluation comments.** The performance summary is generated by fixed rules from the scores and is labelled as such.
* **Decisions use new application statuses** (`shortlisted`, `selected`). There is no "on hold" state and no undo for a shortlist (reject, or ask an admin to correct it in the database).
* Interview feedback is free text: no structured scorecards, no panel with several feedback forms per interview, no calendar (.ics) invite or reminder emails, and no video-conference integration (a link is stored as given, https only).
* A speech recognition job runs in the API process after submission (and is retried by the sweeper); there is no separate worker queue.
* Reviewing is not four-eyes: the person who overrides a score can also approve and release it.
* A reviewer must manage dates and times in their device timezone; the applicant sees them in theirs.
* Rejecting after assessment shows the reviewer's reason to the applicant, like earlier rejections.

## Phase 7 — Bulk upload, analytics, reports, deployment ✅

| Feature | Status | Verified by |
|---|---|---|
| Bulk resume screening: up to 50 PDF/DOCX per batch against one opening; type, size and magic-byte checks; bad files are rejected with a reason and the rest are kept | ✅ | backend tests |
| Background processing with per-file commits, automatic retries (max 3), manual retry of failed files, and recovery of files stuck after a crash by the sweeper | ✅ | backend tests + browser |
| Heuristic extraction of name, email, phone, skills, experience years and education, with warnings for anything not found; labelled as guesses in the UI | ✅ | backend + component tests |
| Advisory match score per resume through the same AI layer (MOCK clearly labelled; AI never sees name or contact details; prompt-injection text flagged) | ✅ | backend tests |
| Duplicates: same file in batch, same email in batch, and registered applicant with the same email (linked, never merged) | ✅ | backend + browser |
| Screening only: no accounts created, no applicant profile changed, nobody notified; triage labels (interesting / not suitable) change nothing about any application | ✅ | backend test |
| Sort, filter (status, triage, duplicates, minimum score), search, pagination; live progress bar | ✅ | backend + component + browser |
| Access: `bulk_upload_resumes` permission plus assignment to the opening (404 hides others); resume download is authorised, `no-store` and audited; whole batch can be deleted with its files | ✅ | backend tests |
| Recruitment analytics: totals, pending, approval/rejection rates, funnel, per opening/category/month, attendance, completion, score distribution, performance and match-score trends, skill gaps, stage durations | ✅ | backend + component tests |
| Every rate states its denominator and shows "n/a" instead of inventing a number; definitions are shown on the page | ✅ | backend + component tests |
| Analytics limited to the viewer's assigned openings; filters (date, opening, category, employee) can never widen scope; employee filter is admin-only | ✅ | backend tests |
| Candidate comparison (2 to 5) needs `view_analytics` and `review_applications`; out-of-scope applications return 404 | ✅ | backend + component tests |
| CSV and XLSX export (bulk batches and analytics) with spreadsheet-formula neutralisation and audit entries | ✅ | backend tests |
| In-app notification to the uploader when a bulk batch finishes (once per completion, including after a retry; no email) | ✅ | backend test |
| In-app "Results awaiting review" reminder: one digest per reviewer (admins for everything, employees with `review_results` for their assigned openings) when a draft evaluation has waited over 24 h, at most once per 24 h, linking to Results filtered to "In review"; no applicant details in the text | ✅ | backend tests |
| Printable analytics page (browser "Save as PDF") | 🟡 | see limitations |
| Migration 0007 with query indexes for analytics and bulk tables; `alembic check` clean | ✅ | up/down/up + check |
| Route security sweep: every API route is requested without a login and must not answer 200 (except documented public routes) | ✅ | backend test |
| Deployment: backend and frontend Dockerfiles, `docker-compose.prod.yml`, nginx with security headers, `.env.production.example`, `docs/DEPLOYMENT.md`, CI docker build and `alembic check` | 🟡 | syntax only, see limitations |

### Phase 7 limitations and deviations (please read)
* **Deployment files were not run.** The environment had a Docker client but no daemon, so the images were never built and the stack was never started. YAML and the CI workflow parse; nginx syntax was not checked by nginx. Do a staging run first.
* **No server-side PDF.** Reports are CSV/XLSX plus a print stylesheet-based "Save as PDF" from the browser. There are no scheduled or emailed reports.
* **Extraction is regex heuristics.** Names, years and education can be wrong or missing (scanned/image resumes yield almost nothing; there is no OCR). Skills come from the opening's skills plus a built-in list.
* **Bulk screening does not onboard anyone.** It creates no accounts and sends no "please register" emails. A registered applicant with a matching email is only flagged; matching is by email, so a resume with no email cannot be de-duplicated.
* **Match scores are only as good as the provider.** With the default mock provider they are keyword counts; the real Anthropic provider has still never been run live.
* A batch is uploaded in one request and processed in the API process (no separate worker queue). Large batches slow other background jobs a little.
* Analytics are computed on demand from live tables, with indexes but without caching or materialised views. Timing was checked with test-sized data only, not with thousands of applications.
* Stage durations use status history; applications created before history existed (none in a fresh install) would be skipped.
* Rate limits are in memory per process; the sweeper is single-instance (see DEPLOYMENT.md).
* No load test, penetration test or dependency audit was performed. The route sweep checks authentication, not every authorisation rule (those are covered feature by feature).
* Notification polish is limited to the bulk-finished notification; no other new notification types, digests or preferences were added.
* **Test window guards:** copy, cut, paste, drag and the right-click menu are blocked in the test runner, and a warning shows when the applicant returns after leaving the tab. This is a deterrent, not enforcement: a browser cannot stop tab switching, screenshots, a second device or a second window side by side. Leaving the tab is only recorded for reviewers (it never submits, fails or rejects anyone, by design). Component-tested, not yet checked in a real browser.
* **Stricter sign-up input rules (live feedback):** names are 2 to 60 letters (spaces and . ' - allowed); emails are at most 254 characters, with a sane local part, a real-looking domain and extension, and a letter before @; new passwords are 10 to 64 characters with lowercase, uppercase, a digit and a symbol, no spaces, English characters only, no common words and not containing your email name. Register, reset and change-password show a live checklist, strength meter, character counters and match indicator; sign-in checks the email format live but never shows password rules and never rejects an existing password for failing them (max 128 characters). Rules live in `backend/app/core/security.py` and `frontend/src/utils/validation.ts` and must be changed together. Existing users keep their current passwords; the stricter rules apply when they next set one. `ADMIN_INITIAL_PASSWORD` is checked with the same rules, so an old value without a symbol will now be refused at startup. "Meaningful" email means well-formed: there is no disposable-domain list and no check that the mailbox exists.
* Notification polish is limited to the bulk-finished notification and the review reminder (in-app only, no email; "waiting" means a draft evaluation, so approved-but-unreleased results are not reminded); no other new notification types, digests or preferences were added.
* **Larger starter question set:** the starter aptitude bank now has 65 questions (numerical 13, logical 10, analytical 9, verbal 11, data interpretation 10, pattern 12), the mock technical pool has 32 questions, and there are 24 Repeat-the-Sentence sentences. Arithmetic answers are re-derived by a test, but the questions are still hand-written and **not expert-reviewed**, and the mock technical pool only covers Python, SQL, Git, Docker, JavaScript, React, REST, FastAPI and AutoCAD (other skills get placeholders that cannot be approved). Existing databases receive the new aptitude questions the next time `python -m app.cli bootstrap` runs (it adds only questions that are missing and never changes edited or deactivated ones). Real, job-specific questions need the Anthropic provider or a reviewer.
* No data-retention or automatic deletion policy exists for resumes, recordings or bulk batches beyond manual deletion of a batch.


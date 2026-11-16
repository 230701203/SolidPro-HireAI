# Deployment guide

> **Status: written but not run end to end.** The Dockerfiles, `docker-compose.prod.yml` and `nginx.conf` were
> validated for syntax only (the build environment had a Docker client but no running daemon). The application itself
> (migrations, bootstrap, API, SPA) was tested directly. Do a full staging run before going live.

## What you deploy

| Piece | Image / process | Notes |
|---|---|---|
| `postgres` | `postgres:16-alpine` | Data in the `pgdata` volume. Not published to the host. |
| `backend` | `backend/Dockerfile` (Python 3.13) | Runs `alembic upgrade head`, `python -m app.cli bootstrap`, then Uvicorn with **one** worker. Not published to the host. |
| `web` | `frontend/Dockerfile` (nginx) | Serves the SPA and proxies `/api` to the backend. The only published port (`WEB_PORT`, default 8080). |

## First deployment

1. `cp .env.production.example .env.production` and fill in **every** value. Generate `SECRET_KEY` and the database password; never reuse the placeholders and never commit the file.
2. `docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build`
3. Read the backend log once for the generated admin password if you left `ADMIN_INITIAL_PASSWORD` empty (`docker compose -f docker-compose.prod.yml logs backend | grep -i password`). The admin must change it at first login. Then clear the log line from any log shipper you use.
4. Put HTTPS in front of `web` (below), then open the site, sign in as the admin and check **System Settings** and **Email Delivery**.

## HTTPS (required)

The session cookie is `Secure` in production, so the site only works over HTTPS. Terminate TLS in front of the `web` container with a cloud load balancer, Caddy, or nginx + certbot, and forward `X-Forwarded-For` / `X-Forwarded-Proto`. Set `FRONTEND_URL` and `CORS_ORIGINS` to the public `https://` origin. Enable HSTS at the TLS layer once you are sure HTTPS works.

## Things that must be true in production

* `ENVIRONMENT=production` and `COOKIE_SECURE=true` (the compose file sets both).
* `SECRET_KEY` is long, random and secret. Rotating it signs everyone out.
* The backend port is **not** published. `--forwarded-allow-ips='*'` in the Dockerfile is only safe because of this; if you expose port 8000 directly, change it to your proxy's address, or the rate limiter's client IP can be spoofed.
* Rate limits are in memory (per process). With one worker that is fine. For several instances use a shared store (Redis) instead.
* `AI_PROVIDER=mock` / `STT_PROVIDER=mock` are clearly labelled in the UI. Switch to real providers only after setting keys and reviewing cost and privacy (resume text is sent to the provider; names and contact details are not).

## Single instance and the background sweeper

A task inside the API process auto-submits overdue tests, expires missed schedules, processes speech recognition and picks up stuck bulk-screening files. **Run one backend replica.** If you must scale out, set `SWEEPER_ENABLED=false` on all but one replica (and move rate limiting to a shared store).

## File storage

Resumes, audio recordings and bulk-screening files are stored on the `uploads` volume under random names and are only served through authorised API calls. Back this volume up with the database. For cloud storage, replace `app/services/storage_service.py` (three functions) with an S3/Azure implementation.

## Backups and restore

* Database: `docker compose exec postgres pg_dump -U $POSTGRES_USER $POSTGRES_DB | gzip > hireai-$(date +%F).sql.gz` on a schedule, copied off the server.
* Uploads: snapshot the `uploads` volume at the same time (a database row can point to a file, so back both up together).
* **Test a restore** into a scratch environment before you rely on it.

## Upgrades and migrations

Migrations run automatically on container start (`alembic upgrade head`). Take a database backup first. Run migrations and downgrades as separate steps and check `alembic current` after each; do not chain them. Downgrades can delete data (for example, 0007 drops the bulk-screening tables).

## Upload limits

nginx allows 300 MB per request (`client_max_body_size`), enough for a 50-file batch at 5 MB each. If you raise `MAX_UPLOAD_MB` or `BULK_MAX_FILES`, raise the nginx limit to at least their product.

## Health check and monitoring

`GET /api/health` returns `{"status":"ok"}` (the container health check uses it). It does not test the database; add an external uptime check and log shipping. Application errors are logged to stdout.

## Security checklist before go-live

- [ ] HTTPS enforced, HSTS set at the TLS layer
- [ ] Real SMTP configured and a test email delivered
- [ ] `SECRET_KEY`, database password and admin password are unique and stored in a secret manager
- [ ] Only port 443 (and 80 redirecting) is reachable from the internet; Postgres and the API are not
- [ ] Backups run and a restore was tested
- [ ] Audit Logs page reviewed after a test session
- [ ] A person has read the starter aptitude questions (they are not expert-reviewed)
- [ ] Privacy notice and retention policy agreed for resumes and recordings (no automatic deletion exists yet)

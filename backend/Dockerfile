# Production image for the API. Build context: ./backend
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/backend

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# Private upload storage lives on a volume, owned by an unprivileged user.
RUN useradd --system --uid 10001 hireai && mkdir -p /data/storage && chown -R hireai /data /srv/backend
USER hireai
ENV UPLOAD_DIR=/data/storage ENVIRONMENT=production

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"

# Apply migrations, create the admin / defaults if missing (idempotent), then serve.
# ONE worker on purpose: the background sweeper runs inside the process (see docs/DEPLOYMENT.md).
# --forwarded-allow-ips='*' is safe only because port 8000 is never published; only the nginx container can reach it.
CMD ["sh", "-c", "alembic upgrade head && python -m app.cli bootstrap && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]

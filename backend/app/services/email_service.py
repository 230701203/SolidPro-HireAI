"""Email queueing and delivery.

`queue_email` writes an EmailLog row (inside the caller's transaction) and schedules delivery
as a background task that runs after the response is sent (and therefore after the commit).

Delivery modes:
* SMTP_HOST set       -> send through SMTP, status `sent` or `failed` (retryable).
* SMTP_HOST empty, development/test -> nothing is sent; the message is written to the server log
  and stored with status `dev_logged`. This is NOT reported as delivered.
* SMTP_HOST empty, production -> status `failed` with an explanatory error.
"""

import html
import logging
import smtplib
from email.message import EmailMessage

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import SessionLocal
from app.models import EmailLog, EmailStatus
from app.models.base import utcnow

logger = logging.getLogger("hireai.email")


def _wrap_html(title: str, paragraphs: list[str], button: tuple[str, str] | None = None) -> str:
    s = get_settings()
    body = "".join(f"<p style='margin:0 0 14px'>{html.escape(p)}</p>" for p in paragraphs)
    btn = ""
    if button:
        label, url = button
        btn = (
            f"<p style='margin:22px 0'><a href='{html.escape(url, quote=True)}' "
            "style='background:#1d4ed8;color:#fff;padding:11px 20px;border-radius:6px;"
            f"text-decoration:none;font-weight:600'>{html.escape(label)}</a></p>"
            f"<p style='font-size:12px;color:#64748b'>If the button does not work, copy this link:<br>"
            f"{html.escape(url)}</p>"
        )
    return (
        "<div style=\"font-family:Segoe UI,Arial,sans-serif;max-width:560px;margin:auto;color:#0f172a\">"
        f"<h2 style='color:#1d4ed8'>{html.escape(s.app_name)}</h2>"
        f"<h3 style='margin-top:0'>{html.escape(title)}</h3>{body}{btn}"
        f"<hr style='border:none;border-top:1px solid #e2e8f0;margin:24px 0'>"
        f"<p style='font-size:12px;color:#64748b'>Need help? Contact {html.escape(s.support_email)}.</p></div>"
    )


def _text(title: str, paragraphs: list[str], button: tuple[str, str] | None = None) -> str:
    lines = [title, "", *paragraphs]
    if button:
        lines += ["", f"{button[0]}: {button[1]}"]
    lines += ["", f"Need help? Contact {get_settings().support_email}."]
    return "\n".join(lines)


def build_message(title: str, paragraphs: list[str], button: tuple[str, str] | None = None) -> tuple[str, str]:
    """Return (text, html)."""
    return _text(title, paragraphs, button), _wrap_html(title, paragraphs, button)


def queue_email(
    db: Session,
    background: BackgroundTasks | None,
    *,
    to_email: str,
    subject: str,
    template: str,
    title: str,
    paragraphs: list[str],
    button: tuple[str, str] | None = None,
    user_id: int | None = None,
) -> EmailLog:
    text, html_body = build_message(title, paragraphs, button)
    log = EmailLog(
        user_id=user_id,
        to_email=to_email,
        subject=subject,
        template=template,
        body_text=text,
        body_html=html_body,
        status=EmailStatus.QUEUED,
    )
    db.add(log)
    db.flush()
    if background is not None:
        background.add_task(deliver_email, log.id)
    return log


def deliver_email(log_id: int) -> None:
    """Deliver one EmailLog. Uses its own session because it runs after the request."""
    s = get_settings()
    with SessionLocal() as db:
        log = db.get(EmailLog, log_id)
        if log is None or log.status in (EmailStatus.SENT, EmailStatus.DEV_LOGGED):
            return
        log.attempts += 1
        try:
            if not s.smtp_host:
                if s.is_production:
                    raise RuntimeError("SMTP is not configured (SMTP_HOST is empty)")
                logger.info("[DEV EMAIL - not sent] to=%s subject=%s\n%s", log.to_email, log.subject, log.body_text)
                log.status = EmailStatus.DEV_LOGGED
                log.error = None
            else:
                msg = EmailMessage()
                msg["From"] = s.smtp_from
                msg["To"] = log.to_email
                msg["Subject"] = log.subject
                msg.set_content(log.body_text)
                msg.add_alternative(log.body_html, subtype="html")
                with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
                    if s.smtp_starttls:
                        smtp.starttls()
                    if s.smtp_username:
                        smtp.login(s.smtp_username, s.smtp_password)
                    smtp.send_message(msg)
                log.status = EmailStatus.SENT
                log.sent_at = utcnow()
                log.error = None
        except Exception as exc:  # noqa: BLE001 - any delivery failure is recorded and retryable
            logger.warning("Email delivery failed (log %s): %s", log_id, exc)
            log.status = EmailStatus.FAILED
            log.error = str(exc)[:1000]
        db.commit()

"""
Email service with optional SendGrid support and SMTP fallback.

Usage:
- Configure `SENDGRID_API_KEY` in your .env and optionally set `EMAIL_PROVIDER=sendgrid`.
- If SendGrid is not configured or fails, the code falls back to SMTP as configured.
"""
from __future__ import annotations

import base64
import logging

from datetime import datetime
import resend
from pathlib import Path
from typing import List, Optional

import aiosmtplib
import httpx

from app.config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()



async def send_email(
    to_email:     str,
    subject:      str,
    html_content: str,
    text_content: str = None,
) -> bool:
    try:
        resend.api_key = settings.RESEND_API_KEY
        params = {
            "from":    f"{settings.FROM_NAME} <onboarding@resend.dev>",
            "to":      [to_email],
            "subject": subject,
            "html":    html_content,
        }
        if text_content:
            params["text"] = text_content
        resend.Emails.send(params)
        log.info("✅ Email sent → %s", to_email)
        return True
    except Exception as e:
        log.error("❌ Email failed → %s | %s", to_email, e)
        return False

# --- Template builders ---
def build_welcome_email(email: str, unsubscribe_token: str) -> tuple[str, str, list[str]]:
    unsubscribe_url = f"{settings.APP_URL}/unsubscribe?token={unsubscribe_token}"
    today = datetime.now().strftime("%d %b %Y").upper()
    html = f"""<html><body><h1>Welcome</h1><p>You subscribed as {email}.</p><p><a href='{unsubscribe_url}'>Unsubscribe</a></p></body></html>"""
    docs_file = Path(__file__).resolve().parents[1] / "docs" / "vim_complete_guide_v2.pdf"
    attachments: List[str] = []
    if docs_file.exists():
        attachments.append(str(docs_file))
    return ("Welcome to Find me in the terminal", html, attachments)


def build_daily_drop_email(command: str, description: str, example: str, tip: str, unsubscribe_token: str) -> tuple[str, str]:
    unsubscribe_url = f"{settings.APP_URL}/unsubscribe?token={unsubscribe_token}"
    html = f"<html><body><h1>{command}</h1><p>{description}</p><p>{example}</p><p>{tip}</p><p><a href='{unsubscribe_url}'>Unsubscribe</a></p></body></html>"
    return (f"Daily Drop: {command}", html)


def build_broadcast_email(subject: str, html_body: str, unsubscribe_token: str) -> tuple[str, str]:
    unsubscribe_url = f"{settings.APP_URL}/unsubscribe?token={unsubscribe_token}"
    html = f"{html_body}<p><a href='{unsubscribe_url}'>Unsubscribe</a></p>"
    return subject, html

"""
Subscribers Router
──────────────────
POST   /subscribe              → add subscriber, fire welcome email
GET    /unsubscribe            → one-click unsubscribe via token (from email link)
POST   /unsubscribe            → unsubscribe via email address (from form)
GET    /admin/subscribers      → list all subscribers (admin)
DELETE /admin/subscribers/{id} → hard delete (admin)
"""
import secrets
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models   import Subscriber, SubscriberStatus, EmailLog, EmailStatus
from app.schemas  import (
    SubscribeRequest, SubscribeResponse,
    UnsubscribeResponse, SubscriberListResponse, SubscriberOut,
)
from app.services.email_service import (
    send_email,
    build_welcome_email,
)

router = APIRouter(tags=["Subscribers"])
log    = logging.getLogger(__name__)


# ── Helper: generate unsubscribe token ────────────────────────────────────
def _make_token() -> str:
    return secrets.token_urlsafe(32)


# ── POST /subscribe ────────────────────────────────────────────────────────
@router.post("/subscribe", response_model=SubscribeResponse, status_code=201)
async def subscribe(
    data:             SubscribeRequest,
    request:          Request,
    background_tasks: BackgroundTasks,
    db:               AsyncSession = Depends(get_db),
):
    email = data.email

    # Check duplicate
    existing = await db.scalar(select(Subscriber).where(Subscriber.email == email))
    if existing:
        if existing.status == SubscriberStatus.UNSUBSCRIBED:
            # Re-subscribe
            existing.status             = SubscriberStatus.ACTIVE
            existing.unsubscribed_at    = None
            existing.subscribed_at      = datetime.utcnow()
            existing.unsubscribe_token  = _make_token()
            await db.flush()
            background_tasks.add_task(_send_welcome, email, existing.unsubscribe_token, str(existing.id), db)
            return SubscribeResponse(success=True, message="Welcome back! You've been re-subscribed.")
        raise HTTPException(status_code=409, detail="Email already subscribed.")

    # Create subscriber
    sub = Subscriber(
        email             = email,
        status            = SubscriberStatus.ACTIVE,
        unsubscribe_token = _make_token(),
        ip_address        = request.client.host if request.client else None,
        user_agent        = request.headers.get("user-agent", "")[:512],
        source            = "landing_page",
    )
    db.add(sub)
    await db.flush()   # get sub.id before background task

    # Fire welcome email asynchronously (does NOT block the HTTP response)
    background_tasks.add_task(_send_welcome, email, sub.unsubscribe_token, str(sub.id), db)

    log.info("New subscriber: %s from %s", email, sub.ip_address)
    return SubscribeResponse(
        success=True,
        message=f"Subscribed! Check {email} — your Vim cheat sheet is on the way.",
    )


async def _send_welcome(email: str, token: str, subscriber_id: str, db: AsyncSession):
    """Background task: send welcome email and log it."""
    subject, html, attachments = build_welcome_email(email, token)
    ok, err = await send_email(email, subject, html, attachments=attachments)

    # Log the send attempt in a new session (background runs after response)
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        log_entry = EmailLog(
            subscriber_id = subscriber_id,
            email_id      = None,
            status        = EmailStatus.SENT if ok else EmailStatus.FAILED,
            sent_at       = datetime.utcnow() if ok else None,
            error_message = None if ok else (err or "SMTP send failed"),
        )
        session.add(log_entry)
        if ok:
            await session.execute(
                update(Subscriber)
                .where(Subscriber.id == subscriber_id)
                .values(last_emailed_at=datetime.utcnow())
            )
        await session.commit()


# ── GET /unsubscribe?token=xxx  (one-click from email link) ───────────────
@router.get("/unsubscribe", response_model=UnsubscribeResponse)
async def unsubscribe_by_token(
    token: str = Query(..., min_length=10),
    db:    AsyncSession = Depends(get_db),
):
    sub = await db.scalar(select(Subscriber).where(Subscriber.unsubscribe_token == token))
    if not sub:
        raise HTTPException(status_code=404, detail="Invalid or expired unsubscribe link.")
    if sub.status == SubscriberStatus.UNSUBSCRIBED:
        return UnsubscribeResponse(success=True, message="Already unsubscribed.")

    sub.status          = SubscriberStatus.UNSUBSCRIBED
    sub.unsubscribed_at = datetime.utcnow()
    await db.flush()
    log.info("Unsubscribed: %s", sub.email)
    return UnsubscribeResponse(success=True, message=f"{sub.email} has been unsubscribed.")


# ── POST /unsubscribe  (via email address from form) ─────────────────────
@router.post("/unsubscribe", response_model=UnsubscribeResponse)
async def unsubscribe_by_email(
    data: SubscribeRequest,
    db:   AsyncSession = Depends(get_db),
):
    sub = await db.scalar(select(Subscriber).where(Subscriber.email == data.email))
    if not sub:
        # Return success regardless to avoid email enumeration
        return UnsubscribeResponse(success=True, message="If that email exists, it has been unsubscribed.")

    sub.status          = SubscriberStatus.UNSUBSCRIBED
    sub.unsubscribed_at = datetime.utcnow()
    await db.flush()
    return UnsubscribeResponse(success=True, message=f"{sub.email} has been unsubscribed.")


# ── GET /admin/subscribers ─────────────────────────────────────────────────
@router.get("/admin/subscribers", response_model=SubscriberListResponse)
async def list_subscribers(
    db: AsyncSession = Depends(get_db),
):
    all_subs    = (await db.scalars(select(Subscriber).order_by(Subscriber.subscribed_at.desc()))).all()
    active      = [s for s in all_subs if s.status == SubscriberStatus.ACTIVE]
    unsub       = [s for s in all_subs if s.status == SubscriberStatus.UNSUBSCRIBED]

    return SubscriberListResponse(
        total        = len(all_subs),
        active       = len(active),
        unsubscribed = len(unsub),
        subscribers  = [SubscriberOut.model_validate(s) for s in all_subs],
    )

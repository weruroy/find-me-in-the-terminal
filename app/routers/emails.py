"""
Emails Router
─────────────
POST /admin/send-daily     → send today's Linux command drop to all active subscribers
POST /admin/broadcast      → send a custom HTML email to all active subscribers
GET  /admin/stats          → dashboard stats
"""
import logging
from datetime import datetime, date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, AsyncSessionLocal
from app.models   import Subscriber, SubscriberStatus, Email, EmailLog, EmailType, EmailStatus
from app.schemas  import (
    BroadcastRequest, BroadcastResponse,
    DailyDropRequest, StatsResponse,
)
from app.services.email_service import (
    send_email,
    build_daily_drop_email,
    build_broadcast_email,
)

router = APIRouter(prefix="/admin", tags=["Admin / Emails"])
log    = logging.getLogger(__name__)


# ── POST /admin/send-daily ─────────────────────────────────────────────────
@router.post("/send-daily", response_model=BroadcastResponse)
async def send_daily_drop(
    data:             DailyDropRequest,
    background_tasks: BackgroundTasks,
    db:               AsyncSession = Depends(get_db),
):
    """
    Fire the daily Linux command email to all ACTIVE subscribers.
    Typically called by an external cron / scheduler at 06:00 UTC:

        curl -X POST https://your-domain/admin/send-daily \\
             -H 'Content-Type: application/json' \\
             -d '{"command":"grep -rn","description":"...","example":"...","tip":"..."}'
    """
    # Fetch all active subscribers
    subs = (await db.scalars(
        select(Subscriber).where(Subscriber.status == SubscriberStatus.ACTIVE)
    )).all()

    if not subs:
        raise HTTPException(status_code=404, detail="No active subscribers.")

    # Persist the email record
    subject, sample_html = build_daily_drop_email(
        data.command, data.description, data.example, data.tip,
        unsubscribe_token="PLACEHOLDER",
    )
    email_record = Email(
        email_type = EmailType.DAILY_DROP,
        subject    = subject,
        html_body  = sample_html,
        text_body  = None,
        sent_at    = None,
    )
    db.add(email_record)
    await db.flush()
    email_id = email_record.id

    # Queue the actual sends as a background task (non-blocking)
    background_tasks.add_task(
        _blast_daily,
        email_id     = str(email_id),
        subs_data    = [(str(s.id), s.email, s.unsubscribe_token) for s in subs],
        command      = data.command,
        description  = data.description,
        example      = data.example,
        tip          = data.tip,
    )

    return BroadcastResponse(
        success    = True,
        email_id   = email_id,
        queued_for = len(subs),
        message    = f"Daily drop queued for {len(subs)} subscribers.",
    )


async def _blast_daily(
    email_id:    str,
    subs_data:   list[tuple[str, str, str]],
    command:     str,
    description: str,
    example:     str,
    tip:         str,
):
    """Background: send daily drop to every subscriber and log results."""
    sent = failed = 0
    async with AsyncSessionLocal() as session:
        for sub_id, email, token in subs_data:
            subject, html = build_daily_drop_email(command, description, example, tip, token)
            ok, err = await send_email(email, subject, html)
            log_entry = EmailLog(
                subscriber_id = sub_id,
                email_id      = email_id,
                status        = EmailStatus.SENT if ok else EmailStatus.FAILED,
                sent_at       = datetime.utcnow() if ok else None,
                error_message = None if ok else (err or "SMTP send failed"),
            )
            session.add(log_entry)
            if ok:
                sent += 1
            else:
                failed += 1

        # Mark email record as sent
        from sqlalchemy import update as sa_update
        await session.execute(
            sa_update(Email)
            .where(Email.id == email_id)
            .values(sent_at=datetime.utcnow())
        )
        await session.commit()

    log.info("Daily drop complete — sent: %d | failed: %d", sent, failed)


# ── POST /admin/broadcast ──────────────────────────────────────────────────
@router.post("/broadcast", response_model=BroadcastResponse)
async def broadcast(
    data:             BroadcastRequest,
    background_tasks: BackgroundTasks,
    db:               AsyncSession = Depends(get_db),
):
    """Send a custom HTML email to all active subscribers."""
    subs = (await db.scalars(
        select(Subscriber).where(Subscriber.status == SubscriberStatus.ACTIVE)
    )).all()

    if not subs:
        raise HTTPException(status_code=404, detail="No active subscribers.")

    # Persist email record
    email_record = Email(
        email_type = data.email_type,
        subject    = data.subject,
        html_body  = data.html_body,
        text_body  = data.text_body,
    )
    db.add(email_record)
    await db.flush()
    email_id = email_record.id

    background_tasks.add_task(
        _blast_broadcast,
        email_id   = str(email_id),
        subject    = data.subject,
        html_body  = data.html_body,
        subs_data  = [(str(s.id), s.email, s.unsubscribe_token) for s in subs],
    )

    return BroadcastResponse(
        success    = True,
        email_id   = email_id,
        queued_for = len(subs),
        message    = f"Broadcast queued for {len(subs)} subscribers.",
    )


async def _blast_broadcast(
    email_id:  str,
    subject:   str,
    html_body: str,
    subs_data: list[tuple[str, str, str]],
):
    sent = failed = 0
    async with AsyncSessionLocal() as session:
        for sub_id, email, token in subs_data:
            _, personalized_html = build_broadcast_email(subject, html_body, token)
            ok, err = await send_email(email, subject, personalized_html)
            session.add(EmailLog(
                subscriber_id = sub_id,
                email_id      = email_id,
                status        = EmailStatus.SENT if ok else EmailStatus.FAILED,
                sent_at       = datetime.utcnow() if ok else None,
                error_message = None if ok else (err or "SMTP send failed"),
            ))
            if ok: sent += 1
            else:  failed += 1

        from sqlalchemy import update as sa_update
        await session.execute(
            sa_update(Email)
            .where(Email.id == email_id)
            .values(sent_at=datetime.utcnow())
        )
        await session.commit()

    log.info("Broadcast complete — sent: %d | failed: %d", sent, failed)


# ── GET /admin/stats ───────────────────────────────────────────────────────
@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    total  = await db.scalar(select(func.count()).select_from(Subscriber))
    active = await db.scalar(
        select(func.count()).select_from(Subscriber)
        .where(Subscriber.status == SubscriberStatus.ACTIVE)
    )
    sent_total = await db.scalar(
        select(func.count()).select_from(EmailLog)
        .where(EmailLog.status == EmailStatus.SENT)
    )
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today  = await db.scalar(
        select(func.count()).select_from(EmailLog)
        .where(EmailLog.status == EmailStatus.SENT, EmailLog.sent_at >= today_start)
    )
    last_email = await db.scalar(
        select(EmailLog.sent_at)
        .where(EmailLog.status == EmailStatus.SENT)
        .order_by(EmailLog.sent_at.desc())
        .limit(1)
    )

    return StatsResponse(
        total_subscribers  = total  or 0,
        active_subscribers = active or 0,
        emails_sent_total  = sent_total or 0,
        emails_sent_today  = sent_today or 0,
        last_broadcast_at  = last_email,
    )

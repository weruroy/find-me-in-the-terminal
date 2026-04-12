from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict
from app.models import SubscriberStatus, EmailType, EmailStatus


# ── Subscriber schemas ─────────────────────────────────────────────────────
class SubscribeRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower().strip()


class SubscribeResponse(BaseModel):
    success: bool
    message: str


class UnsubscribeResponse(BaseModel):
    success: bool
    message: str


class SubscriberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:             uuid.UUID
    email:          str
    status:         SubscriberStatus
    subscribed_at:  datetime
    last_emailed_at: Optional[datetime]
    source:         Optional[str]


class SubscriberListResponse(BaseModel):
    total:       int
    active:      int
    unsubscribed: int
    subscribers: List[SubscriberOut]


# ── Email / broadcast schemas ──────────────────────────────────────────────
class BroadcastRequest(BaseModel):
    subject:    str
    html_body:  str
    text_body:  Optional[str] = None
    email_type: EmailType = EmailType.BROADCAST


class BroadcastResponse(BaseModel):
    success:    bool
    email_id:   uuid.UUID
    queued_for: int
    message:    str


class DailyDropRequest(BaseModel):
    command:     str
    description: str
    example:     str
    tip:         str


# ── Stats schema ───────────────────────────────────────────────────────────
class StatsResponse(BaseModel):
    total_subscribers:   int
    active_subscribers:  int
    emails_sent_total:   int
    emails_sent_today:   int
    last_broadcast_at:   Optional[datetime]

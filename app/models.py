import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


# ── Enums ──────────────────────────────────────────────────────────────────
class SubscriberStatus(str, enum.Enum):
    PENDING    = "pending"      # signed up, confirmation not yet sent
    ACTIVE     = "active"       # confirmed / receiving emails
    UNSUBSCRIBED = "unsubscribed"


class EmailType(str, enum.Enum):
    WELCOME     = "welcome"
    DAILY_DROP  = "daily_drop"
    DEEP_DIVE   = "deep_dive"
    BROADCAST   = "broadcast"


class EmailStatus(str, enum.Enum):
    QUEUED  = "queued"
    SENT    = "sent"
    FAILED  = "failed"
    SKIPPED = "skipped"


# ── Subscriber ────────────────────────────────────────────────────────────
class Subscriber(Base):
    __tablename__ = "subscribers"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email      = Column(String(320), unique=True, nullable=False, index=True)
    status     = Column(Enum(SubscriberStatus), default=SubscriberStatus.ACTIVE, nullable=False, index=True)

    # metadata
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)
    source     = Column(String(64), default="landing_page")   # landing_page | api | import

    # tokens
    unsubscribe_token = Column(String(64), unique=True, nullable=False, index=True)
    confirm_token     = Column(String(64), nullable=True)

    # timestamps
    subscribed_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    unsubscribed_at = Column(DateTime(timezone=True), nullable=True)
    last_emailed_at = Column(DateTime(timezone=True), nullable=True)

    # relationships
    email_logs = relationship("EmailLog", back_populates="subscriber", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Subscriber {self.email} [{self.status}]>"


# ── Email campaign / broadcast ─────────────────────────────────────────────
class Email(Base):
    __tablename__ = "emails"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_type = Column(Enum(EmailType), nullable=False, index=True)
    subject    = Column(String(998), nullable=False)
    html_body  = Column(Text, nullable=False)
    text_body  = Column(Text, nullable=True)

    # scheduling
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    sent_at      = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # relationships
    logs = relationship("EmailLog", back_populates="email", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Email [{self.email_type}] '{self.subject}'>"


# ── Email send log ─────────────────────────────────────────────────────────
class EmailLog(Base):
    __tablename__ = "email_logs"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscriber_id = Column(UUID(as_uuid=True), ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False, index=True)
    email_id      = Column(UUID(as_uuid=True), ForeignKey("emails.id", ondelete="CASCADE"),      nullable=True,  index=True)

    status        = Column(Enum(EmailStatus), default=EmailStatus.QUEUED, nullable=False, index=True)
    error_message = Column(Text, nullable=True)
    sent_at       = Column(DateTime(timezone=True), nullable=True)

    # relationships
    subscriber = relationship("Subscriber", back_populates="email_logs")
    email      = relationship("Email",      back_populates="logs")

"""
SQLAlchemy ORM Models for Ghost Copilot.
PostgreSQL and SQLite compatible.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=True) # None if using external OAuth / dev token
    full_name = Column(String(255), nullable=True)
    plan = Column(String(50), default="development", nullable=False) # development, free, pro, enterprise
    status = Column(String(50), default="active", nullable=False) # active, suspended, canceled
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    usages = relationship("Usage", back_populates="user", cascade="all, delete-orphan")
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), default="Interview Session", nullable=False)
    domain = Column(String(50), default="general", nullable=False) # technical, consulting, hr, general
    custom_instructions = Column(Text, nullable=True)
    status = Column(String(50), default="active", nullable=False) # active, closed, expired
    created_at = Column(DateTime, default=utc_now, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    user = relationship("User", back_populates="sessions")
    usages = relationship("Usage", back_populates="session", cascade="all, delete-orphan")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(50), default="mock", nullable=False) # stripe, lemonsqueezy, mock
    provider_customer_id = Column(String(255), nullable=True)
    provider_subscription_id = Column(String(255), nullable=True)
    plan = Column(String(50), default="development", nullable=False) # development, pro, enterprise
    status = Column(String(50), default="active", nullable=False) # active, past_due, canceled
    current_period_start = Column(DateTime, default=utc_now, nullable=False)
    current_period_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    user = relationship("User", back_populates="subscriptions")


class Usage(Base):
    __tablename__ = "usages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    operation = Column(String(50), nullable=False) # solve, transcribe, speech_vad
    timestamp = Column(DateTime, default=utc_now, nullable=False, index=True)
    tokens_used = Column(Integer, default=0, nullable=False)
    duration_ms = Column(Integer, default=0, nullable=False)
    metadata_json = Column(Text, nullable=True) # Safe operational metadata only (no full prompts)

    user = relationship("User", back_populates="usages")
    session = relationship("Session", back_populates="usages")


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    response_style = Column(String(50), default="crisp", nullable=False) # crisp, detailed, conversational
    custom_instructions = Column(Text, nullable=True)
    preferred_model = Column(String(100), default="qwen/qwen3.8-27b", nullable=False)
    audio_sensitivity_threshold = Column(Float, default=-30.0, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    user = relationship("User", back_populates="settings")

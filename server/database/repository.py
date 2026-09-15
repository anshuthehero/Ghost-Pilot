"""
Repository Layer for Database Interactions.
Keeps SQL queries isolated from business logic.
"""

from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from server.database.models import User, Session as UserSession, Subscription, Usage, UserSettings


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: str) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()

    def get_by_email(self, email: str) -> Optional[User]:
        return self.db.query(User).filter(User.email == email.lower()).first()

    def create(self, email: str, password_hash: Optional[str] = None, full_name: Optional[str] = None, plan: str = "development") -> User:
        user = User(
            email=email.lower(),
            password_hash=password_hash,
            full_name=full_name,
            plan=plan,
            status="active"
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        # Create default user settings
        settings = UserSettings(user_id=user.id)
        self.db.add(settings)
        self.db.commit()

        # Create active subscription record
        sub = Subscription(user_id=user.id, plan=plan, status="active")
        self.db.add(sub)
        self.db.commit()

        return user

    def get_or_create_dev_user(self) -> User:
        dev_email = "dev@ghostcopilot.local"
        user = self.get_by_email(dev_email)
        if not user:
            user = self.create(email=dev_email, full_name="Local Developer", plan="development")
        return user


class SessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_session(self, user_id: str, title: str = "Interview Session", domain: str = "general", custom_instructions: Optional[str] = None) -> UserSession:
        sess = UserSession(
            user_id=user_id,
            title=title,
            domain=domain,
            custom_instructions=custom_instructions,
            status="active"
        )
        self.db.add(sess)
        self.db.commit()
        self.db.refresh(sess)
        return sess

    def get_session(self, session_id: str, user_id: str) -> Optional[UserSession]:
        return self.db.query(UserSession).filter(UserSession.id == session_id, UserSession.user_id == user_id).first()

    def list_user_sessions(self, user_id: str, limit: int = 20) -> List[UserSession]:
        return self.db.query(UserSession).filter(UserSession.user_id == user_id).order_by(UserSession.created_at.desc()).limit(limit).all()

    def touch_session(self, session_id: str, user_id: str):
        """Update last_seen_at only if the session belongs to the given user (prevents IDOR)."""
        sess = self.db.query(UserSession).filter(
            UserSession.id == session_id, UserSession.user_id == user_id
        ).first()
        if sess:
            sess.last_seen_at = datetime.now(timezone.utc)
            self.db.commit()


class UsageRepository:
    def __init__(self, db: Session):
        self.db = db

    def record_usage(self, user_id: str, session_id: Optional[str], operation: str, tokens_used: int = 0, duration_ms: int = 0, metadata_json: Optional[str] = None) -> Usage:
        usage = Usage(
            user_id=user_id,
            session_id=session_id,
            operation=operation,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            metadata_json=metadata_json
        )
        self.db.add(usage)
        self.db.commit()
        self.db.refresh(usage)
        return usage

    def get_user_total_tokens(self, user_id: str) -> int:
        from sqlalchemy import func
        result = self.db.query(func.sum(Usage.tokens_used)).filter(Usage.user_id == user_id).scalar()
        return result or 0

    def get_user_daily_solve_count(self, user_id: str) -> int:
        """Returns the number of 'solve' operations the user has performed today (UTC).
        Used by EntitlementService to enforce per-plan daily quotas (fixes M-2)."""
        from sqlalchemy import func
        from datetime import date
        today_str = date.today().isoformat()  # e.g. "2026-09-07"
        result = self.db.query(func.count(Usage.id)).filter(
            Usage.user_id == user_id,
            Usage.operation == "solve",
            # Usage.timestamp is the DateTime column on the Usage model
            func.date(Usage.timestamp) == today_str
        ).scalar()
        return result or 0

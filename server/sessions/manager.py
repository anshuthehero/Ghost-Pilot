"""
Multi-Tenant Session State Manager.
Replaces all global singleton variables with isolated, session-scoped context.
"""

import time
import asyncio
from typing import Dict, List, Optional, Deque
from collections import deque
from shared.schemas import MessageItem


class SessionContext:
    def __init__(self, session_id: str, user_id: str):
        self.session_id: str = session_id
        self.user_id: str = user_id
        self.history: Deque[Dict[str, str]] = deque(maxlen=8)
        self.active_gen_id: int = 0
        self.reading_until: float = 0.0
        self.custom_duration: str = "auto"
        self.subscribers: List[asyncio.Queue] = []
        self.lock: asyncio.Lock = asyncio.Lock()

    def add_subscriber(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.subscribers.append(q)
        return q

    def remove_subscriber(self, q: asyncio.Queue):
        if q in self.subscribers:
            self.subscribers.remove(q)

    async def broadcast(self, event: str, data: Dict):
        """Broadcasts an event ONLY to clients connected to this specific session."""
        dead = []
        for q in self.subscribers:
            try:
                await q.put({"event": event, "data": data})
            except Exception:
                dead.append(q)
        for d in dead:
            self.remove_subscriber(d)

    def abort_current_generation(self):
        """Increments gen_id to abort any in-flight LLM stream."""
        self.active_gen_id += 1
        self.reading_until = 0.0


class SessionManager:
    def __init__(self):
        self._sessions: Dict[str, SessionContext] = {}
        self._lock = asyncio.Lock()

    async def get_or_create_context(self, session_id: str, user_id: str) -> SessionContext:
        async with self._lock:
            key = f"{user_id}:{session_id}"
            if key not in self._sessions:
                self._sessions[key] = SessionContext(session_id=session_id, user_id=user_id)
            return self._sessions[key]

    async def get_context(self, session_id: str, user_id: str) -> Optional[SessionContext]:
        async with self._lock:
            key = f"{user_id}:{session_id}"
            return self._sessions.get(key)

    async def cleanup_idle_sessions(self, max_idle_seconds: int = 86400):
        """Periodic cleanup of abandoned in-memory session states."""
        # Future enhancement for Redis eviction
        pass


session_manager = SessionManager()

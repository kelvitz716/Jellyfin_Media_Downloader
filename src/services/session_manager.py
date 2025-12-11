"""
Session Manager - Replaces defaultdict with proper TTL-based sessions.

This module provides session state management with automatic expiry,
replacing the memory-leaking defaultdict pattern.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, Any


@dataclass
class UserSession:
    """Represents a user's session state."""
    user_id: int
    state: str
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(minutes=30))
    
    def is_expired(self) -> bool:
        """Check if session has expired."""
        return datetime.now() > self.expires_at
    
    def refresh(self, ttl_minutes: int = 30):
        """Extend session expiry."""
        self.expires_at = datetime.now() + timedelta(minutes=ttl_minutes)


class SessionManager:
    """
    Manages user sessions with automatic expiry.
    
    Replaces the defaultdict pattern with proper lifecycle management:
    - Sessions expire after TTL
    - Automatic cleanup on access
    - Memory-safe design
    """
    
    def __init__(self, ttl_minutes: int = 30):
        self._sessions: Dict[int, UserSession] = {}
        self._ttl = ttl_minutes
    
    def get(self, user_id: int) -> Optional[UserSession]:
        """
        Get session for user, returning None if expired or not found.
        """
        session = self._sessions.get(user_id)
        if session and session.is_expired():
            self.clear(user_id)
            return None
        return session
    
    def create(self, user_id: int, state: str, data: Optional[Dict[str, Any]] = None) -> UserSession:
        """
        Create a new session for user, replacing any existing one.
        """
        session = UserSession(
            user_id=user_id,
            state=state,
            data=data or {},
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(minutes=self._ttl)
        )
        self._sessions[user_id] = session
        return session
    
    def update(self, user_id: int, **kwargs) -> Optional[UserSession]:
        """
        Update existing session data. Returns None if session doesn't exist.
        """
        session = self.get(user_id)
        if session:
            session.data.update(kwargs)
            session.refresh(self._ttl)
        return session
    
    def clear(self, user_id: int):
        """Remove session for user."""
        self._sessions.pop(user_id, None)
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired sessions.
        Returns the number of sessions removed.
        """
        expired = [uid for uid, sess in self._sessions.items() if sess.is_expired()]
        for uid in expired:
            del self._sessions[uid]
        return len(expired)
    
    def __contains__(self, user_id: int) -> bool:
        """Check if user has an active (non-expired) session."""
        return self.get(user_id) is not None
    
    def __getitem__(self, user_id: int) -> Dict[str, Any]:
        """
        Dict-like access for backwards compatibility.
        Returns session data or empty dict if no session.
        """
        session = self.get(user_id)
        return session.data if session else {}
    
    def __setitem__(self, user_id: int, data: Dict[str, Any]):
        """
        Dict-like assignment for backwards compatibility.
        Creates or updates session with given data.
        """
        session = self.get(user_id)
        if session:
            session.data = data
            session.refresh(self._ttl)
        else:
            self.create(user_id, "active", data)


# Global session managers (replacing the defaultdict instances)
organize_sessions = SessionManager(ttl_minutes=30)
bulk_sessions = SessionManager(ttl_minutes=30)

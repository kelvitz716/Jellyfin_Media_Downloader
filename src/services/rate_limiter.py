"""
Rate Limiter - Prevent command spam and abuse.

This module provides rate limiting functionality to protect
bot commands from excessive usage.
"""
from collections import defaultdict
from time import time
from typing import Optional
from functools import wraps


class RateLimiter:
    """
    Token bucket rate limiter with per-user tracking.
    
    Example:
        limiter = RateLimiter(max_calls=10, period_seconds=60)
        
        if not limiter.is_allowed(user_id):
            await event.respond("⏳ Too many requests. Please wait.")
            return
    """
    
    def __init__(self, max_calls: int = 10, period_seconds: int = 60):
        """
        Initialize rate limiter.
        
        Args:
            max_calls: Maximum number of calls allowed in the period
            period_seconds: Time window in seconds
        """
        self.max_calls = max_calls
        self.period = period_seconds
        self._calls: dict[int, list[float]] = defaultdict(list)
    
    def is_allowed(self, user_id: int) -> bool:
        """
        Check if user is allowed to make a call.
        
        Cleans up old timestamps and checks if under limit.
        """
        now = time()
        # Clean up old timestamps
        self._calls[user_id] = [
            t for t in self._calls[user_id] 
            if now - t < self.period
        ]
        
        if len(self._calls[user_id]) >= self.max_calls:
            return False
        
        self._calls[user_id].append(now)
        return True
    
    def get_remaining(self, user_id: int) -> int:
        """Get remaining calls for user in current window."""
        now = time()
        recent = [t for t in self._calls[user_id] if now - t < self.period]
        return max(0, self.max_calls - len(recent))
    
    def get_reset_time(self, user_id: int) -> Optional[float]:
        """Get seconds until rate limit resets for user."""
        if not self._calls[user_id]:
            return None
        oldest = min(self._calls[user_id])
        reset = oldest + self.period - time()
        return max(0, reset)
    
    def cleanup(self) -> int:
        """
        Remove expired entries from all users.
        Returns number of users cleaned up.
        """
        now = time()
        cleaned = 0
        empty_users = []
        
        for user_id, timestamps in self._calls.items():
            self._calls[user_id] = [t for t in timestamps if now - t < self.period]
            if not self._calls[user_id]:
                empty_users.append(user_id)
        
        for user_id in empty_users:
            del self._calls[user_id]
            cleaned += 1
        
        return cleaned


# Pre-configured rate limiters for different use cases
command_limiter = RateLimiter(max_calls=10, period_seconds=60)      # 10 commands/minute
download_limiter = RateLimiter(max_calls=5, period_seconds=60)      # 5 downloads/minute
organize_limiter = RateLimiter(max_calls=20, period_seconds=300)    # 20 organizes/5 min


def rate_limited(limiter: RateLimiter = command_limiter, message: str = "⏳ Rate limit exceeded. Please wait."):
    """
    Decorator to apply rate limiting to handlers.
    
    Usage:
        @rate_limited()
        async def my_handler(event):
            ...
        
        @rate_limited(download_limiter, "Too many downloads!")
        async def download_handler(event):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(event, *args, **kwargs):
            user_id = getattr(event, 'sender_id', None) or getattr(event.query, 'user_id', None)
            if user_id and not limiter.is_allowed(user_id):
                reset_time = limiter.get_reset_time(user_id)
                full_message = message
                if reset_time:
                    full_message += f" (resets in {int(reset_time)}s)"
                await event.respond(full_message)
                return
            return await func(event, *args, **kwargs)
        return wrapper
    return decorator

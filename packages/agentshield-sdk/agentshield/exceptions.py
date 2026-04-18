"""Exception types for the AgentShield SDK."""

from __future__ import annotations

from typing import Any, Optional


class AgentShieldError(Exception):
    """Base exception for all AgentShield SDK errors."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class AuthenticationError(AgentShieldError):
    """Raised when the API key is invalid, missing, or deactivated (HTTP 401/403)."""


class RateLimitError(AgentShieldError):
    """Raised when the account's daily quota or per-minute rate limit is exhausted (HTTP 429).

    Attributes:
        retry_after: seconds until the caller should retry (parsed from Retry-After header when present).
    """

    def __init__(self, message: str, *, status_code: int = 429, payload: Any = None, retry_after: Optional[int] = None):
        super().__init__(message, status_code=status_code, payload=payload)
        self.retry_after = retry_after


class APIError(AgentShieldError):
    """Raised for any 4xx/5xx response that isn't specifically handled above."""


class TimeoutError(AgentShieldError):
    """Raised when a request times out."""

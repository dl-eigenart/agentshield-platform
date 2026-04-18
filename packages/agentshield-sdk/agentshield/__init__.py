"""AgentShield — Python SDK for the AgentShield prompt-injection API."""

from agentshield.client import AgentShield, AsyncAgentShield
from agentshield.models import Verdict, ClassifyResponse
from agentshield.exceptions import (
    AgentShieldError,
    AuthenticationError,
    RateLimitError,
    APIError,
    TimeoutError as AgentShieldTimeoutError,
)

__version__ = "0.1.0"
__all__ = [
    "AgentShield",
    "AsyncAgentShield",
    "Verdict",
    "ClassifyResponse",
    "AgentShieldError",
    "AuthenticationError",
    "RateLimitError",
    "APIError",
    "AgentShieldTimeoutError",
]

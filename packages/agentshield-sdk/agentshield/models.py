"""Response models for the AgentShield SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Verdict:
    """A single classification verdict returned by the AgentShield API.

    Attributes:
        is_injection: True if the input was flagged as a prompt-injection attempt.
        confidence: Model confidence in the verdict, in [0.0, 1.0].
        category: High-level category label (e.g. "benign", "jailbreak", "injection",
            "data_exfiltration"). May be None for older API versions.
        latency_ms: Server-side classification latency in milliseconds.
        model: Identifier of the classifier model that produced the verdict.
        request_id: Opaque identifier assigned by the gateway for this request.
        raw: Full raw JSON body from the API response. Useful for forward compatibility
            if the API adds fields the SDK does not yet model.
    """

    is_injection: bool
    confidence: float
    category: Optional[str] = None
    latency_ms: Optional[float] = None
    model: Optional[str] = None
    request_id: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Verdict":
        """Build a Verdict from the gateway's /v1/classify response body."""
        return cls(
            is_injection=bool(data.get("is_injection", data.get("injection", False))),
            confidence=float(data.get("confidence", 0.0)),
            category=data.get("category") or data.get("label"),
            latency_ms=_as_float(data.get("latency_ms")),
            model=data.get("model"),
            request_id=data.get("request_id") or data.get("id"),
            raw=dict(data),
        )


@dataclass
class ClassifyResponse:
    """Batch response wrapper for /v1/classify.

    The current gateway returns a single verdict per call, but the SDK exposes a
    list-shaped response so batching can be added without a breaking change.

    Attributes:
        verdicts: One or more verdicts, in input order.
        model: Classifier model identifier (mirrored from the first verdict).
        request_id: Opaque gateway request identifier.
        raw: Full raw JSON body from the API response.
    """

    verdicts: List[Verdict]
    model: Optional[str] = None
    request_id: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def verdict(self) -> Verdict:
        """Return the first verdict (the common single-input case)."""
        if not self.verdicts:
            raise ValueError("ClassifyResponse contains no verdicts")
        return self.verdicts[0]

    @property
    def is_injection(self) -> bool:
        """Convenience flag for the single-verdict case."""
        return self.verdict.is_injection

    @property
    def confidence(self) -> float:
        """Convenience field for the single-verdict case."""
        return self.verdict.confidence

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClassifyResponse":
        """Build a ClassifyResponse from the gateway's /v1/classify response body."""
        if "verdicts" in data and isinstance(data["verdicts"], list):
            verdicts = [Verdict.from_dict(v) for v in data["verdicts"]]
        else:
            # Single-verdict shape — wrap it.
            verdicts = [Verdict.from_dict(data)]
        return cls(
            verdicts=verdicts,
            model=data.get("model") or (verdicts[0].model if verdicts else None),
            request_id=data.get("request_id") or data.get("id"),
            raw=dict(data),
        )


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

"""Enterprise Observability, Distributed Tracing & PII Redaction Module.

Provides:
- PIIRedactor: Deep scrubbing of sensitive keys, tokens, emails, phone numbers, and credentials.
- StructuredLogger: Cloud Logging-compliant JSON logging with trace correlation.
- Distributed Tracing: OpenTelemetry instrumentation helpers for agent turns, tools, and domain rules.
- Intent & Outcome Taxonomy: Structured capture of athletic support intents and execution outcomes.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Span, StatusCode

logger = logging.getLogger(__name__)

# Ensure an active TracerProvider is registered so spans record valid trace contexts
if not isinstance(trace.get_tracer_provider(), TracerProvider):
    try:
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    except Exception:
        pass

# Tracer instance for small-team-support-agent
tracer = trace.get_tracer("small-team-support-agent", "0.1.0")


# =============================================================================
# 1. Intent & Outcome Taxonomy
# =============================================================================


class AgentIntent(StrEnum):
    """Categorized domain intents for the WTA tennis support system."""

    QUERY_SCHEDULE = "QUERY_SCHEDULE"
    PROPOSE_TRAINING = "PROPOSE_TRAINING"
    APPROVE_PROPOSAL = "APPROVE_PROPOSAL"
    REJECT_PROPOSAL = "REJECT_PROPOSAL"
    ATTACH_WORKOUT_SYLLABUS = "ATTACH_WORKOUT_SYLLABUS"
    ORDER_MEALS = "ORDER_MEALS"
    BOOK_PR_ACTIVITY = "BOOK_PR_ACTIVITY"
    SCOUT_OPPONENT = "SCOUT_OPPONENT"
    QUERY_TEAM_MEMORY = "QUERY_TEAM_MEMORY"
    OVERRIDE_PRIORITY = "OVERRIDE_PRIORITY"
    GENERAL_CONVERSATION = "GENERAL_CONVERSATION"


class ExecutionOutcome(StrEnum):
    """Execution outcomes and safety guardrail status codes."""

    SUCCESS = "SUCCESS"
    FATIGUE_GUARDRAIL_BLOCKED = "FATIGUE_GUARDRAIL_BLOCKED"
    DURATION_CAP_EXCEEDED = "DURATION_CAP_EXCEEDED"
    PR_BEFORE_TRAINING_BLOCKED = "PR_BEFORE_TRAINING_BLOCKED"
    GAME_DAY_PR_PROHIBITED = "GAME_DAY_PR_PROHIBITED"
    QUIET_HOURS_SILENCED = "QUIET_HOURS_SILENCED"
    CONFLICT_DETECTED = "CONFLICT_DETECTED"
    OVERRIDE_APPROVED = "OVERRIDE_APPROVED"
    OVERRIDE_REJECTED = "OVERRIDE_REJECTED"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    ERROR = "ERROR"


def classify_intent(text: str) -> AgentIntent:
    """Heuristic intent classifier for routing and telemetry tagging."""
    t = text.lower()
    # 1. Interactive proposal confirmations
    if "[approve]" in t or t.strip() in ("approve", "confirm", "approve override", "yes", "accept"):
        return AgentIntent.APPROVE_PROPOSAL
    if "[reject]" in t or t.strip() in ("reject", "cancel", "no", "deny"):
        return AgentIntent.REJECT_PROPOSAL

    # 2. Specific action intents
    if any(k in t for k in ["training", "court", "practice", "serve session"]) and any(
        k in t for k in ["schedule", "propose", "book", "min", "hour", "session"]
    ):
        return AgentIntent.PROPOSE_TRAINING
    if any(k in t for k in ["syllabus", "workout", "mobility", "warm-up", "banded"]):
        return AgentIntent.ATTACH_WORKOUT_SYLLABUS
    if any(
        k in t for k in ["sponsor", "meet-and-greet", "interview", "photo shoot", "media"]
    ) or bool(re.search(r"\bpr\b", t)):
        return AgentIntent.BOOK_PR_ACTIVITY
    if any(
        k in t for k in ["scout", "tactical", "video", "analysis", "kenin", "swiatek", "opponent"]
    ):
        return AgentIntent.SCOUT_OPPONENT
    if any(
        k in t for k in ["prefer", "preference", "memory", "dietary rule", "guideline", "remember"]
    ):
        return AgentIntent.QUERY_TEAM_MEMORY
    if (
        "meal plan" in t
        or "order meal" in t
        or ("breakfast" in t and "dinner" in t and "plan" in t)
    ):
        return AgentIntent.ORDER_MEALS
    if any(k in t for k in ["schedule", "agenda", "what is my", "what's my", "briefing"]):
        return AgentIntent.QUERY_SCHEDULE
    if any(k in t for k in ["dietary", "nutrition"]):
        return AgentIntent.ORDER_MEALS
    if "override" in t:
        return AgentIntent.OVERRIDE_PRIORITY
    return AgentIntent.GENERAL_CONVERSATION


# =============================================================================
# 2. PII Redaction Engine
# =============================================================================


class PIIRedactor:
    """High-performance regex and structural PII scrubber."""

    EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    PHONE_PATTERN = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
    # Match GitHub tokens, Google API keys, Bearer headers, generic tokens
    TOKEN_PATTERN = re.compile(
        r"(?:github_pat_[A-Za-z0-9_]{40,}|ghp_[A-Za-z0-9_]{30,}|AIza[0-9A-Za-z_-]{35})"
    )
    BEARER_PATTERN = re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]+", re.IGNORECASE)
    CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
    SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

    SENSITIVE_KEYS = frozenset(
        {
            "password",
            "secret",
            "token",
            "api_key",
            "apikey",
            "authorization",
            "auth",
            "credential",
            "credentials",
            "private_key",
            "gemini_api_key",
        }
    )

    @classmethod
    def redact_text(cls, text: str) -> str:
        """Sanitize sensitive patterns from raw string."""
        if not text or not isinstance(text, str):
            return text

        # 1. API Keys & Auth tokens
        text = cls.TOKEN_PATTERN.sub("[SECRET_REDACTED]", text)
        text = cls.BEARER_PATTERN.sub(r"\1[TOKEN_REDACTED]", text)

        # 2. Communication PII
        text = cls.EMAIL_PATTERN.sub("[EMAIL_REDACTED]", text)
        text = cls.PHONE_PATTERN.sub("[PHONE_REDACTED]", text)

        # 3. Financial & Government Identifiers
        text = cls.CREDIT_CARD_PATTERN.sub("[PAYMENT_REDACTED]", text)
        text = cls.SSN_PATTERN.sub("[SSN_REDACTED]", text)

        return text

    @classmethod
    def redact(cls, data: Any) -> Any:
        """Deeply redact PII from nested structures (dict, list, string)."""
        if isinstance(data, str):
            return cls.redact_text(data)

        if isinstance(data, Mapping):
            cleaned: dict[str, Any] = {}
            for k, v in data.items():
                k_str = str(k)
                if any(sk in k_str.lower() for sk in cls.SENSITIVE_KEYS):
                    cleaned[k_str] = "[REDACTED]"
                else:
                    cleaned[k_str] = cls.redact(v)
            return cleaned

        if isinstance(data, Sequence) and not isinstance(data, (bytes, bytearray)):
            return [cls.redact(item) for item in data]

        return data


# =============================================================================
# 3. Distributed Tracing Utilities (OpenTelemetry)
# =============================================================================


def get_current_trace_context() -> tuple[str | None, str | None]:
    """Retrieve the current active trace ID and span ID as formatted hex strings."""
    span = trace.get_current_span()
    if span and span.is_recording():
        ctx = span.get_span_context()
        if ctx and ctx.is_valid:
            trace_id = format(ctx.trace_id, "032x")
            span_id = format(ctx.span_id, "016x")
            return trace_id, span_id
    return None, None


@contextmanager
def trace_span(
    name: str,
    attributes: dict[str, Any] | None = None,
    component: str = "agent_core",
) -> Generator[Span, None, None]:
    """Context manager creating an OpenTelemetry span with PII-sanitized attributes."""
    safe_attributes: dict[str, Any] = {"component": component}
    if attributes:
        for k, v in attributes.items():
            safe_val = PIIRedactor.redact(v)
            if isinstance(safe_val, (str, bool, int, float)):
                safe_attributes[k] = safe_val
            else:
                safe_attributes[k] = str(safe_val)

    with tracer.start_as_current_span(name, attributes=safe_attributes) as span:
        try:
            yield span
            span.set_status(StatusCode.OK)
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, description=str(exc))
            raise


# =============================================================================
# 4. Structured JSON Logging (Google Cloud Logging Standard)
# =============================================================================


class StructuredLogger:
    """Emits JSON-formatted structured logs correlating with Google Cloud Trace."""

    def __init__(self, name: str = "small-team-support-agent"):
        self.name = name
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "")

    def _log(
        self,
        severity: str,
        message: str,
        intent: AgentIntent | str | None = None,
        outcome: ExecutionOutcome | str | None = None,
        target_persona: str | None = None,
        duration_ms: float | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        component: str = "app",
    ) -> dict[str, Any]:
        """Construct and emit a single JSON log payload."""
        trace_id, span_id = get_current_trace_context()

        # Sanitize all text fields through PII redactor
        safe_message = PIIRedactor.redact_text(message)
        safe_metadata = PIIRedactor.redact(metadata) if metadata else None

        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": severity.upper(),
            "message": safe_message,
            "component": component,
            "logger": self.name,
        }

        # Google Cloud Logging Trace correlation
        if trace_id:
            if self.project_id:
                payload["logging.googleapis.com/trace"] = (
                    f"projects/{self.project_id}/traces/{trace_id}"
                )
            else:
                payload["logging.googleapis.com/trace"] = trace_id
            payload["logging.googleapis.com/trace_sampled"] = True

        if span_id:
            payload["logging.googleapis.com/spanId"] = span_id

        # Intent & Outcome telemetry
        if intent:
            payload["intent"] = str(intent)
        if outcome:
            payload["outcome"] = str(outcome)
        if target_persona:
            payload["target_persona"] = target_persona
        if duration_ms is not None:
            payload["duration_ms"] = round(duration_ms, 2)
        if session_id:
            payload["session_id"] = session_id
        if user_id:
            payload["user_id"] = user_id
        if safe_metadata:
            payload["metadata"] = safe_metadata

        # Output NDJSON line to stdout/stderr
        json_output = json.dumps(payload, ensure_ascii=False)
        if severity.upper() in ("ERROR", "CRITICAL"):
            sys.stderr.write(json_output + "\n")
            sys.stderr.flush()
        else:
            sys.stdout.write(json_output + "\n")
            sys.stdout.flush()

        return payload

    def info(self, message: str, **kwargs: Any) -> dict[str, Any]:
        return self._log("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> dict[str, Any]:
        return self._log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> dict[str, Any]:
        return self._log("ERROR", message, **kwargs)

    def audit(
        self,
        event_name: str,
        intent: AgentIntent | str,
        outcome: ExecutionOutcome | str,
        actor: str,
        details: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Record a structured audit log entry."""
        meta = {"event_name": event_name, "actor": actor}
        if details:
            meta.update(details)
        return self._log(
            "INFO",
            f"Audit event [{event_name}]: actor={actor}, intent={intent}, outcome={outcome}",
            intent=intent,
            outcome=outcome,
            metadata=meta,
            component="audit",
            **kwargs,
        )


# Global singleton logger
structured_logger = StructuredLogger()

"""Unit tests for Enterprise Observability, Distributed Tracing, and PII Redaction."""

import pytest

from app.observability import (
    AgentIntent,
    ExecutionOutcome,
    PIIRedactor,
    classify_intent,
    get_current_trace_context,
    structured_logger,
    trace_span,
)


class TestPIIRedaction:
    """Test suite verifying comprehensive PII scrubbing."""

    def test_redact_emails(self):
        text = "Please reach out to support@wta-tennis.com or gina.player@pro-tour.org immediately."
        redacted = PIIRedactor.redact_text(text)
        assert "support@wta-tennis.com" not in redacted
        assert "gina.player@pro-tour.org" not in redacted
        assert "[EMAIL_REDACTED]" in redacted

    def test_redact_phone_numbers(self):
        text = "Emergency contact: +1 (555) 234-5678 or 800-555-0199."
        redacted = PIIRedactor.redact_text(text)
        assert "234-5678" not in redacted
        assert "800-555-0199" not in redacted
        assert "[PHONE_REDACTED]" in redacted

    def test_redact_api_tokens(self):
        # Dynamically compose synthetic fake test strings to prevent static secret scanners from flagging false positives
        fake_pat = "github" + "_pat_" + ("TEST_FAKE_TOKEN_" * 5)
        fake_ghp = "gh" + "p_" + ("FAKE_KEY_FOR_TESTING_" * 2)
        fake_aiza = "AI" + "za" + "Sy" + "FakeMockApiKeyForTesting123456789"

        raw_pat = f"Use token {fake_pat}"
        raw_ghp = f"Or token {fake_ghp}"
        raw_aiza = f"Google API Key: {fake_aiza}"

        assert "[SECRET_REDACTED]" in PIIRedactor.redact_text(raw_pat)
        assert "TEST_FAKE_TOKEN_" not in PIIRedactor.redact_text(raw_pat)
        assert "[SECRET_REDACTED]" in PIIRedactor.redact_text(raw_ghp)
        assert "[SECRET_REDACTED]" in PIIRedactor.redact_text(raw_aiza)

    def test_redact_bearer_headers(self):
        # Synthetic Bearer token using split string
        fake_bearer = "ya" + "29." + "MockBearerTokenForUnitTesting12345"
        auth_header = f"Authorization: Bearer {fake_bearer}"
        redacted = PIIRedactor.redact_text(auth_header)
        assert "ya" + "29" not in redacted
        assert "Bearer [TOKEN_REDACTED]" in redacted

    def test_redact_payment_and_ssn(self):
        cc = "Card: 4532-1234-5678-9010 on file, SSN: 123-45-6789"
        redacted = PIIRedactor.redact_text(cc)
        assert "4532" not in redacted
        assert "123-45-6789" not in redacted
        assert "[PAYMENT_REDACTED]" in redacted
        assert "[SSN_REDACTED]" in redacted

    def test_recursive_nested_dict_redaction(self):
        payload = {
            "player": "Gina",
            "api_key": "super_secret_token_12345",
            "metadata": {
                "coach_email": "gor@team.org",
                "auth_token": "token_xyz",
                "nested_list": ["clean item", "contact: user@example.com"],
            },
        }
        cleaned = PIIRedactor.redact(payload)
        assert cleaned["player"] == "Gina"
        assert cleaned["api_key"] == "[REDACTED]"
        assert cleaned["metadata"]["auth_token"] == "[REDACTED]"
        assert cleaned["metadata"]["coach_email"] == "[EMAIL_REDACTED]"
        assert "[EMAIL_REDACTED]" in cleaned["metadata"]["nested_list"][1]


class TestIntentAndOutcomeClassification:
    """Test suite for intent classification heuristic."""

    def test_intent_classification(self):
        assert classify_intent("What is my schedule for today?") == AgentIntent.QUERY_SCHEDULE
        assert (
            classify_intent("Schedule 90-min court training at 14:30")
            == AgentIntent.PROPOSE_TRAINING
        )
        assert classify_intent("[Approve] confirm training") == AgentIntent.APPROVE_PROPOSAL
        assert classify_intent("[Reject] do not book") == AgentIntent.REJECT_PROPOSAL
        assert (
            classify_intent("Workout syllabus: banded hip walks")
            == AgentIntent.ATTACH_WORKOUT_SYLLABUS
        )
        assert (
            classify_intent("Meal plan: oatmeal for breakfast, salmon for dinner")
            == AgentIntent.ORDER_MEALS
        )
        assert classify_intent("Book sponsor photo shoot at 16:30") == AgentIntent.BOOK_PR_ACTIVITY
        assert (
            classify_intent("Book tactical video scouting vs Kenin") == AgentIntent.SCOUT_OPPONENT
        )
        assert (
            classify_intent("What does Gina prefer for recovery dinner?")
            == AgentIntent.QUERY_TEAM_MEMORY
        )


class TestDistributedTracingAndStructuredLogging:
    """Test suite for OpenTelemetry distributed spans and JSON logging."""

    def test_trace_span_lifecycle(self):
        with trace_span("unit_test_span", attributes={"test.key": "test_value"}) as span:
            trace_id, span_id = get_current_trace_context()
            assert trace_id is not None
            assert span_id is not None
            assert span.is_recording()

    def test_trace_span_error_recording(self):
        with pytest.raises(ValueError):
            with trace_span("failing_span"):
                raise ValueError("Deliberate test failure")

    def test_structured_logger_payload_format(self):
        with trace_span("test_logger_span"):
            entry = structured_logger.info(
                "Court training booked successfully",
                intent=AgentIntent.PROPOSE_TRAINING,
                outcome=ExecutionOutcome.SUCCESS,
                target_persona="gor",
                duration_ms=52.4,
                metadata={"court": "Court 3", "email": "coach@tennis.com"},
            )

        # Assert mandatory JSON schema fields
        assert entry["severity"] == "INFO"
        assert entry["message"] == "Court training booked successfully"
        assert entry["intent"] == "PROPOSE_TRAINING"
        assert entry["outcome"] == "SUCCESS"
        assert entry["target_persona"] == "gor"
        assert entry["duration_ms"] == 52.4
        assert "logging.googleapis.com/trace" in entry
        assert "logging.googleapis.com/spanId" in entry
        # Verify metadata was sanitized of PII
        assert entry["metadata"]["email"] == "[EMAIL_REDACTED]"

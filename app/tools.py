"""ADK 2.0 Function Tools wrapping the deterministic engine.

Exposes clean, type-annotated tool functions instrumented with:
- Distributed OpenTelemetry tracing spans
- Structured JSON logging (Cloud Logging format)
- Intent & outcome classification
- Automatic PII redaction
"""

from __future__ import annotations

import time
from typing import Any

from app.engine import calendar_store
from app.observability import (
    AgentIntent,
    ExecutionOutcome,
    PIIRedactor,
    structured_logger,
    trace_span,
)


def get_daily_schedule(target_date: str = "2026-09-02") -> str:
    """Fetch Gina's complete daily chronological schedule and active 1-hour pre-activity alerts.

    Applies the Sleep Quiet Hours policy (22:00 - 07:30), silencing early morning alarms.

    Args:
        target_date: Date in YYYY-MM-DD format (default: '2026-09-02').

    Returns:
        Formatted textual agenda and alerts markdown table.
    """
    t0 = time.perf_counter()
    with trace_span(
        "tool.get_daily_schedule",
        attributes={"target_date": target_date},
        component="sports_science_engine",
    ):
        result = calendar_store.format_daily_agenda_and_alerts(target_date)
        duration_ms = (time.perf_counter() - t0) * 1000

        structured_logger.info(
            f"Daily schedule & alerts retrieved for {target_date}",
            intent=AgentIntent.QUERY_SCHEDULE,
            outcome=ExecutionOutcome.SUCCESS,
            target_persona="gina",
            duration_ms=duration_ms,
            metadata={"target_date": target_date, "response_length": len(result)},
            component="sports_science_engine",
        )
        return result


def propose_court_training(
    training_date: str,
    start_time: str,
    duration_minutes: int,
    court: str = "Court 3",
    syllabus: str | None = None,
) -> dict[str, Any]:
    """Propose a court training session for Head Coach Gor.

    Enforces:
    1. Maximum 120-minute (2-hour) duration limit.
    2. 4-day consecutive fatigue guardrail (mandatory rest on day 5).
    3. No training on official match days.
    4. Auto-couples a 1-hour pre-training workout for PT Ma.
    5. Priority collision detection & override negotiation if overlapping lower-priority PR events.

    Args:
        training_date: Date in YYYY-MM-DD format (e.g. '2026-09-02').
        start_time: Start time in HH:MM format (e.g. '14:30').
        duration_minutes: Duration in minutes (must be <= 120).
        court: Court name or identifier (e.g. 'Court 3', 'Court 1').
        syllabus: Training syllabus or coaching focus.

    Returns:
        Result dict containing proposal status, pending details, options, or rejection reason.
    """
    t0 = time.perf_counter()
    with trace_span(
        "tool.propose_court_training",
        attributes={
            "training_date": training_date,
            "start_time": start_time,
            "duration_minutes": duration_minutes,
            "court": court,
        },
        component="sports_science_engine",
    ):
        result = calendar_store.propose_training(
            training_date=training_date,
            start_time=start_time,
            duration_minutes=duration_minutes,
            court=court,
            syllabus=syllabus,
        )
        duration_ms = (time.perf_counter() - t0) * 1000

        outcome = ExecutionOutcome.SUCCESS
        if not result.get("success", False):
            err = result.get("error_code")
            if err == "FATIGUE_LIMIT_REACHED":
                outcome = ExecutionOutcome.FATIGUE_GUARDRAIL_BLOCKED
            elif err == "DURATION_EXCEEDED":
                outcome = ExecutionOutcome.DURATION_CAP_EXCEEDED
            else:
                outcome = ExecutionOutcome.INVALID_ARGUMENT
        elif result.get("conflict_detected"):
            outcome = ExecutionOutcome.CONFLICT_DETECTED

        structured_logger.info(
            f"Court training proposal evaluated: success={result.get('success', False)}",
            intent=AgentIntent.PROPOSE_TRAINING,
            outcome=outcome,
            target_persona="gor",
            duration_ms=duration_ms,
            metadata=PIIRedactor.redact(
                {
                    "date": training_date,
                    "slot": f"{start_time} ({duration_minutes}m)",
                    "error_code": result.get("error_code"),
                    "conflict": result.get("conflict_detected", False),
                }
            ),
            component="sports_science_engine",
        )
        return result


def approve_pending_proposal() -> dict[str, Any]:
    """Approve and commit the active pending proposal (e.g. Gor's training booking or override).

    Downstream cascading bookings (such as Ma's workout or assisted PR rescheduling)
    are automatically triggered and committed to the team calendar.

    Returns:
        Confirmation dictionary with booking details and notifications.
    """
    t0 = time.perf_counter()
    with trace_span(
        "tool.approve_pending_proposal",
        component="sports_science_engine",
    ):
        result = calendar_store.approve_pending_proposal()
        duration_ms = (time.perf_counter() - t0) * 1000

        is_override = "override" in str(result.get("message", "")).lower()
        outcome = ExecutionOutcome.OVERRIDE_APPROVED if is_override else ExecutionOutcome.SUCCESS

        structured_logger.info(
            f"Proposal approval processed: {result.get('status', 'PROCESSED')}",
            intent=AgentIntent.APPROVE_PROPOSAL,
            outcome=outcome,
            target_persona="gor",
            duration_ms=duration_ms,
            metadata=PIIRedactor.redact(result),
            component="sports_science_engine",
        )
        return result


def reject_pending_proposal() -> dict[str, Any]:
    """Reject and cancel the current pending proposal without altering the calendar.

    Returns:
        Cancellation confirmation dictionary.
    """
    t0 = time.perf_counter()
    with trace_span(
        "tool.reject_pending_proposal",
        component="sports_science_engine",
    ):
        result = calendar_store.reject_pending_proposal()
        duration_ms = (time.perf_counter() - t0) * 1000

        structured_logger.info(
            "Pending proposal rejected by user",
            intent=AgentIntent.REJECT_PROPOSAL,
            outcome=ExecutionOutcome.OVERRIDE_REJECTED,
            target_persona="gor",
            duration_ms=duration_ms,
            metadata=PIIRedactor.redact(result),
            component="sports_science_engine",
        )
        return result


def book_pr_activity(
    event_date: str,
    start_time: str,
    end_time: str,
    title: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """Book a PR, sponsor, or media session for Personal Assistant Beita.

    Enforces:
    1. Allowed strictly between 10:00 AM and 6:00 PM.
    2. Prohibited before court training on the same day.
    3. Prohibited on official game days and the day immediately before a game day.
    4. Can be overridden by higher-priority court training sessions.

    Args:
        event_date: Date in YYYY-MM-DD format (e.g. '2026-09-02').
        start_time: Start time in HH:MM format (e.g. '16:30').
        end_time: End time in HH:MM format (e.g. '17:30').
        title: Title of the PR/sponsor activity.
        notes: Optional details or sponsor requirements.

    Returns:
        Confirmation dict with booking details, or rejection reason with suggested alternative slots.
    """
    t0 = time.perf_counter()
    with trace_span(
        "tool.book_pr_activity",
        attributes={
            "event_date": event_date,
            "slot": f"{start_time}-{end_time}",
            "title": PIIRedactor.redact_text(title),
        },
        component="sports_science_engine",
    ):
        result = calendar_store.book_pr_event(
            event_date=event_date,
            start_time=start_time,
            end_time=end_time,
            title=title,
            notes=notes,
        )
        duration_ms = (time.perf_counter() - t0) * 1000

        outcome = ExecutionOutcome.SUCCESS
        if not result.get("success", False):
            err = result.get("error_code")
            if err == "PR_BEFORE_TRAINING_PROHIBITED":
                outcome = ExecutionOutcome.PR_BEFORE_TRAINING_BLOCKED
            elif err == "GAME_DAY_PR_PROHIBITED":
                outcome = ExecutionOutcome.GAME_DAY_PR_PROHIBITED
            else:
                outcome = ExecutionOutcome.INVALID_ARGUMENT

        structured_logger.info(
            f"PR activity booking evaluated: success={result.get('success', False)}",
            intent=AgentIntent.BOOK_PR_ACTIVITY,
            outcome=outcome,
            target_persona="beita",
            duration_ms=duration_ms,
            metadata=PIIRedactor.redact(result),
            component="sports_science_engine",
        )
        return result


def book_opponent_tactical_analysis(
    analysis_date: str,
    start_time: str = "10:30",
    end_time: str = "11:30",
    opponent: str = "Sofia Kenin",
    tactical_notes: str | None = None,
) -> dict[str, Any]:
    """Book an opponent tactical scouting and video analysis session for Coach II Sai.

    Enforces:
    1. Allowed strictly on the day immediately preceding an official tournament match.
    2. Calendar-blocking 60-minute session involving Gina, Gor, and Sai.

    Args:
        analysis_date: Date in YYYY-MM-DD format (e.g. '2026-09-03').
        start_time: Start time in HH:MM format (default: '10:30').
        end_time: End time in HH:MM format (default: '11:30').
        opponent: Opponent player name (e.g. 'Sofia Kenin').
        tactical_notes: Opponent tendencies, serve directions, break point plans.

    Returns:
        Confirmation dict with scouting session details.
    """
    t0 = time.perf_counter()
    with trace_span(
        "tool.book_opponent_tactical_analysis",
        attributes={
            "analysis_date": analysis_date,
            "slot": f"{start_time}-{end_time}",
            "opponent": opponent,
        },
        component="sports_science_engine",
    ):
        result = calendar_store.book_opponent_analysis(
            analysis_date=analysis_date,
            start_time=start_time,
            end_time=end_time,
            opponent=opponent,
            tactical_notes=tactical_notes,
        )
        duration_ms = (time.perf_counter() - t0) * 1000

        structured_logger.info(
            f"Opponent tactical analysis booked for opponent {opponent}",
            intent=AgentIntent.SCOUT_OPPONENT,
            outcome=ExecutionOutcome.SUCCESS,
            target_persona="sai",
            duration_ms=duration_ms,
            metadata=PIIRedactor.redact(result),
            component="sports_science_engine",
        )
        return result


def set_workout_syllabus(workout_date: str, syllabus: str) -> dict[str, Any]:
    """Attach the physical therapy and conditioning syllabus for Physical Therapist Ma.

    Updates the auto-coupled pre-training workout session.

    Args:
        workout_date: Date in YYYY-MM-DD format (e.g. '2026-09-02').
        syllabus: Description of exercises, mobility work, or physical therapy focus.

    Returns:
        Confirmation dict with updated workout details.
    """
    t0 = time.perf_counter()
    with trace_span(
        "tool.set_workout_syllabus",
        attributes={
            "workout_date": workout_date,
            "syllabus": PIIRedactor.redact_text(syllabus),
        },
        component="sports_science_engine",
    ):
        result = calendar_store.update_workout_syllabus(workout_date, syllabus)
        duration_ms = (time.perf_counter() - t0) * 1000

        structured_logger.info(
            f"Workout syllabus attached for {workout_date}",
            intent=AgentIntent.ATTACH_WORKOUT_SYLLABUS,
            outcome=ExecutionOutcome.SUCCESS,
            target_persona="ma",
            duration_ms=duration_ms,
            metadata=PIIRedactor.redact(result),
            component="sports_science_engine",
        )
        return result


def order_daily_meals(
    meal_date: str,
    breakfast: list[str],
    lunch: list[str],
    dinner: list[str],
) -> dict[str, Any]:
    """Record nutritional menus and trigger mock food delivery for Physical Therapist Ma.

    Args:
        meal_date: Date in YYYY-MM-DD format (e.g. '2026-09-02').
        breakfast: List of breakfast dishes/items.
        lunch: List of lunch dishes/items.
        dinner: List of dinner dishes/items.

    Returns:
        Order confirmation dict with generated order ID and status.
    """
    t0 = time.perf_counter()
    with trace_span(
        "tool.order_daily_meals",
        attributes={"meal_date": meal_date},
        component="sports_science_engine",
    ):
        result = calendar_store.record_meal_plan(
            meal_date=meal_date,
            breakfast_items=breakfast,
            lunch_items=lunch,
            dinner_items=dinner,
        )
        duration_ms = (time.perf_counter() - t0) * 1000

        structured_logger.info(
            f"Meal plan & food order dispatched: {result.get('order_id')}",
            intent=AgentIntent.ORDER_MEALS,
            outcome=ExecutionOutcome.SUCCESS,
            target_persona="ma",
            duration_ms=duration_ms,
            metadata=PIIRedactor.redact(result),
            component="sports_science_engine",
        )
        return result


def query_team_memory(query: str = "Gina preferences") -> str:
    """Query long-term athlete facts, dietary preferences, coaching guidelines, and sponsor rules.

    Args:
        query: Search keywords (e.g. 'dietary preference', 'recovery', 'court', 'sponsor').

    Returns:
        Relevant knowledge entries from the team's long-term memory bank.
    """
    t0 = time.perf_counter()
    with trace_span(
        "tool.query_team_memory",
        attributes={"query": PIIRedactor.redact_text(query)},
        component="memory_bank",
    ):
        from app.sessions import team_memory_bank

        result = team_memory_bank.format_memories_prompt(query)
        duration_ms = (time.perf_counter() - t0) * 1000

        structured_logger.info(
            "Long-term team memory queried",
            intent=AgentIntent.QUERY_TEAM_MEMORY,
            outcome=ExecutionOutcome.SUCCESS,
            target_persona="coordinator",
            duration_ms=duration_ms,
            metadata={"query_length": len(query), "matches_length": len(result)},
            component="memory_bank",
        )
        return result


def reset_store_state() -> dict[str, str]:
    """Reset the CalendarStore to the initial pre-seeded tournament simulation state."""
    with trace_span("tool.reset_store_state", component="sports_science_engine"):
        calendar_store.seed()
        structured_logger.audit(
            event_name="calendar_store_reset",
            intent=AgentIntent.GENERAL_CONVERSATION,
            outcome=ExecutionOutcome.SUCCESS,
            actor="test_runner",
            details={"initial_seed_date": "2026-09-01"},
        )
        return {
            "status": "SUCCESS",
            "message": "Simulation calendar state successfully reset to seed.",
        }

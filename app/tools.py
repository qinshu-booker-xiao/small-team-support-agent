"""ADK 2.0 Function Tools wrapping the deterministic engine.

Exposes clean, type-annotated tool functions for the ADK agents to invoke.
"""

from typing import Any, Dict, List, Optional
from app.engine import calendar_store


def get_daily_schedule(target_date: str = "2026-09-02") -> str:
    """Fetch Gina's complete daily chronological schedule and active 1-hour pre-activity alerts.

    Applies the Sleep Quiet Hours policy (22:00 - 07:30), silencing early morning alarms.

    Args:
        target_date: Date in YYYY-MM-DD format (default: '2026-09-02').

    Returns:
        Formatted textual agenda and alerts markdown table.
    """
    return calendar_store.format_daily_agenda_and_alerts(target_date)


def propose_court_training(
    training_date: str,
    start_time: str,
    duration_minutes: int,
    court: str = "Court 3",
    syllabus: Optional[str] = None,
) -> Dict[str, Any]:
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
    return calendar_store.propose_training(
        training_date=training_date,
        start_time=start_time,
        duration_minutes=duration_minutes,
        court=court,
        syllabus=syllabus,
    )


def approve_pending_proposal() -> Dict[str, Any]:
    """Approve and commit the active pending proposal (e.g. Gor's training booking or override).

    Downstream cascading bookings (such as Ma's workout or assisted PR rescheduling)
    are automatically triggered and committed to the team calendar.

    Returns:
        Confirmation dictionary with booking details and notifications.
    """
    return calendar_store.approve_pending_proposal()


def reject_pending_proposal() -> Dict[str, Any]:
    """Reject and cancel the current pending proposal without altering the calendar.

    Returns:
        Cancellation confirmation dictionary.
    """
    return calendar_store.reject_pending_proposal()


def book_pr_activity(
    event_date: str,
    start_time: str,
    end_time: str,
    title: str,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
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
    return calendar_store.book_pr_event(
        event_date=event_date,
        start_time=start_time,
        end_time=end_time,
        title=title,
        notes=notes,
    )


def book_opponent_tactical_analysis(
    analysis_date: str,
    start_time: str = "10:30",
    end_time: str = "11:30",
    opponent: str = "Sofia Kenin",
    tactical_notes: Optional[str] = None,
) -> Dict[str, Any]:
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
    return calendar_store.book_opponent_analysis(
        analysis_date=analysis_date,
        start_time=start_time,
        end_time=end_time,
        opponent=opponent,
        tactical_notes=tactical_notes,
    )


def set_workout_syllabus(workout_date: str, syllabus: str) -> Dict[str, Any]:
    """Attach the physical therapy and conditioning syllabus for Physical Therapist Ma.

    Updates the auto-coupled pre-training workout session.

    Args:
        workout_date: Date in YYYY-MM-DD format (e.g. '2026-09-02').
        syllabus: Description of exercises, mobility work, or physical therapy focus.

    Returns:
        Confirmation dict with updated workout details.
    """
    return calendar_store.update_workout_syllabus(workout_date, syllabus)


def order_daily_meals(
    meal_date: str,
    breakfast: List[str],
    lunch: List[str],
    dinner: List[str],
) -> Dict[str, Any]:
    """Record nutritional menus and trigger mock food delivery for Physical Therapist Ma.

    Args:
        meal_date: Date in YYYY-MM-DD format (e.g. '2026-09-02').
        breakfast: List of breakfast dishes/items.
        lunch: List of lunch dishes/items.
        dinner: List of dinner dishes/items.

    Returns:
        Order confirmation dict with generated order ID and status.
    """
    return calendar_store.record_meal_plan(
        meal_date=meal_date,
        breakfast_items=breakfast,
        lunch_items=lunch,
        dinner_items=dinner,
    )


def query_team_memory(query: str = "Gina preferences") -> str:
    """Query long-term athlete facts, dietary preferences, coaching guidelines, and sponsor rules.

    Args:
        query: Search keywords (e.g. 'dietary preference', 'recovery', 'court', 'sponsor').

    Returns:
        Relevant knowledge entries from the team's long-term memory bank.
    """
    from app.sessions import team_memory_bank
    return team_memory_bank.format_memories_prompt(query)


def reset_store_state() -> Dict[str, str]:
    """Reset the CalendarStore to the initial pre-seeded tournament simulation state."""
    calendar_store.seed()
    return {"status": "SUCCESS", "message": "Simulation calendar state successfully reset to seed."}

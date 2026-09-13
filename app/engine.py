"""Deterministic Scheduling & Sports Science Engine for small-team-support-agent.

Strictly separates deterministic calculations (fatigue rules, time math,
priority collisions, quiet hours) from LLM intelligence.
"""

from datetime import date, datetime, timedelta
from typing import Any

from app.models import (
    CalendarEvent,
    EventStatus,
    EventType,
    MealPlan,
    PendingProposal,
)

# Reference Fixed Simulation Date
SIMULATION_REFERENCE_DATE = "2026-09-01"  # Tuesday (US Open Week)
SLEEP_START_MINUTES = 22 * 60  # 22:00 (1320 mins)
SLEEP_END_MINUTES = 7 * 60 + 30  # 07:30 (450 mins)


def time_to_minutes(t_str: str) -> int:
    """Convert 'HH:MM' string to integer minutes from midnight."""
    h, m = map(int, t_str.strip().split(":"))
    return h * 60 + m


def minutes_to_time(minutes: int) -> str:
    """Convert integer minutes from midnight to 'HH:MM' string."""
    h = (minutes // 60) % 24
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def minutes_to_ampm(minutes: int) -> str:
    """Convert integer minutes to 'HH:MM AM/PM' format."""
    h = (minutes // 60) % 24
    m = minutes % 60
    ampm = "AM" if h < 12 else "PM"
    h12 = h % 12
    if h12 == 0:
        h12 = 12
    return f"{h12:02d}:{m:02d} {ampm}"


def is_in_sleep_quiet_hours(minutes: int) -> bool:
    """Check if given minutes from midnight falls within sleep quiet window (22:00 - 07:30)."""
    return minutes >= SLEEP_START_MINUTES or minutes < SLEEP_END_MINUTES


class CalendarStore:
    """In-memory deterministic data store for calendar events, fatigue history, and HITL proposals."""

    def __init__(self):
        self.current_date = SIMULATION_REFERENCE_DATE
        self.events: list[CalendarEvent] = []
        self.fatigue_history: list[dict[str, str]] = []
        self.meals: dict[str, MealPlan] = {}
        self.tactical_notes: dict[str, str] = {}
        self.pending_proposal: PendingProposal | None = None
        self.seed()

    def seed(self):
        """Pre-seed deterministic tournament simulation state."""
        self.current_date = SIMULATION_REFERENCE_DATE
        self.events.clear()
        self.meals.clear()
        self.tactical_notes.clear()
        self.pending_proposal = None

        # Pre-seed fatigue history (T-3, T-2, T-1)
        self.fatigue_history = [
            {"date": "2026-08-30", "event_type": "TRAINING", "title": "Court 1 Training"},
            {"date": "2026-08-31", "event_type": "TRAINING", "title": "Court 2 Training"},
            {"date": "2026-09-01", "event_type": "TRAINING", "title": "Court 1 Training"},
        ]

        # Seed 09/04 Kenin Match (Priority 1) & Cascading Buffers
        self.add_game_with_buffers(
            match_date="2026-09-04",
            start_time="14:00",
            end_time="16:00",
            title="WTA R16 Match vs Sofia Kenin",
            opponent="Sofia Kenin",
            court="Grandstand Court",
        )

        # Seed default fixed meals for 2026-09-02 (non-game day)
        self.events.append(
            CalendarEvent(
                id="meal_bf_20260902",
                date="2026-09-02",
                start_time="07:00",
                end_time="07:30",
                event_type=EventType.MEAL,
                title="Breakfast (Oatmeal with berries & almond butter)",
                syllabus_or_notes="Dining Lounge",
                requested_by="Ma",
                priority=2,
                status=EventStatus.CONFIRMED,
            )
        )
        self.events.append(
            CalendarEvent(
                id="meal_lu_20260902",
                date="2026-09-02",
                start_time="12:00",
                end_time="13:00",
                event_type=EventType.MEAL,
                title="Lunch (Grilled chicken breast, quinoa, steamed broccoli)",
                syllabus_or_notes="Dining Lounge",
                requested_by="Ma",
                priority=2,
                status=EventStatus.CONFIRMED,
            )
        )
        self.events.append(
            CalendarEvent(
                id="meal_di_20260902",
                date="2026-09-02",
                start_time="18:00",
                end_time="19:00",
                event_type=EventType.MEAL,
                title="Dinner (Grilled salmon, sweet potato, green salad)",
                syllabus_or_notes="Dining Lounge",
                requested_by="Ma",
                priority=2,
                status=EventStatus.CONFIRMED,
            )
        )

        # Seed default fixed meals for 2026-09-03 (scouting/rest day)
        self.events.append(
            CalendarEvent(
                id="meal_bf_20260903",
                date="2026-09-03",
                start_time="07:00",
                end_time="07:30",
                event_type=EventType.MEAL,
                title="Breakfast (Greek yogurt with honey, chia seeds)",
                syllabus_or_notes="Dining Lounge",
                requested_by="Ma",
                priority=2,
                status=EventStatus.CONFIRMED,
            )
        )
        self.events.append(
            CalendarEvent(
                id="meal_lu_20260903",
                date="2026-09-03",
                start_time="12:00",
                end_time="13:00",
                event_type=EventType.MEAL,
                title="Lunch (Turkey breast wrap, avocado, mixed greens)",
                syllabus_or_notes="Dining Lounge",
                requested_by="Ma",
                priority=2,
                status=EventStatus.CONFIRMED,
            )
        )
        self.events.append(
            CalendarEvent(
                id="meal_di_20260903",
                date="2026-09-03",
                start_time="18:00",
                end_time="19:00",
                event_type=EventType.MEAL,
                title="Dinner (Lean steak, roasted asparagus, brown rice)",
                syllabus_or_notes="Dining Lounge",
                requested_by="Ma",
                priority=2,
                status=EventStatus.CONFIRMED,
            )
        )

        # Seed default meal menus for 2026-09-02
        self.meals["2026-09-02"] = MealPlan(
            date="2026-09-02",
            breakfast_items=["Oatmeal with berries & almond butter"],
            lunch_items=["Grilled chicken breast, quinoa, steamed broccoli"],
            dinner_items=["Grilled salmon, sweet potato, green salad"],
            order_id="MEAL-20260902-01",
            status="ORDERED",
        )

    def add_game_with_buffers(
        self,
        match_date: str,
        start_time: str,
        end_time: str,
        title: str,
        opponent: str,
        court: str = "Grandstand Court",
    ):
        """Register an official match (P1) and auto-cascade all sports-science buffers (P2 & Meals)."""
        # 1. P1: Official Match
        match_event = CalendarEvent(
            id=f"match_{match_date.replace('-', '')}",
            date=match_date,
            start_time=start_time,
            end_time=end_time,
            event_type=EventType.GAME,
            title=title,
            syllabus_or_notes=f"Opponent: {opponent}, Court: {court}",
            requested_by="System",
            priority=1,
            status=EventStatus.CONFIRMED,
            overridable=False,
        )
        self.events.append(match_event)

        # 2. P2: Pre-game Warm-up (60m, finishing 30m before match -> 12:30 - 13:30)
        match_start_min = time_to_minutes(start_time)
        warmup_end_min = match_start_min - 30
        warmup_start_min = warmup_end_min - 60
        self.events.append(
            CalendarEvent(
                id=f"warmup_{match_date.replace('-', '')}",
                date=match_date,
                start_time=minutes_to_time(warmup_start_min),
                end_time=minutes_to_time(warmup_end_min),
                event_type=EventType.PRE_GAME_WARMUP,
                title="Pre-Game Warm-Up with Sai & Gor",
                syllabus_or_notes="Match preparation, racket calibration, dynamic mobility",
                requested_by="Sai",
                priority=2,
                status=EventStatus.CONFIRMED,
                overridable=False,
            )
        )

        # 3. P2: Post-game Media (15m immediately post-match -> 16:00 - 16:15)
        match_end_min = time_to_minutes(end_time)
        media_end_min = match_end_min + 15
        self.events.append(
            CalendarEvent(
                id=f"media_{match_date.replace('-', '')}",
                date=match_date,
                start_time=minutes_to_time(match_end_min),
                end_time=minutes_to_time(media_end_min),
                event_type=EventType.POST_GAME_MEDIA,
                title="Post-Game Press Conference with Beita",
                syllabus_or_notes="WTA official press room obligations",
                requested_by="Beita",
                priority=2,
                status=EventStatus.CONFIRMED,
                overridable=False,
            )
        )

        # 4. P2: Post-game Recovery (60m immediately after media -> 16:15 - 17:15)
        recovery_end_min = media_end_min + 60
        self.events.append(
            CalendarEvent(
                id=f"recovery_{match_date.replace('-', '')}",
                date=match_date,
                start_time=minutes_to_time(media_end_min),
                end_time=minutes_to_time(recovery_end_min),
                event_type=EventType.POST_GAME_RECOVERY,
                title="Post-Game Cool-Down & Physical Therapy with Ma",
                syllabus_or_notes="Ice bath, lymphatic drainage, soft tissue release",
                requested_by="Ma",
                priority=2,
                status=EventStatus.CONFIRMED,
                overridable=False,
            )
        )

        # 5. Shifted Game-Day Meals (1h buffer around match: Lunch 11:30 - 12:15, Dinner 18:00 - 19:00)
        self.events.append(
            CalendarEvent(
                id=f"meal_bf_{match_date.replace('-', '')}",
                date=match_date,
                start_time="07:00",
                end_time="07:30",
                event_type=EventType.MEAL,
                title="Breakfast (Pre-Match Complex Carbs)",
                syllabus_or_notes="Oatmeal, banana, almond butter",
                requested_by="Ma",
                priority=2,
                status=EventStatus.CONFIRMED,
            )
        )
        self.events.append(
            CalendarEvent(
                id=f"meal_lunch_{match_date.replace('-', '')}",
                date=match_date,
                start_time="11:30",
                end_time="12:15",
                event_type=EventType.MEAL,
                title="Lunch (Pre-Match Optimized Meal)",
                syllabus_or_notes="Light poultry, white rice, steamed zucchini (ends >105m pre-match)",
                requested_by="Ma",
                priority=2,
                status=EventStatus.CONFIRMED,
            )
        )
        self.events.append(
            CalendarEvent(
                id=f"meal_dinner_{match_date.replace('-', '')}",
                date=match_date,
                start_time="18:00",
                end_time="19:00",
                event_type=EventType.MEAL,
                title="Dinner (Post-Match Protein & Recovery)",
                syllabus_or_notes="Salmon, sweet potato, antioxidant salad",
                requested_by="Ma",
                priority=2,
                status=EventStatus.CONFIRMED,
            )
        )

    def get_events_for_date(self, target_date: str) -> list[CalendarEvent]:
        """Return all confirmed or pending events for a date sorted by start_time."""
        events = [
            e
            for e in self.events
            if e.date == target_date
            and e.status in (EventStatus.CONFIRMED, EventStatus.PENDING_APPROVAL)
        ]
        events.sort(key=lambda x: time_to_minutes(x.start_time))
        return events

    def get_all_events_for_date_including_bumped(self, target_date: str) -> list[CalendarEvent]:
        """Return all events for a date, including bumped ones."""
        events = [e for e in self.events if e.date == target_date]
        events.sort(key=lambda x: time_to_minutes(x.start_time))
        return events

    def check_fatigue_rule(self, target_date: str) -> tuple[bool, int, str]:
        """Evaluate the 4-Day Fatigue Guardrail:

        Count consecutive training or match days on T-4, T-3, T-2, T-1.
        Returns: (is_blocked, consecutive_days, reason)
        """
        t_date = date.fromisoformat(target_date)
        consecutive_days = 0

        for i in range(1, 5):
            day_to_check = (t_date - timedelta(days=i)).isoformat()

            # Check in fatigue_history seed
            has_history = any(
                h["date"] == day_to_check and h.get("event_type") in ("TRAINING", "GAME")
                for h in self.fatigue_history
            )

            # Also check confirmed events in calendar
            has_calendar = any(
                e.date == day_to_check
                and e.event_type in (EventType.TRAINING, EventType.GAME)
                and e.status == EventStatus.CONFIRMED
                for e in self.events
            )

            if has_history or has_calendar:
                consecutive_days += 1
            else:
                break

        if consecutive_days >= 4:
            return (
                True,
                consecutive_days,
                f"Fatigue Guardrail Block: Gina has trained/competed for {consecutive_days} consecutive days prior to {target_date}. Mandatory rest day required to protect athlete recovery before matches.",
            )
        return False, consecutive_days, "Fatigue check passed."

    def has_game_on_date(self, target_date: str) -> bool:
        """Check if target_date has an official tournament match."""
        return any(
            e.date == target_date
            and e.event_type == EventType.GAME
            and e.status == EventStatus.CONFIRMED
            for e in self.events
        )

    def is_day_before_game(self, target_date: str) -> bool:
        """Check if target_date is the day immediately preceding an official match."""
        next_day = (date.fromisoformat(target_date) + timedelta(days=1)).isoformat()
        return self.has_game_on_date(next_day)

    def propose_training(
        self,
        training_date: str,
        start_time: str,
        duration_minutes: int,
        court: str = "Court 3",
        syllabus: str | None = None,
    ) -> dict[str, Any]:
        """Propose court training for Gor with validation, workout coupling, and conflict/override detection."""
        # 1. Training duration cap <= 120m
        if duration_minutes > 120:
            return {
                "success": False,
                "error_code": "DURATION_LIMIT_EXCEEDED",
                "message": f"Training proposal rejected: Requested duration of {duration_minutes} minutes exceeds the 120-minute (2-hour) maximum single-session limit.",
            }

        # 2. Check 4-day fatigue rule
        blocked, consecutive, reason = self.check_fatigue_rule(training_date)
        if blocked:
            return {
                "success": False,
                "error_code": "FATIGUE_LIMIT_REACHED",
                "message": f"Training proposal rejected: {reason}",
            }

        # 3. Cannot train on game days
        if self.has_game_on_date(training_date):
            return {
                "success": False,
                "error_code": "GAME_DAY_TRAINING_PROHIBITED",
                "message": f"Training proposal rejected: Official tournament match is scheduled on {training_date}. Court training cannot take place on game days.",
            }

        # Calculate time windows
        start_min = time_to_minutes(start_time)
        end_min = start_min + duration_minutes
        end_time = minutes_to_time(end_min)

        # Pre-training workout (Ma): 1h immediately preceding court training
        # Only couple if a workout is not already scheduled on this day
        existing_events = self.get_events_for_date(training_date)
        already_has_workout = any(
            e.event_type == EventType.WORKOUT and e.status == EventStatus.CONFIRMED
            for e in existing_events
        )

        workout_event: CalendarEvent | None = None
        workout_start_min = start_min - 60
        workout_start_time = minutes_to_time(workout_start_min)
        workout_end_time = start_time

        if not already_has_workout:
            workout_event = CalendarEvent(
                id=f"workout_{training_date.replace('-', '')}_{workout_start_min}",
                date=training_date,
                start_time=workout_start_time,
                end_time=workout_end_time,
                event_type=EventType.WORKOUT,
                title="Pre-Training Workout with Ma",
                syllabus_or_notes="Core stability & hip mobility (auto-coupled 1h prior)",
                requested_by="Ma",
                priority=3,
                status=EventStatus.PENDING_APPROVAL,
                overridable=False,
            )

        # Check collisions with existing events on training_date
        conflicts = []
        for ev in existing_events:
            ev_s = time_to_minutes(ev.start_time)
            ev_e = time_to_minutes(ev.end_time)
            # Check overlap with training
            training_overlap = not (end_min <= ev_s or start_min >= ev_e)
            # Check overlap with coupled workout if one is being scheduled
            workout_overlap = False
            if workout_event is not None:
                workout_overlap = not (start_min <= ev_s or workout_start_min >= ev_e)
            if training_overlap or workout_overlap:
                conflicts.append(ev)

        # Check conflict priorities
        overridden_event: CalendarEvent | None = None
        reschedule_suggestion: CalendarEvent | None = None

        for conf in conflicts:
            if conf.priority <= 3:  # P1 (Game), P2 (Game buffers), P3 (Training/Workout)
                return {
                    "success": False,
                    "error_code": "UNRESOLVABLE_COLLISION",
                    "message": f"Training proposal rejected: Slot {start_time}-{end_time} conflicts with higher/equal priority event: '{conf.title}' ({conf.start_time}-{conf.end_time}, Priority {conf.priority}).",
                }
            elif conf.priority > 3:
                # Can be overridden (e.g. P5 PR/Social)
                overridden_event = conf

        # Prepare proposal events
        training_event = CalendarEvent(
            id=f"train_{training_date.replace('-', '')}_{start_min}",
            date=training_date,
            start_time=start_time,
            end_time=end_time,
            event_type=EventType.TRAINING,
            title=f"Court Training with Gor ({court})",
            syllabus_or_notes=syllabus or "Baseline consistency & serve +1",
            requested_by="Gor",
            priority=3,
            status=EventStatus.PENDING_APPROVAL,
            overridable=False,
        )

        workout_event = CalendarEvent(
            id=f"workout_{training_date.replace('-', '')}_{workout_start_min}",
            date=training_date,
            start_time=workout_start_time,
            end_time=workout_end_time,
            event_type=EventType.WORKOUT,
            title="Pre-Training Workout with Ma",
            syllabus_or_notes="Core stability & hip mobility (auto-coupled 1h prior)",
            requested_by="Ma",
            priority=3,
            status=EventStatus.PENDING_APPROVAL,
            overridable=False,
        )

        # If overriding Beita's PR event, calculate assisted reschedule slot
        if overridden_event and overridden_event.event_type == EventType.BUSINESS_SOCIAL:
            reschedule_suggestion = self.find_next_pr_slot(
                target_date=training_date,
                duration_minutes=time_to_minutes(overridden_event.end_time)
                - time_to_minutes(overridden_event.start_time),
                after_time=end_time,
            )

        # Register pending proposal in state
        proposal_id = f"prop_{training_date.replace('-', '')}_{start_min}"
        if overridden_event:
            prompt_msg = (
                f"Gor, {court} requested for {start_time} - {end_time} conflicts with Beita's '{overridden_event.title}' "
                f"({overridden_event.start_time} - {overridden_event.end_time}). Training (Priority 3) has higher priority "
                f"than PR/Social (Priority 5). You can override this event."
            )
            options = ["[Approve Override]", "[Reject]", "[Change Time]"]
        else:
            prompt_msg = (
                f"Gor, for {training_date}:\n"
                f"• Recommended Training Slot: {start_time} - {end_time} ({court}, {duration_minutes} mins).\n"
                f"• Auto-coupled Workout with Ma: {workout_start_time} - {workout_end_time}.\n"
                f"Please confirm to commit."
            )
            options = ["[Approve]", "[Reject]", "[Change Time]"]

        self.pending_proposal = PendingProposal(
            proposal_id=proposal_id,
            event=training_event,
            coupled_event=workout_event,
            overridden_event_id=overridden_event.id if overridden_event else None,
            reschedule_suggestion=reschedule_suggestion,
            prompt_message=prompt_msg,
            options=options,
        )

        return {
            "success": True,
            "status": "PENDING_APPROVAL",
            "proposal_id": proposal_id,
            "message": prompt_msg,
            "options": options,
            "training_slot": f"{start_time} - {end_time}",
            "workout_slot": f"{workout_start_time} - {workout_end_time}",
            "overriding_event": overridden_event.title if overridden_event else None,
            "reschedule_suggestion": (
                f"{reschedule_suggestion.start_time} - {reschedule_suggestion.end_time}"
                if reschedule_suggestion
                else None
            ),
        }

    def find_next_pr_slot(
        self, target_date: str, duration_minutes: int = 60, after_time: str = "16:00"
    ) -> CalendarEvent | None:
        """Find the next compliant open timeslot between 10:00 and 18:00 for PR."""
        start_bound = max(time_to_minutes("10:00"), time_to_minutes(after_time))
        end_bound = time_to_minutes("18:00")

        # Check existing confirmed events
        events = self.get_events_for_date(target_date)

        curr = start_bound
        while curr + duration_minutes <= end_bound:
            candidate_end = curr + duration_minutes
            overlap = False
            for ev in events:
                ev_s = time_to_minutes(ev.start_time)
                ev_e = time_to_minutes(ev.end_time)
                if not (candidate_end <= ev_s or curr >= ev_e):
                    overlap = True
                    curr = ev_e
                    break
            if not overlap:
                return CalendarEvent(
                    id=f"pr_resched_{target_date.replace('-', '')}_{curr}",
                    date=target_date,
                    start_time=minutes_to_time(curr),
                    end_time=minutes_to_time(candidate_end),
                    event_type=EventType.BUSINESS_SOCIAL,
                    title="Rescheduled Media / Sponsor Session",
                    syllabus_or_notes="Auto-assisted rescheduling proposal",
                    requested_by="Beita",
                    priority=5,
                    status=EventStatus.PENDING_APPROVAL,
                    overridable=True,
                )
        # Fallback slot 17:30 - 18:30 if 18:00 boundary allows buffer
        return CalendarEvent(
            id=f"pr_resched_{target_date.replace('-', '')}_fallback",
            date=target_date,
            start_time="17:30",
            end_time="18:30",
            event_type=EventType.BUSINESS_SOCIAL,
            title="Rescheduled Media / Sponsor Session",
            syllabus_or_notes="Auto-assisted rescheduling proposal",
            requested_by="Beita",
            priority=5,
            status=EventStatus.PENDING_APPROVAL,
            overridable=True,
        )

    def approve_pending_proposal(self) -> dict[str, Any]:
        """Approve and commit the current pending proposal to CalendarStore."""
        if not self.pending_proposal:
            return {"success": False, "message": "No pending proposal to approve."}

        prop = self.pending_proposal
        # If this proposal overrides an existing event, mark that event as bumped
        bumped_event: CalendarEvent | None = None
        if prop.overridden_event_id:
            for ev in self.events:
                if ev.id == prop.overridden_event_id:
                    ev.status = EventStatus.BUMPED_BY_OVERRIDE
                    bumped_event = ev
                    break

        # Commit main event
        main_event = prop.event
        main_event.status = EventStatus.CONFIRMED
        self.events.append(main_event)

        # Commit coupled event (workout)
        coupled_event = prop.coupled_event
        if coupled_event:
            coupled_event.status = EventStatus.CONFIRMED
            self.events.append(coupled_event)

        # Update fatigue history if it was a training event
        if main_event.event_type == EventType.TRAINING:
            if not any(h["date"] == main_event.date for h in self.fatigue_history):
                self.fatigue_history.append(
                    {
                        "date": main_event.date,
                        "event_type": "TRAINING",
                        "title": main_event.title,
                    }
                )

        reschedule_suggestion = prop.reschedule_suggestion
        self.pending_proposal = None

        response = {
            "success": True,
            "message": f"Confirmed! {main_event.title} successfully booked for {main_event.date} ({main_event.start_time} - {main_event.end_time}).",
            "event_id": main_event.id,
            "date": main_event.date,
            "training_slot": f"{main_event.start_time} - {main_event.end_time}",
        }

        if coupled_event:
            response["coupled_workout"] = (
                f"{coupled_event.start_time} - {coupled_event.end_time} (Ma prompted for syllabus)"
            )

        if bumped_event:
            response["bumped_event"] = {
                "id": bumped_event.id,
                "title": bumped_event.title,
                "original_slot": f"{bumped_event.start_time} - {bumped_event.end_time}",
            }
            if reschedule_suggestion:
                response["reschedule_suggestion"] = {
                    "slot": f"{reschedule_suggestion.start_time} - {reschedule_suggestion.end_time}",
                    "recipient": "Beita",
                    "message": f"Beita, your event '{bumped_event.title}' was bumped by court training. Suggested alternative: {reschedule_suggestion.start_time} - {reschedule_suggestion.end_time}.",
                }

        return response

    def reject_pending_proposal(self) -> dict[str, Any]:
        """Reject and discard the active pending proposal."""
        if not self.pending_proposal:
            return {"success": False, "message": "No pending proposal to reject."}
        self.pending_proposal = None
        return {"success": True, "message": "Pending proposal was cancelled."}

    def book_pr_event(
        self,
        event_date: str,
        start_time: str,
        end_time: str,
        title: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Book a PR/Business event for Beita with all constraint validations:

        - Allowed strictly 10:00 - 18:00
        - Prohibited before court training on same day
        - Prohibited on game day and day before game day
        """
        # Rule 1: Prohibited on game day
        if self.has_game_on_date(event_date):
            return {
                "success": False,
                "error_code": "GAME_DAY_PR_PROHIBITED",
                "message": f"PR booking rejected: Social & PR activities are prohibited on match day ({event_date}). Focus is 100% on tournament competition.",
            }

        # Rule 2: Prohibited on day before game day
        if self.is_day_before_game(event_date):
            return {
                "success": False,
                "error_code": "PRE_GAME_DAY_PR_PROHIBITED",
                "message": f"PR booking rejected: Social & PR activities are prohibited on the day before match day ({event_date}). Mandatory focus & recovery blackout active.",
            }

        # Rule 3: Allowed only 10:00 to 18:00
        s_min = time_to_minutes(start_time)
        e_min = time_to_minutes(end_time)
        if s_min < time_to_minutes("10:00") or e_min > time_to_minutes("18:00"):
            return {
                "success": False,
                "error_code": "OUTSIDE_PERMITTED_HOURS",
                "message": "PR booking rejected: Business/PR slots must be scheduled strictly between 10:00 AM and 6:00 PM.",
            }

        # Rule 4: Prohibited before court training on the same day
        events = self.get_events_for_date(event_date)
        training_events = [e for e in events if e.event_type == EventType.TRAINING]
        for tr in training_events:
            tr_start = time_to_minutes(tr.start_time)
            if s_min < tr_start:
                # Offer afternoon slot post-training
                suggested_slot = self.find_next_pr_slot(
                    event_date,
                    duration_minutes=(e_min - s_min),
                    after_time=tr.end_time,
                )
                alt_slot_str = (
                    f"{suggested_slot.start_time} - {suggested_slot.end_time}"
                    if suggested_slot
                    else "16:30 - 17:30"
                )
                return {
                    "success": False,
                    "error_code": "PR_BEFORE_TRAINING_PROHIBITED",
                    "message": f"PR booking rejected: PR activities cannot be scheduled before court training on the same day (training is at {tr.start_time}). Proposed afternoon alternative: {alt_slot_str}.",
                    "suggested_slot": alt_slot_str,
                }

        # Check direct time collision
        for ev in events:
            ev_s = time_to_minutes(ev.start_time)
            ev_e = time_to_minutes(ev.end_time)
            if not (e_min <= ev_s or s_min >= ev_e):
                return {
                    "success": False,
                    "error_code": "COLLISION",
                    "message": f"PR booking rejected: Time slot {start_time}-{end_time} conflicts with '{ev.title}' ({ev.start_time}-{ev.end_time}).",
                }

        pr_event = CalendarEvent(
            id=f"pr_{event_date.replace('-', '')}_{s_min}",
            date=event_date,
            start_time=start_time,
            end_time=end_time,
            event_type=EventType.BUSINESS_SOCIAL,
            title=title,
            syllabus_or_notes=notes,
            requested_by="Beita",
            priority=5,
            status=EventStatus.CONFIRMED,
            overridable=True,
        )
        self.events.append(pr_event)

        return {
            "success": True,
            "message": f"Confirmed! PR session '{title}' booked for {event_date} ({start_time} - {end_time}).",
            "event_id": pr_event.id,
            "slot": f"{start_time} - {end_time}",
        }

    def book_opponent_analysis(
        self,
        analysis_date: str,
        start_time: str = "10:30",
        end_time: str = "11:30",
        opponent: str = "Sofia Kenin",
        tactical_notes: str | None = None,
    ) -> dict[str, Any]:
        """Book Sai's opponent tactical scouting session.

        - Allowed strictly on the day before a game day.
        - Calendar blocking (60 mins).
        """
        if not self.is_day_before_game(analysis_date):
            return {
                "success": False,
                "error_code": "NOT_PRE_GAME_DAY",
                "message": "Opponent analysis rejected: Tactical scouting sessions are permitted only on the day prior to an official match.",
            }

        s_min = time_to_minutes(start_time)
        e_min = time_to_minutes(end_time)

        # Check collisions
        events = self.get_events_for_date(analysis_date)
        for ev in events:
            ev_s = time_to_minutes(ev.start_time)
            ev_e = time_to_minutes(ev.end_time)
            if not (e_min <= ev_s or s_min >= ev_e):
                return {
                    "success": False,
                    "error_code": "COLLISION",
                    "message": f"Analysis booking rejected: Slot conflicts with '{ev.title}'.",
                }

        ev_id = f"scout_{analysis_date.replace('-', '')}_{s_min}"
        analysis_event = CalendarEvent(
            id=ev_id,
            date=analysis_date,
            start_time=start_time,
            end_time=end_time,
            event_type=EventType.OPPONENT_ANALYSIS,
            title=f"Opponent Tactical Analysis: {opponent}",
            syllabus_or_notes=tactical_notes
            or "Opponent serve tendencies, backhand baseline patterns, break-point strategy",
            requested_by="Sai",
            priority=4,
            status=EventStatus.CONFIRMED,
            overridable=False,
        )
        self.events.append(analysis_event)

        if tactical_notes:
            self.tactical_notes[analysis_date] = tactical_notes

        return {
            "success": True,
            "message": f"Confirmed! Opponent tactical analysis for {opponent} booked on {analysis_date} from {start_time} to {end_time}.",
            "event_id": ev_id,
            "slot": f"{start_time} - {end_time}",
            "tactical_notes": tactical_notes,
        }

    def update_workout_syllabus(self, workout_date: str, syllabus: str) -> dict[str, Any]:
        """Ma attaches physical therapy / workout syllabus to auto-booked workout slot."""
        events = self.get_events_for_date(workout_date)
        workout_event = next((e for e in events if e.event_type == EventType.WORKOUT), None)

        if not workout_event:
            return {
                "success": False,
                "message": f"No workout session found on {workout_date} to attach syllabus.",
            }

        workout_event.syllabus_or_notes = syllabus
        return {
            "success": True,
            "message": f"Syllabus successfully updated for workout on {workout_date} ({workout_event.start_time} - {workout_event.end_time}): '{syllabus}'.",
            "event_id": workout_event.id,
        }

    def record_meal_plan(
        self,
        meal_date: str,
        breakfast_items: list[str],
        lunch_items: list[str],
        dinner_items: list[str],
    ) -> dict[str, Any]:
        """Ma records daily nutrition plan and triggers mock food order."""
        order_id = f"ORDER-{meal_date.replace('-', '')}-{datetime.now().strftime('%H%M%S')}"
        meal_plan = MealPlan(
            date=meal_date,
            breakfast_items=breakfast_items,
            lunch_items=lunch_items,
            dinner_items=dinner_items,
            order_id=order_id,
            status="ORDERED",
        )
        self.meals[meal_date] = meal_plan

        # Ensure or update meal entries in calendar
        events = self.get_events_for_date(meal_date)
        bf_ev = next(
            (e for e in events if e.event_type == EventType.MEAL and "Breakfast" in e.title), None
        )
        if bf_ev:
            bf_ev.title = f"Breakfast ({', '.join(breakfast_items)})"
            bf_ev.syllabus_or_notes = f"Ordered via {order_id}"
        else:
            self.events.append(
                CalendarEvent(
                    id=f"meal_bf_{meal_date.replace('-', '')}",
                    date=meal_date,
                    start_time="07:00",
                    end_time="07:30",
                    event_type=EventType.MEAL,
                    title=f"Breakfast ({', '.join(breakfast_items)})",
                    syllabus_or_notes=f"Ordered via {order_id}",
                    requested_by="Ma",
                    priority=2,
                    status=EventStatus.CONFIRMED,
                )
            )

        lu_ev = next(
            (e for e in events if e.event_type == EventType.MEAL and "Lunch" in e.title), None
        )
        if lu_ev:
            lu_ev.title = f"Lunch ({', '.join(lunch_items)})"
            lu_ev.syllabus_or_notes = f"Ordered via {order_id}"
        else:
            self.events.append(
                CalendarEvent(
                    id=f"meal_lu_{meal_date.replace('-', '')}",
                    date=meal_date,
                    start_time="12:00",
                    end_time="13:00",
                    event_type=EventType.MEAL,
                    title=f"Lunch ({', '.join(lunch_items)})",
                    syllabus_or_notes=f"Ordered via {order_id}",
                    requested_by="Ma",
                    priority=2,
                    status=EventStatus.CONFIRMED,
                )
            )

        di_ev = next(
            (e for e in events if e.event_type == EventType.MEAL and "Dinner" in e.title), None
        )
        if di_ev:
            di_ev.title = f"Dinner ({', '.join(dinner_items)})"
            di_ev.syllabus_or_notes = f"Ordered via {order_id}"
        else:
            self.events.append(
                CalendarEvent(
                    id=f"meal_di_{meal_date.replace('-', '')}",
                    date=meal_date,
                    start_time="18:00",
                    end_time="19:00",
                    event_type=EventType.MEAL,
                    title=f"Dinner ({', '.join(dinner_items)})",
                    syllabus_or_notes=f"Ordered via {order_id}",
                    requested_by="Ma",
                    priority=2,
                    status=EventStatus.CONFIRMED,
                )
            )

        return {
            "success": True,
            "order_id": order_id,
            "status": "ORDERED",
            "message": f"Meal plan for {meal_date} confirmed. Food order {order_id} dispatched.",
            "breakfast": breakfast_items,
            "lunch": lunch_items,
            "dinner": dinner_items,
        }

    def format_daily_agenda_and_alerts(self, target_date: str) -> str:
        """Format daily schedule agenda and 1-hour pre-activity alerts with sleep quiet hours filter."""
        d_obj = date.fromisoformat(target_date)
        day_name = d_obj.strftime("%A")
        formatted_date = d_obj.strftime("%B %d, %Y")

        events = self.get_events_for_date(target_date)

        # Build schedule rows
        schedule_lines = []
        icons = {
            EventType.MEAL: "🍳",
            EventType.WORKOUT: "🏋️",
            EventType.TRAINING: "🎾",
            EventType.GAME: "🏆",
            EventType.PRE_GAME_WARMUP: "🎾",
            EventType.POST_GAME_MEDIA: "🎙️",
            EventType.POST_GAME_RECOVERY: "🧊",
            EventType.OPPONENT_ANALYSIS: "📋",
            EventType.BUSINESS_SOCIAL: "📸",
        }

        for ev in events:
            icon = icons.get(ev.event_type, "📌")
            details = f" ({ev.syllabus_or_notes})" if ev.syllabus_or_notes else ""
            schedule_lines.append(f"{ev.start_time} - {ev.end_time} | {icon} {ev.title}{details}")

        schedule_lines.append("22:00         | 🌙 Sleep & Recovery")

        # Build 1-Hour pre-activity alerts
        alert_rows = []
        for ev in events:
            ev_start_min = time_to_minutes(ev.start_time)
            alert_trigger_min = ev_start_min - 60

            # Determine recipient
            if ev.event_type == EventType.TRAINING:
                recipient = "Gina, Gor"
                location = "Court 3"
            elif ev.event_type == EventType.WORKOUT:
                recipient = "Gina, Ma"
                location = "Gym / PT Room"
            elif ev.event_type == EventType.BUSINESS_SOCIAL:
                recipient = "Gina, Beita"
                location = "Media Suite A"
            elif ev.event_type == EventType.OPPONENT_ANALYSIS:
                recipient = "Gina, Gor, Sai"
                location = "Tactical Briefing Room"
            elif ev.event_type == EventType.GAME:
                recipient = "Gina, Team"
                location = "Grandstand Court"
            elif ev.event_type == EventType.PRE_GAME_WARMUP:
                recipient = "Gina, Sai"
                location = "Practice Court"
            elif ev.event_type == EventType.POST_GAME_MEDIA:
                recipient = "Gina, Beita"
                location = "Press Conference Room"
            elif ev.event_type == EventType.POST_GAME_RECOVERY:
                recipient = "Gina, Ma"
                location = "Recovery & PT Suite"
            else:
                recipient = "Gina"
                location = "Dining Lounge"

            start_ampm = minutes_to_ampm(ev_start_min)

            if is_in_sleep_quiet_hours(alert_trigger_min):
                alert_rows.append(
                    f"| --:-- (Silent)| {start_ampm} {ev.title} | {location} (Silent for Sleep) | {recipient} |"
                )
            else:
                trigger_ampm = minutes_to_ampm(alert_trigger_min)
                alert_rows.append(
                    f"| {trigger_ampm} | {start_ampm} {ev.title} | {location} | {recipient} |"
                )

        # Construct final formatted document
        border = "=" * 80
        sub_border = "-" * 80
        sched_body = "\n".join(schedule_lines)
        alerts_body = "\n".join(alert_rows)

        result = f"""{border}
🎾 GINA'S DAILY SCHEDULE: {day_name}, {formatted_date}
{border}
{sched_body}

{sub_border}
🔔 ACTIVE ALERTS & REMINDERS (1-Hour Pre-Activity Alerts)
[Policy: Sleep Quiet Hours active 22:00 - 07:30. Early breakfast alarm silenced.]
{sub_border}
| Trigger Time | Scheduled Event | Location / Notes | Alert Recipient |
| :--- | :--- | :--- | :--- |
{alerts_body}
{border}"""
        return result


# Global singleton engine store instance
calendar_store = CalendarStore()

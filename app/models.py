"""Domain models and Pydantic schemas for the small-team-support-agent."""

from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class EventType(str, Enum):
    GAME = "GAME"
    PRE_GAME_WARMUP = "PRE_GAME_WARMUP"
    POST_GAME_MEDIA = "POST_GAME_MEDIA"
    POST_GAME_RECOVERY = "POST_GAME_RECOVERY"
    TRAINING = "TRAINING"
    WORKOUT = "WORKOUT"
    OPPONENT_ANALYSIS = "OPPONENT_ANALYSIS"
    BUSINESS_SOCIAL = "BUSINESS_SOCIAL"
    MEAL = "MEAL"


class EventStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    CONFIRMED = "CONFIRMED"
    BUMPED_BY_OVERRIDE = "BUMPED_BY_OVERRIDE"
    CANCELLED = "CANCELLED"


class CalendarEvent(BaseModel):
    id: str
    date: str  # YYYY-MM-DD
    start_time: str  # HH:MM
    end_time: str  # HH:MM
    event_type: EventType
    title: str
    syllabus_or_notes: Optional[str] = None
    requested_by: str  # Gina, Gor, Sai, Ma, Beita, System
    priority: int  # 1 (Highest) to 5 (Lowest)
    status: EventStatus = EventStatus.CONFIRMED
    overridable: bool = False


class MealPlan(BaseModel):
    date: str
    breakfast_items: List[str]
    lunch_items: List[str]
    dinner_items: List[str]
    order_id: Optional[str] = None
    status: str = "ORDERED"


class PendingProposal(BaseModel):
    proposal_id: str
    event: CalendarEvent
    coupled_event: Optional[CalendarEvent] = None
    overridden_event_id: Optional[str] = None
    reschedule_suggestion: Optional[CalendarEvent] = None
    prompt_message: str
    options: List[str] = Field(default_factory=lambda: ["[Approve]", "[Reject]"])

"""ADK 2.0 Multi-Persona Agent Architecture with Strategic Model Routing.

Defines the Coordinator Agent and Specialist Sub-Agents:
- CoordinatorAgent (gemini-3.6-flash): Triage, persona dispatch, intent routing.
- GorAgent (gemini-3.7-flash): Training proposals, 4-day fatigue, priority overrides.
- SaiAgent (gemini-3.1-pro-preview): Opponent tactical scouting & match analysis.
- MaAgent (gemini-3.6-flash): Pre-training workout syllabus, post-game recovery, meal orders.
- BeitaAgent (gemini-3.6-flash): PR & sponsor bookings, assisted rescheduling.
- GinaAgent (gemini-3.6-flash): Player daily briefing, 1-hour alerts, sleep quiet hours.
"""

import asyncio
import os
import re

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.apps.app import EventsCompactionConfig
from google.adk.runners import Runner
from google.genai import types

from app.sessions import get_session_service
from app.tools import (
    approve_pending_proposal,
    book_opponent_tactical_analysis,
    book_pr_activity,
    get_daily_schedule,
    order_daily_meals,
    propose_court_training,
    query_team_memory,
    reject_pending_proposal,
    set_workout_syllabus,
)

# Load environment variables (.env) if present; in GCP, credentials are provided via ADC or Secret Manager
load_dotenv()

# Strategic Model Routing Configuration
MODEL_COORDINATOR = os.getenv("MODEL_COORDINATOR", "gemini-3.6-flash")
MODEL_GOR = os.getenv("MODEL_GOR", "gemini-3.7-flash")
MODEL_SAI = os.getenv("MODEL_SAI", "gemini-3.1-pro-preview")
MODEL_MA = os.getenv("MODEL_MA", "gemini-3.6-flash")
MODEL_BEITA = os.getenv("MODEL_BEITA", "gemini-3.6-flash")
MODEL_GINA = os.getenv("MODEL_GINA", "gemini-3.6-flash")

# 1. GorAgent: Coach I (Head Coach)
gor_agent = Agent(
    name="gor_agent",
    model=MODEL_GOR,
    description="Head Coach Gor: Responsible for court training curriculum, daily session scheduling, and overrides.",
    instruction="""You are GorAgent, assisting Gor (Head Coach of WTA tennis player Gina).

Your primary responsibilities:
1. Propose court training sessions using `propose_court_training`.
   - The maximum allowed duration is 120 minutes (2 hours). Never exceed 120 minutes.
   - Respect the 4-Day Fatigue Guardrail: if Gina has trained or played 4 consecutive days, training is blocked with mandatory rest.
   - Court training is strictly prohibited on official tournament game days.
   - When proposing training, a 1-hour pre-training workout with PT Ma is automatically coupled immediately preceding the session.
2. Conflict & Priority Overrides:
   - Court Training (Priority 3) has higher priority than PR/Social (Priority 5).
   - If a proposed slot overlaps Beita's PR event, inform Gor of the conflict and provide the override option.
   - When Gor approves (e.g. '[Approve]', '[Approve Override]', 'yes', 'confirm'), call `approve_pending_proposal`.
   - When Gor rejects, call `reject_pending_proposal`.
3. Check the schedule anytime using `get_daily_schedule`.
Always maintain a sharp, authoritative, and direct coaching tone.""",
    tools=[
        propose_court_training,
        approve_pending_proposal,
        reject_pending_proposal,
        get_daily_schedule,
        query_team_memory,
    ],
)

# 2. SaiAgent: Coach II (Tactics & Scouting)
sai_agent = Agent(
    name="sai_agent",
    model=MODEL_SAI,
    description="Tactical Coach Sai: Responsible for opponent scouting, tactical video analysis, and game-day warm-up.",
    instruction="""You are SaiAgent, assisting Sai (Tactical Coach and Scout for WTA player Gina).

Your primary responsibilities:
1. Book opponent tactical analysis and video scouting sessions using `book_opponent_tactical_analysis`.
   - Tactical analysis is calendar-blocking (Gina, Gor, Sai) and is permitted ONLY on the day immediately preceding an official match day.
   - Provide in-depth tactical notes on opponent tendencies (serve directions, backhand vulnerabilities, break-point strategy).
2. Refine game-day pre-match warm-up preparations.
3. Check the schedule using `get_daily_schedule`.
4. Check long-term facts & guidelines using `query_team_memory`.
Always speak with deep tactical insight, analytical precision, and strategic focus.""",
    tools=[
        book_opponent_tactical_analysis,
        get_daily_schedule,
        query_team_memory,
    ],
)

# 3. MaAgent: Physical Therapist & Nutritionist
ma_agent = Agent(
    name="ma_agent",
    model=MODEL_MA,
    description="Physical Therapist & Nutritionist Ma: Responsible for workout syllabus, post-game recovery, and nutrition.",
    instruction="""You are MaAgent, assisting Ma (Physical Therapist and Nutrition Specialist for Gina).

Your primary responsibilities:
1. Attach exercise and physical therapy syllabus to auto-booked pre-training workout slots using `set_workout_syllabus`.
   - Do NOT try to change the workout time slot on regular training days; it is automatically anchored 1 hour prior to Gor's training.
2. Record daily nutritional meal plans and trigger food delivery orders using `order_daily_meals`.
   - Specify breakfast, lunch, and dinner items.
3. Check the schedule using `get_daily_schedule`.
4. Consult long-term athlete preferences using `query_team_memory`.
Always prioritize athlete muscular recovery, physiological readiness, and dietary discipline.""",
    tools=[
        set_workout_syllabus,
        order_daily_meals,
        get_daily_schedule,
        query_team_memory,
    ],
)

# 4. BeitaAgent: Personal Assistant & PR Manager
beita_agent = Agent(
    name="beita_agent",
    model=MODEL_BEITA,
    description="Personal Assistant Beita: Responsible for PR interviews, sponsor engagements, and media sessions.",
    instruction="""You are BeitaAgent, assisting Beita (Personal Assistant and PR/Media Manager for Gina).

Your primary responsibilities:
1. Book PR, media, and sponsor slots using `book_pr_activity`.
   - Allowed strictly between 10:00 AM and 6:00 PM.
   - Prohibited before court training on the same day.
   - Prohibited on tournament match days and the day immediately before match day.
2. Assisted Rescheduling:
   - If a PR event is bumped by Gor's training override, Beita's event is marked BUMPED_BY_OVERRIDE.
   - Present the engine's suggested alternative open slot to Beita politely and offer to rebook.
3. Check the schedule using `get_daily_schedule`.
4. Check sponsor terms & guidelines using `query_team_memory`.
Always maintain a diplomatic, organized, and polished tone.""",
    tools=[
        book_pr_activity,
        get_daily_schedule,
        query_team_memory,
    ],
)

# 5. GinaAgent: WTA Tennis Player
gina_agent = Agent(
    name="gina_agent",
    model=MODEL_GINA,
    description="Player Gina: View-only daily agendas, 1-hour pre-activity alerts, and sleep quiet hours.",
    instruction="""You are GinaAgent, assisting professional WTA tennis player Gina.

Your primary responsibilities:
1. Provide Gina with her daily schedule and active 1-hour pre-activity alerts using `get_daily_schedule`.
2. Emphasize Sleep Quiet Hours (22:00 - 07:30): Explain that advance notifications during sleep hours (like early breakfast alarms) are silenced to protect deep sleep and athletic recovery.
3. Gina has view-only permissions. If she requests adding or overriding calendar events, kindly remind her that scheduling is handled by Gor (training), Ma (workouts/meals), Sai (scouting), or Beita (PR).
4. Review athlete habits & memories via `query_team_memory`.
Always maintain an empathetic, supportive, and athlete-centric tone.""",
    tools=[
        get_daily_schedule,
        query_team_memory,
    ],
)

# 6. Coordinator Agent: Master Triage & Router
coordinator_agent = Agent(
    name="coordinator_agent",
    model=MODEL_COORDINATOR,
    description="Master Coordinator for Gina's Tennis Team: Routes intents and tags to Gor, Sai, Ma, Beita, and Gina.",
    instruction="""You are the Coordinator Agent (Digital Chief-of-Staff) for WTA tennis player Gina and her support team.

The team members are:
- Gina: The Player (view schedule, alerts, meal plan).
- Gor: Head Coach (court training, fatigue limits, overrides).
- Sai: Tactical Coach (opponent analysis on pre-match days, tactics).
- Ma: Physical Therapist / Nutritionist (workout syllabus, meal plans & orders).
- Beita: PR / PA (media, sponsor shoots, rescheduling).

Behavior:
1. Inspect persona tags such as '[As Gor]', '[As Sai]', '[As Ma]', '[As Beita]', '[As Gina]' or conversational context.
2. Delegate the request to the matching specialist sub-agent.
3. For general schedule inquiries, you may directly call `get_daily_schedule`.
4. Query long-term team memory using `query_team_memory`.
Always ensure swift, accurate routing and seamless team coordination.""",
    sub_agents=[
        gor_agent,
        sai_agent,
        ma_agent,
        beita_agent,
        gina_agent,
    ],
    tools=[
        get_daily_schedule,
        approve_pending_proposal,
        reject_pending_proposal,
        query_team_memory,
    ],
)

# Root export & App definition with Context Compaction
root_agent = coordinator_agent

compaction_config = EventsCompactionConfig(
    token_threshold=16000,
    event_retention_size=5,
)

app = App(
    name="app",
    root_agent=root_agent,
    events_compaction_config=compaction_config,
)

# Registry mapping persona names to agents
PERSONA_AGENT_MAP: dict[str, Agent] = {
    "gor": gor_agent,
    "coach gor": gor_agent,
    "sai": sai_agent,
    "coach sai": sai_agent,
    "ma": ma_agent,
    "beita": beita_agent,
    "gina": gina_agent,
    "coordinator": coordinator_agent,
    "system": coordinator_agent,
}


def extract_persona(text: str) -> tuple[str | None, str]:
    """Extract persona tag like '[As Gor]' from the prompt if present."""
    match = re.match(r"^\s*\[(?:As\s+)?([A-Za-z]+)\]\s*(.*)$", text, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip().lower(), match.group(2).strip()
    return None, text.strip()


class SupportAgentRunner:
    """Manages multi-turn conversations and persona dispatching using ADK's Runner with compaction and persistence."""

    def __init__(self):
        self.session_service = get_session_service()
        self.runners: dict[str, Runner] = {
            "coordinator": Runner(app=app, session_service=self.session_service),
            "gor": Runner(
                app=App(
                    name="app", root_agent=gor_agent, events_compaction_config=compaction_config
                ),
                session_service=self.session_service,
            ),
            "sai": Runner(
                app=App(
                    name="app", root_agent=sai_agent, events_compaction_config=compaction_config
                ),
                session_service=self.session_service,
            ),
            "ma": Runner(
                app=App(
                    name="app", root_agent=ma_agent, events_compaction_config=compaction_config
                ),
                session_service=self.session_service,
            ),
            "beita": Runner(
                app=App(
                    name="app", root_agent=beita_agent, events_compaction_config=compaction_config
                ),
                session_service=self.session_service,
            ),
            "gina": Runner(
                app=App(
                    name="app", root_agent=gina_agent, events_compaction_config=compaction_config
                ),
                session_service=self.session_service,
            ),
        }
        self.sessions: dict[str, str] = {}

    async def execute_turn(
        self, user_input: str, persona: str | None = None, user_id: str = "team_user"
    ) -> str:
        """Execute a conversational turn dispatched to the appropriate agent."""
        # 1. Check for explicit persona tag in message
        tagged_persona, clean_input = extract_persona(user_input)
        target_persona = (persona or tagged_persona or "coordinator").lower()
        active_runner = self.runners.get(target_persona, self.runners["coordinator"])

        # 2. Get or create session for this runner
        session_key = f"{target_persona}_{user_id}"
        if session_key not in self.sessions:
            session = await active_runner.session_service.create_session(
                app_name=active_runner.app_name, user_id=user_id
            )
            self.sessions[session_key] = session.id
        session_id = self.sessions[session_key]

        # 3. Dispatch message to ADK runner
        content = types.Content(
            role="user", parts=[types.Part.from_text(text=clean_input or user_input)]
        )

        response_parts = []
        async for event in active_runner.run_async(
            session_id=session_id, user_id=user_id, new_message=content
        ):
            if hasattr(event, "content") and event.content:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        response_parts.append(part.text)

        if response_parts:
            return "\n".join(response_parts).strip()

        # Fallback if model returned structured tool call only
        return "Action processed successfully."


# Global runner instance
agent_runner = SupportAgentRunner()


def run_turn(user_input: str, persona: str | None = None) -> str:
    """Synchronous entry point for running a conversational turn."""
    return asyncio.run(agent_runner.execute_turn(user_input, persona))

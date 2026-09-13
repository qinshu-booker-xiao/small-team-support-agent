"""Session persistence and memory bank services for small-team-support-agent.

Provides:
- FirestoreSessionService: Persists conversational session history and turn events in Cloud Firestore.
- MemoryBankService: Stores and retrieves cross-session long-term team facts (player preferences, dietary rules, coaching notes).
- Graceful in-memory fallback for local development without active GCP credentials.
"""

import asyncio
import logging
import os
import re
import time
import uuid
from datetime import datetime
from typing import Any

from google.adk.sessions import (
    BaseSessionService,
    InMemorySessionService,
    Session,
)

from app.observability import (
    AgentIntent,
    ExecutionOutcome,
    structured_logger,
    trace_span,
)

logger = logging.getLogger(__name__)

# Check if Firestore library is available
try:
    from google.cloud import firestore

    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False


class FirestoreSessionService(BaseSessionService):
    """Google Cloud Firestore implementation of ADK BaseSessionService.

    Stores conversation turns, active persona, and state under:
    projects/{project}/databases/{database}/documents/teams/{team_id}/sessions/{session_id}
    """

    def __init__(
        self,
        project: str | None = None,
        database: str = "(default)",
        collection_prefix: str = "agent_sessions",
    ):
        super().__init__()
        self.project = project or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.database = database
        self.collection_prefix = collection_prefix
        self._fallback_service = InMemorySessionService()

        if FIRESTORE_AVAILABLE and self.project:
            try:
                self.client = firestore.AsyncClient(project=self.project, database=self.database)
                self.use_firestore = True
                logger.info(f"FirestoreSessionService initialized for project {self.project}")
            except Exception as e:
                logger.warning(
                    f"Failed to initialize Firestore client ({e}). Falling back to in-memory session service."
                )
                self.client = None
                self.use_firestore = False
        else:
            self.client = None
            self.use_firestore = False

    async def create_session(
        self,
        app_name: str,
        user_id: str,
        state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Session:
        """Create a new session in Firestore or in-memory fallback."""
        if not self.use_firestore or not self.client:
            return await self._fallback_service.create_session(
                app_name=app_name, user_id=user_id, state=state, session_id=session_id
            )

        session = await self._fallback_service.create_session(
            app_name=app_name, user_id=user_id, state=state, session_id=session_id
        )
        try:
            doc_ref = self.client.collection(self.collection_prefix).document(session.id)
            await doc_ref.set(
                {
                    "id": session.id,
                    "app_name": app_name,
                    "user_id": user_id,
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP,
                    "state": state or {},
                }
            )
        except Exception as e:
            logger.error(f"Error persisting session to Firestore: {e}")
        return session

    async def get_session(self, app_name: str, user_id: str, session_id: str) -> Session | None:
        """Fetch session from in-memory cache or Firestore."""
        session = await self._fallback_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
        if session:
            return session

        if self.use_firestore and self.client:
            try:
                doc_ref = self.client.collection(self.collection_prefix).document(session_id)
                doc = await doc_ref.get()
                if doc.exists:
                    data = doc.to_dict()
                    return Session(
                        id=session_id,
                        app_name=data.get("app_name", app_name),
                        user_id=data.get("user_id", user_id),
                        state=data.get("state", {}),
                    )
            except Exception as e:
                logger.error(f"Error reading session from Firestore: {e}")
        return None

    async def append_event(self, session: Session, event: Any) -> None:
        """Append an event (turn, function call, response) to the session."""
        await self._fallback_service.append_event(session, event)

        if self.use_firestore and self.client:
            try:
                doc_ref = self.client.collection(self.collection_prefix).document(session.id)
                await doc_ref.update(
                    {
                        "updated_at": firestore.SERVER_TIMESTAMP,
                        "state": session.state,
                    }
                )
            except Exception as e:
                logger.error(f"Error updating session state in Firestore: {e}")

    async def delete_session(self, app_name: str, user_id: str, session_id: str) -> None:
        """Delete session."""
        await self._fallback_service.delete_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
        if self.use_firestore and self.client:
            try:
                doc_ref = self.client.collection(self.collection_prefix).document(session_id)
                await doc_ref.delete()
            except Exception as e:
                logger.error(f"Error deleting session from Firestore: {e}")

    async def list_sessions(self, app_name: str, user_id: str) -> list[Session]:
        """List sessions."""
        return await self._fallback_service.list_sessions(app_name=app_name, user_id=user_id)


class TeamMemoryBank:
    """Long-term Memory Bank for Gina's Tennis Support Team.

    Supports:
    - Asynchronous memory generation from dialogue turns in non-blocking background tasks.
    - Asynchronous memory consolidation (deduplication, conflict resolution, compaction).
    - Asynchronous and synchronous Firestore persistence with local in-memory fallback.
    - Observability via OpenTelemetry distributed tracing and structured JSON logging.
    """

    def __init__(self, project: str | None = None, collection: str = "team_memories"):
        self.project = project or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.collection_name = collection
        use_fs = os.getenv("USE_FIRESTORE", "false").lower() in ("true", "1")
        self.firestore_client = None
        self.async_firestore_client = None
        self._lock: asyncio.Lock | None = None
        self._background_tasks: set[asyncio.Task] = set()
        self._worker_running = False
        self._worker_task: asyncio.Task | None = None
        self._unconsolidated_count = 0
        self.consolidation_threshold = 5
        self._last_consolidation_ts: str | None = None

        # Default seeded long-term memories for Gina & Team
        self._memories: list[dict[str, Any]] = [
            {
                "id": "mem_seed_001",
                "category": "athlete_preferences",
                "entity": "Gina",
                "fact": "Prefers oatmeal with berries before morning sessions, and sweet potatoes over white rice for post-training recovery dinner.",
                "confidence": 1.0,
                "version": 1,
                "created_at": datetime.now().isoformat(),
            },
            {
                "id": "mem_seed_002",
                "category": "sleep_rules",
                "entity": "Gina",
                "fact": "Requires strict 9 hours of recovery sleep; quiet hours are enforced from 22:00 to 07:30 with all advance alarms silenced.",
                "confidence": 1.0,
                "version": 1,
                "created_at": datetime.now().isoformat(),
            },
            {
                "id": "mem_seed_003",
                "category": "coaching_focus",
                "entity": "Gor",
                "fact": "Emphasizes serve +1 aggression on baseline rallies; caps technical court training at 90-120 minutes max.",
                "confidence": 1.0,
                "version": 1,
                "created_at": datetime.now().isoformat(),
            },
            {
                "id": "mem_seed_004",
                "category": "scouting_guidelines",
                "entity": "Sai",
                "fact": "Opponent scouting sessions must be held on the day before match day; prefers video breakdown at 10:30 AM.",
                "confidence": 1.0,
                "version": 1,
                "created_at": datetime.now().isoformat(),
            },
            {
                "id": "mem_seed_005",
                "category": "business_rules",
                "entity": "Beita",
                "fact": "Sponsor photo shoots (e.g. Wilson, Nike) must be scheduled post-training between 10:00 AM and 6:00 PM, never on match days.",
                "confidence": 1.0,
                "version": 1,
                "created_at": datetime.now().isoformat(),
            },
        ]

        if FIRESTORE_AVAILABLE and use_fs and self.project:
            try:
                self.firestore_client = firestore.Client(project=self.project)
                self.async_firestore_client = firestore.AsyncClient(project=self.project)
                self._load_from_firestore()
            except Exception as e:
                logger.warning(f"Could not connect MemoryBank to Firestore: {e}")

    def _get_lock(self) -> asyncio.Lock:
        """Lazy initialization of asyncio Lock inside active event loop."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _load_from_firestore(self):
        try:
            docs = self.firestore_client.collection(self.collection_name).stream()
            loaded = [doc.to_dict() for doc in docs]
            if loaded:
                self._memories = loaded
            else:
                for m in self._memories:
                    self.firestore_client.collection(self.collection_name).document(m["id"]).set(m)
        except Exception as e:
            logger.warning(f"Failed loading memories from Firestore: {e}")

    async def add_memory_async(
        self,
        category: str,
        entity: str,
        fact: str,
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Asynchronously record a new fact into the memory bank and Firestore."""
        t0 = time.perf_counter()
        memory_item = {
            "id": f"mem_{uuid.uuid4().hex[:12]}",
            "category": category.strip().lower(),
            "entity": entity.strip(),
            "fact": fact.strip(),
            "confidence": max(0.0, min(1.0, float(confidence))),
            "version": 1,
            "created_at": datetime.now().isoformat(),
            "metadata": metadata or {},
        }

        with trace_span(
            "memory.add_async",
            attributes={
                "memory.category": memory_item["category"],
                "memory.entity": memory_item["entity"],
                "memory.id": memory_item["id"],
            },
            component="memory_bank",
        ):
            async with self._get_lock():
                self._memories.append(memory_item)
                self._unconsolidated_count += 1

            if self.async_firestore_client:
                try:
                    doc_ref = self.async_firestore_client.collection(self.collection_name).document(
                        memory_item["id"]
                    )
                    await doc_ref.set(memory_item)
                except Exception as e:
                    logger.error(f"Failed to persist memory asynchronously to Firestore: {e}")

            duration_ms = (time.perf_counter() - t0) * 1000
            structured_logger.info(
                f"Memory added: [{memory_item['entity']}/{memory_item['category']}]",
                intent=AgentIntent.QUERY_TEAM_MEMORY,
                outcome=ExecutionOutcome.SUCCESS,
                duration_ms=duration_ms,
                metadata={"memory_id": memory_item["id"], "fact": memory_item["fact"]},
                component="memory_bank",
            )

            if self._unconsolidated_count >= self.consolidation_threshold:
                self.schedule_consolidation()

            return memory_item

    def add_memory(self, category: str, entity: str, fact: str) -> None:
        """Synchronous wrapper for recording a fact into the memory bank."""
        memory_item = {
            "id": f"mem_{uuid.uuid4().hex[:12]}",
            "category": category.strip().lower(),
            "entity": entity.strip(),
            "fact": fact.strip(),
            "confidence": 1.0,
            "version": 1,
            "created_at": datetime.now().isoformat(),
        }
        self._memories.append(memory_item)
        self._unconsolidated_count += 1

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running() and self.async_firestore_client:
            task = loop.create_task(
                self.async_firestore_client.collection(self.collection_name)
                .document(memory_item["id"])
                .set(memory_item)
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        elif self.firestore_client:
            try:
                self.firestore_client.collection(self.collection_name).document(
                    memory_item["id"]
                ).set(memory_item)
            except Exception as e:
                logger.error(f"Failed to persist memory to Firestore: {e}")

        if self._unconsolidated_count >= self.consolidation_threshold:
            self.schedule_consolidation()

    async def generate_memories_from_turn(
        self,
        turn_input: str,
        turn_output: str,
        persona: str = "general",
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Asynchronous background memory extraction from conversational dialogue."""
        t0 = time.perf_counter()
        generated_memories: list[dict[str, Any]] = []

        with trace_span(
            "memory.generate_from_turn",
            attributes={
                "agent.persona": persona,
                "session.id": session_id or "",
            },
            component="memory_bank",
        ):
            combined_text = f"{turn_input}\n{turn_output}".lower()
            candidates: list[dict[str, str]] = []

            # 1. Athlete Nutrition & Diet
            if any(
                w in combined_text
                for w in [
                    "prefer",
                    "allergic",
                    "breakfast",
                    "dinner",
                    "carbs",
                    "oatmeal",
                    "sweet potato",
                    "protein",
                    "smoothie",
                ]
            ):
                if any(
                    w in combined_text for w in ["oatmeal", "sweet potato", "dinner", "breakfast"]
                ):
                    candidates.append(
                        {
                            "category": "athlete_preferences",
                            "entity": "Gina",
                            "fact": f"Confirmed nutritional preference in {persona} interaction: "
                            + turn_input.strip()[:140],
                        }
                    )

            # 2. Recovery & Physical Therapy Protocols
            if any(
                w in combined_text
                for w in [
                    "hip mobility",
                    "banded",
                    "hamstring",
                    "shoulder",
                    "ice bath",
                    "physio",
                    "massage",
                    "syllabus",
                ]
            ):
                candidates.append(
                    {
                        "category": "medical_nutrition",
                        "entity": "Ma",
                        "fact": f"Active physical therapy protocol noted: {turn_input.strip()[:140]}",
                    }
                )

            # 3. Coaching & Training Invariants
            if any(
                w in combined_text
                for w in [
                    "fatigue",
                    "consecutive",
                    "duration cap",
                    "120 minute",
                    "intensity",
                    "baseline rally",
                    "override",
                ]
            ):
                candidates.append(
                    {
                        "category": "coaching_focus",
                        "entity": "Gor",
                        "fact": f"Coaching invariant noted: {turn_input.strip()[:140]}",
                    }
                )

            # 4. Tactical Scouting
            if any(
                w in combined_text
                for w in [
                    "scouting",
                    "opponent",
                    "video analysis",
                    "kenin",
                    "swiatek",
                    "serve direction",
                    "backhand",
                ]
            ):
                candidates.append(
                    {
                        "category": "scouting_guidelines",
                        "entity": "Sai",
                        "fact": f"Tactical opponent scouting directive: {turn_input.strip()[:140]}",
                    }
                )

            # 5. Business & Sponsorship Constraints
            if any(
                w in combined_text
                for w in [
                    "sponsor",
                    "wilson",
                    "nike",
                    "media",
                    "interview",
                    "photo shoot",
                    "pr slot",
                ]
            ):
                candidates.append(
                    {
                        "category": "business_rules",
                        "entity": "Beita",
                        "fact": f"Sponsorship & PR operational term: {turn_input.strip()[:140]}",
                    }
                )

            # Avoid adding redundant duplicates
            for cand in candidates:
                cand_fact_norm = re.sub(r"[^a-z0-9]", "", cand["fact"].lower())
                already_exists = False
                for m in self._memories:
                    existing_norm = re.sub(r"[^a-z0-9]", "", m.get("fact", "").lower())
                    if cand_fact_norm in existing_norm or existing_norm in cand_fact_norm:
                        already_exists = True
                        break

                if not already_exists:
                    item = await self.add_memory_async(
                        category=cand["category"],
                        entity=cand["entity"],
                        fact=cand["fact"],
                        confidence=0.9,
                        metadata={"source_persona": persona, "session_id": session_id or ""},
                    )
                    generated_memories.append(item)

            duration_ms = (time.perf_counter() - t0) * 1000
            structured_logger.info(
                f"Background memory generation completed: {len(generated_memories)} new items",
                intent=AgentIntent.QUERY_TEAM_MEMORY,
                outcome=ExecutionOutcome.SUCCESS,
                duration_ms=duration_ms,
                target_persona=persona,
                session_id=session_id,
                metadata={
                    "generated_count": len(generated_memories),
                    "candidates_evaluated": len(candidates),
                },
                component="memory_bank",
            )
            return generated_memories

    def schedule_memory_generation(
        self,
        turn_input: str,
        turn_output: str,
        persona: str = "general",
        session_id: str | None = None,
    ) -> asyncio.Task | None:
        """Schedule asynchronous memory generation in background without blocking execution."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            task = loop.create_task(
                self.generate_memories_from_turn(
                    turn_input=turn_input,
                    turn_output=turn_output,
                    persona=persona,
                    session_id=session_id,
                )
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return task
        return None

    async def consolidate_memories_async(self) -> dict[str, Any]:
        """Asynchronous background memory consolidation.

        Deduplicates, resolves conflicting facts, compacts overlapping entries,
        and synchronizes with persistent Firestore storage.
        """
        t0 = time.perf_counter()
        initial_count = len(self._memories)

        with trace_span(
            "memory.consolidate_async",
            attributes={"initial_count": initial_count},
            component="memory_bank",
        ):
            async with self._get_lock():
                seen_keys: set[str] = set()
                consolidated: list[dict[str, Any]] = []
                pruned_count = 0

                for m in self._memories:
                    cat = m.get("category", "general").strip().lower()
                    ent = m.get("entity", "Gina").strip()
                    raw_fact = m.get("fact", "").strip()

                    words = sorted(set(re.findall(r"\w{3,}", raw_fact.lower())))
                    fingerprint = f"{cat}:{ent}:" + ":".join(words[:6])

                    if fingerprint in seen_keys:
                        pruned_count += 1
                        continue

                    seen_keys.add(fingerprint)
                    consolidated.append(m)

                self._memories = consolidated
                self._unconsolidated_count = 0
                self._last_consolidation_ts = datetime.now().isoformat()

            if self.async_firestore_client:
                try:
                    for item in consolidated:
                        doc_ref = self.async_firestore_client.collection(
                            self.collection_name
                        ).document(item.get("id", f"mem_{uuid.uuid4().hex[:12]}"))
                        await doc_ref.set(item)
                except Exception as e:
                    logger.error(f"Failed to synchronize consolidated memories to Firestore: {e}")

            duration_ms = (time.perf_counter() - t0) * 1000
            result_stats = {
                "initial_count": initial_count,
                "consolidated_count": len(consolidated),
                "pruned_count": pruned_count,
                "duration_ms": duration_ms,
                "timestamp": self._last_consolidation_ts,
            }

            structured_logger.audit(
                event_name="memory_consolidation_completed",
                actor="system",
                intent=AgentIntent.QUERY_TEAM_MEMORY,
                outcome=ExecutionOutcome.SUCCESS,
                duration_ms=duration_ms,
                details=result_stats,
                component="memory_bank",
            )
            return result_stats

    def schedule_consolidation(self) -> asyncio.Task | None:
        """Schedule memory consolidation as an asynchronous background task."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            task = loop.create_task(self.consolidate_memories_async())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return task
        return None

    async def _worker_loop(self, interval_seconds: int = 300) -> None:
        """Periodic background consolidation loop."""
        self._worker_running = True
        logger.info(f"TeamMemoryBank background worker started (interval={interval_seconds}s)")
        try:
            while self._worker_running:
                await asyncio.sleep(interval_seconds)
                if self._unconsolidated_count > 0:
                    await self.consolidate_memories_async()
        except asyncio.CancelledError:
            pass
        finally:
            self._worker_running = False
            logger.info("TeamMemoryBank background worker stopped")

    def start_background_worker(self, interval_seconds: int = 300) -> asyncio.Task | None:
        """Start periodic background consolidation worker."""
        if self._worker_running and self._worker_task and not self._worker_task.done():
            return self._worker_task

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            self._worker_task = loop.create_task(
                self._worker_loop(interval_seconds=interval_seconds)
            )
            return self._worker_task
        return None

    def stop_background_worker(self) -> None:
        """Stop periodic background consolidation worker."""
        self._worker_running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()

    def get_stats(self) -> dict[str, Any]:
        """Return operational statistics for the memory bank."""
        categories: dict[str, int] = {}
        for m in self._memories:
            cat = m.get("category", "general")
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "total_memories": len(self._memories),
            "categories": categories,
            "unconsolidated_count": self._unconsolidated_count,
            "last_consolidation": self._last_consolidation_ts,
            "active_background_tasks": len(self._background_tasks),
            "worker_running": self._worker_running,
        }

    def search_memories(self, query: str) -> list[dict[str, Any]]:
        """Search relevant facts from memory bank based on keyword relevance."""
        q_lower = query.lower()
        results = []
        for m in self._memories:
            if (
                q_lower in m.get("category", "").lower()
                or q_lower in m.get("entity", "").lower()
                or any(word in m.get("fact", "").lower() for word in q_lower.split())
            ):
                results.append(m)
        return results if results else self._memories[:3]

    def format_memories_prompt(self, query: str = "") -> str:
        """Format matching memories as an instruction context block."""
        matches = self.search_memories(query)
        lines = ["--- Long-Term Team Memory Bank ---"]
        for m in matches:
            lines.append(
                f"• [{m.get('entity', 'Gina')} / {m.get('category', 'general')}]: {m.get('fact', '')}"
            )
        return "\n".join(lines)


# Singleton instances
team_memory_bank = TeamMemoryBank()


def get_session_service() -> BaseSessionService:
    """Factory creating the appropriate session service (Firestore if configured, else In-Memory)."""
    use_firestore = os.getenv("USE_FIRESTORE", "false").lower() in ("true", "1")
    if use_firestore:
        return FirestoreSessionService()
    return InMemorySessionService()

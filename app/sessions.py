"""Session persistence and memory bank services for small-team-support-agent.

Provides:
- FirestoreSessionService: Persists conversational session history and turn events in Cloud Firestore.
- MemoryBankService: Stores and retrieves cross-session long-term team facts (player preferences, dietary rules, coaching notes).
- Graceful in-memory fallback for local development without active GCP credentials.
"""

import logging
import os
from typing import Any, Dict, List, Optional
from datetime import datetime

from google.adk.sessions import (
    BaseSessionService,
    InMemorySessionService,
    Session,
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
        project: Optional[str] = None,
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
                self.client = firestore.AsyncClient(
                    project=self.project, database=self.database
                )
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
        state: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
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

    async def get_session(
        self, app_name: str, user_id: str, session_id: str
    ) -> Optional[Session]:
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

    async def delete_session(
        self, app_name: str, user_id: str, session_id: str
    ) -> None:
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

    async def list_sessions(
        self, app_name: str, user_id: str
    ) -> List[Session]:
        """List sessions."""
        return await self._fallback_service.list_sessions(app_name=app_name, user_id=user_id)


class TeamMemoryBank:
    """Long-term Memory Bank for Gina's Tennis Support Team.

    Stores cross-session athlete preferences, coaching guidelines, and sponsor constraints.
    Supports Firestore persistence when USE_FIRESTORE=true with local in-memory fallback.
    """

    def __init__(self, project: Optional[str] = None, collection: str = "team_memories"):
        self.project = project or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.collection_name = collection
        use_fs = os.getenv("USE_FIRESTORE", "false").lower() in ("true", "1")
        self.firestore_client = None

        # Default seeded long-term memories for Gina & Team
        self._memories: List[Dict[str, Any]] = [
            {
                "category": "athlete_preferences",
                "entity": "Gina",
                "fact": "Prefers oatmeal with berries before morning sessions, and sweet potatoes over white rice for post-training recovery dinner.",
            },
            {
                "category": "sleep_rules",
                "entity": "Gina",
                "fact": "Requires strict 9 hours of recovery sleep; quiet hours are enforced from 22:00 to 07:30 with all advance alarms silenced.",
            },
            {
                "category": "coaching_focus",
                "entity": "Gor",
                "fact": "Emphasizes serve +1 aggression on baseline rallies; caps technical court training at 90-120 minutes max.",
            },
            {
                "category": "scouting_guidelines",
                "entity": "Sai",
                "fact": "Opponent scouting sessions must be held on the day before match day; prefers video breakdown at 10:30 AM.",
            },
            {
                "category": "business_rules",
                "entity": "Beita",
                "fact": "Sponsor photo shoots (e.g. Wilson, Nike) must be scheduled post-training between 10:00 AM and 6:00 PM, never on match days.",
            },
        ]

        if FIRESTORE_AVAILABLE and use_fs and self.project:
            try:
                self.firestore_client = firestore.Client(project=self.project)
                self._load_from_firestore()
            except Exception as e:
                logger.warning(f"Could not connect MemoryBank to Firestore: {e}")

    def _load_from_firestore(self):
        try:
            docs = self.firestore_client.collection(self.collection_name).stream()
            loaded = [doc.to_dict() for doc in docs]
            if loaded:
                self._memories = loaded
            else:
                # Seed Firestore with initial memories
                for m in self._memories:
                    self.firestore_client.collection(self.collection_name).add(m)
        except Exception as e:
            logger.warning(f"Failed loading memories from Firestore: {e}")

    def add_memory(self, category: str, entity: str, fact: str) -> None:
        """Record a new fact into the memory bank."""
        memory_item = {
            "category": category,
            "entity": entity,
            "fact": fact,
            "created_at": datetime.now().isoformat(),
        }
        self._memories.append(memory_item)
        if self.firestore_client:
            try:
                self.firestore_client.collection(self.collection_name).add(memory_item)
            except Exception as e:
                logger.error(f"Failed to persist memory to Firestore: {e}")

    def search_memories(self, query: str) -> List[Dict[str, Any]]:
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
            lines.append(f"• [{m.get('entity', 'Gina')} / {m.get('category', 'general')}]: {m.get('fact', '')}")
        return "\n".join(lines)


# Singleton instances
team_memory_bank = TeamMemoryBank()


def get_session_service() -> BaseSessionService:
    """Factory creating the appropriate session service (Firestore if configured, else In-Memory)."""
    use_firestore = os.getenv("USE_FIRESTORE", "false").lower() in ("true", "1")
    if use_firestore:
        return FirestoreSessionService()
    return InMemorySessionService()

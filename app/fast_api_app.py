# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import contextlib
import os
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Literal

from a2a.server.tasks import InMemoryTaskStore
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import Runner
from pydantic import BaseModel, Field

from app.app_utils import services
from app.app_utils.a2a import attach_a2a_routes
from app.observability import (
    PIIRedactor,
    structured_logger,
)

load_dotenv()
allow_origins = os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
otel_to_cloud = os.getenv("OTEL_TO_CLOUD", "false").lower() in ("true", "1")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class UserFeedback(BaseModel):
    """Represents user rating and qualitative feedback for athletic support conversations."""

    score: int | float = Field(..., description="Rating score (e.g. 1 to 5)")
    text: str | None = Field(default="", description="User feedback commentary")
    log_type: Literal["feedback"] = "feedback"
    service_name: str = "small-team-support-agent"
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from app.agent import app as adk_app
    from app.agent import root_agent

    runner = Runner(
        app=adk_app,
        session_service=services.get_session_service(),
        artifact_service=services.get_artifact_service(),
        auto_create_session=True,
    )
    app.state.runner = runner
    app.state.agent_app_name = adk_app.name
    await attach_a2a_routes(
        app,
        agent=root_agent,
        runner=runner,
        task_store=InMemoryTaskStore(),
        rpc_path=f"/a2a/{adk_app.name}",
    )
    structured_logger.info(
        "FastAPI service initialized with ADK routes and A2A interfaces",
        component="fast_api_server",
        metadata={"otel_to_cloud": otel_to_cloud, "app_name": adk_app.name},
    )
    yield


app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=services.ARTIFACT_SERVICE_URI,
    allow_origins=allow_origins,
    session_service_uri=services.SESSION_SERVICE_URI,
    otel_to_cloud=otel_to_cloud,
    lifespan=lifespan,
)
app.title = "small-team-support-agent"
app.description = "Enterprise API for WTA Tennis Player & Multi-Persona Support Team"


@app.middleware("http")
async def structured_http_logging_middleware(request: Request, call_next):
    """Structured HTTP middleware recording latency and status codes."""
    t0 = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - t0) * 1000

    # Only log non-internal assets to keep logs high-signal
    if not request.url.path.startswith("/static"):
        structured_logger.info(
            f"{request.method} {request.url.path} -> {response.status_code}",
            component="http_server",
            duration_ms=duration_ms,
            metadata={
                "http.method": request.method,
                "http.path": request.url.path,
                "http.status_code": response.status_code,
            },
        )
    return response


@app.post("/feedback")
def submit_feedback(feedback: UserFeedback) -> dict[str, str]:
    """Submit qualitative conversation feedback with automatic PII scrubbing."""
    sanitized_text = PIIRedactor.redact_text(feedback.text or "")
    structured_logger.info(
        f"User feedback received: score={feedback.score}",
        component="feedback",
        metadata={
            "score": feedback.score,
            "comment": sanitized_text,
            "user_id": feedback.user_id,
            "session_id": feedback.session_id,
            "log_type": feedback.log_type,
        },
    )
    return {"status": "success", "message": "Feedback recorded successfully."}


@app.get("/healthz")
def health_check() -> dict[str, Any]:
    """Liveness probe for Cloud Run container orchestration."""
    return {
        "status": "HEALTHY",
        "service": "small-team-support-agent",
        "version": os.getenv("AGENT_VERSION", "0.1.0"),
        "tracing_enabled": True,
        "structured_logging": True,
        "pii_redaction": True,
    }


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)

# `small-team-support-agent`
**Multi-Persona Tennis Support Agent built on Google ADK 2.0**

The `small-team-support-agent` acts as the digital chief-of-staff for professional WTA tennis player **Gina** and her multi-disciplinary support team:
- **Gina**: Professional WTA Player (view-only schedule & sleep-protected alerts).
- **Gor**: Head Coach (court training sessions, fatigue limits, priority overrides).
- **Sai**: Tactical Coach (opponent video analysis on pre-match days, scouting dossier).
- **Ma**: Physical Therapist & Nutritionist (workout syllabus coupling, post-game recovery, meal orders).
- **Beita**: Personal Assistant & PR Manager (media/sponsor bookings, assisted rescheduling).
- **Coordinator**: Master Triage & Router (intent routing and persona tagging).

---

## Architecture: "Thin ADK 2.0 Wrapper + Deterministic Engine"

```
small-team-support-agent/
├── app/
│   ├── __init__.py
│   ├── models.py          # Pydantic schemas (CalendarEvent, MealPlan, Enums)
│   ├── engine.py          # Deterministic CalendarStore, Fatigue, Buffers & Formatter
│   ├── tools.py           # ADK 2.0 FunctionTools wrapping the engine
│   ├── agent.py           # Strategic Model Routed Multi-Agent System (Compaction enabled)
│   ├── sessions.py        # FirestoreSessionService & TeamMemoryBank persistence
│   ├── fast_api_app.py    # FastAPI server exposing ADK & A2A protocol routes
│   └── app_utils/         # Shared service registry & dynamic A2A endpoint mounter
├── tests/
│   └── eval/
│       ├── datasets/
│       │   └── team_support_eval.json # Canonical evaluation dataset for all personas
│       └── eval_config.yaml           # LLM-as-judge rubric metric configuration
├── docs/
│   └── design_spec_small_team_support_agent.md
├── Dockerfile             # Container definition for Cloud Run / Agent Runtime
├── agents-cli-manifest.yaml # agents-cli deployment manifest
├── run_demo.py            # Interactive terminal CLI with colored persona switcher
├── verify_demo.py         # Automated test runner asserting TC-01 through TC-11
├── run_eval.py            # Automated LLM-as-a-judge behavioral evaluation runner
├── README.md              # Project documentation and usage guide
└── pyproject.toml         # Package definition & tool.ruff linting config
```

### Strategic Model Routing
| Agent | Model | Role |
| :--- | :--- | :--- |
| **Coordinator** | `gemini-3.6-flash` | Fast persona dispatch & intent triage |
| **GorAgent** | `gemini-3.7-flash` | Multi-constraint reasoning, fatigue limits & overrides |
| **SaiAgent** | `gemini-3.1-pro-preview` | Deep tactical scouting and opponent analysis |
| **MaAgent** | `gemini-3.6-flash` | Structured workout syllabus & nutritional orders |
| **BeitaAgent** | `gemini-3.6-flash` | PR slot matching & assisted rescheduling |
| **GinaAgent** | `gemini-3.6-flash` | Empathetic briefings & sleep quiet hours filtering |

---

## Quick Start & Verification

### 1. Run Automated Deterministic Verification Suite (TC-01 through TC-11)
Runs unit & math assertions for all 11 core verification scenarios (fatigue rules, duration caps, quiet hours, auto-coupling, override rescheduling):
```bash
python3 verify_demo.py
```

### 2. Run Behavioral Evaluation Suite (LLM-as-a-Judge)
Executes end-to-end evaluation against `tests/eval/datasets/team_support_eval.json` with structured rubric scoring, generating JSON & HTML report artifacts in `artifacts/eval_results/`:
```bash
# Run all evaluation cases
python3 run_eval.py

# Run a quick sample of evaluation cases
python3 run_eval.py --max-cases 3
```

### 3. Run Interactive CLI Demo
Start the terminal interface with the interactive persona switcher:
```bash
python3 run_demo.py
```

Inside the CLI:
- `/persona <gor|sai|ma|beita|gina|coordinator>` — switch active persona.
- `/schedule [YYYY-MM-DD]` — view daily schedule and active alerts table.
- `/quick <1-11>` — trigger predefined test scenarios.
- `/reset` — reset calendar store to the reference simulation date (`2026-09-01`).
- `[Approve]` / `[Reject]` — confirm or cancel pending proposals.

---

## Cloud Deployment & GCP Production Integration

### 1. Firestore Session Persistence & Team Memory Bank
- **Session Persistence:** Set `USE_FIRESTORE=true` to persist all multi-turn sessions and context compaction states to Google Cloud Firestore Native database (`(default)` in `us-central1`).
- **Team Memory Bank:** Athlete preferences, coaching rules, and recovery guidelines are automatically seeded and synced with Firestore under the `team_memories` collection.
- **Context Compaction:** Enabled via ADK's `EventsCompactionConfig(token_threshold=16000, event_retention_size=5)` to prevent token bloat during multi-turn tennis tournament dialogues.
- **Graceful Fallback:** If `USE_FIRESTORE=false` or GCP credentials are absent, the agent automatically falls back to in-memory session management.

### 2. Serving via FastAPI & A2A (Agent-to-Agent)
The application provides a containerized HTTP service (`app/fast_api_app.py`) exposing:
- ADK standard routes (`/run_sse`, `/apps/app/...`).
- Built-in Agent2Agent JSON-RPC and Agent Card endpoints (`/a2a/app/.well-known/agent-card.json`).

Run the local web server:
```bash
uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8080
```

### 3. Deploy to GCP Cloud Run via `agents-cli`
```bash
# Verify build and dry-run deployment
agents-cli deploy --dry-run --project <YOUR_GCP_PROJECT_ID> --region us-central1

# Deploy to Cloud Run (scales to zero when idle, min-instances configurable)
agents-cli deploy \
  --project <YOUR_GCP_PROJECT_ID> \
  --region us-central1 \
  --service-name small-team-support-agent \
  --update-env-vars "USE_FIRESTORE=true,GOOGLE_CLOUD_PROJECT=<YOUR_GCP_PROJECT_ID>" \
  --no-confirm-project
```

### 4. Security & Credential Management
- Plaintext key file fallbacks (e.g. `~/gemini_key.txt`) are eliminated.
- Local execution relies on `.env` (strictly gitignored).
- Cloud Run / GCP execution uses Application Default Credentials (ADC) or GCP Secret Manager (`--secrets GEMINI_API_KEY=my-gemini-key`).

---

## Code Quality & Linting

The project enforces PEP 8 and Python 3.12+ syntax standards via **Ruff**:

```bash
# Check linting rules across codebase
ruff check .

# Check code formatting
ruff format --check .

# Auto-format codebase
ruff format .
```

---

## GitHub Repository

- **Repository**: [https://github.com/qinshu-booker-xiao/small-team-support-agent](https://github.com/qinshu-booker-xiao/small-team-support-agent)
- **Default Branch**: `main`
- **License**: Apache 2.0 / Proprietary to WTA Gina Team



# AgentHub Backend

FastAPI service for a **multi-agent AI platform**. Agents are defined as configuration documents in MongoDB, loaded per request, and routed through a **LangGraph** workflow. Adding a new agent needs no code changes.

<!-- [add a screenshot of /docs or a sample chat response] -->

## How a chat request flows

```
POST /api/chat/send
   │
   ▼
load_context → load_agents → route_request → run_selected_agent
                                                    │
                       format_response ← save_messages ← save_memory
```

| Step | What it does |
|---|---|
| `load_context` | Loads the session and its history |
| `load_agents` | Loads the agent registry from MongoDB |
| `route_request` | `AgentRouter` picks one agent using routing keywords and priority |
| `run_selected_agent` | Runs the chosen agent (LangChain `create_agent`) |
| `save_memory` | Updates session memory |
| `save_messages` | Stores the conversation |
| `format_response` | Returns the reply, including a `memory_updated` flag |

If no LLM key is set, agents fall back to deterministic, role-aware logic, so the service still runs for demos and tests.

## Agents are configuration

Each agent is a MongoDB document (or a seed config) with fields such as:

| Field | Purpose |
|---|---|
| `system_prompt` | The agent's instructions |
| `model`, `temperature` | LLM settings |
| `tools` | Tools the agent can use |
| `routing_keywords` | Words used by the router to choose this agent |

Example seeded agents: **Sales Bot**, **SEO Content Agent**, **Data Analyst Pro**.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/chat/send` | Route and run a chat message through LangGraph |
| GET | `/api/chat/history/{session_id}` | Session history |
| GET | `/api/v1/health` | Health check |
| POST, GET | `/api/v1/agents` | Create or list agents |
| GET | `/api/v1/agents/configs` | List agent configs |
| POST | `/api/v1/agents/route` | Route a task through the supervisor |
| GET | `/api/v1/agents/tools` | List available tools |
| POST | `/api/v1/agents/registry/rebuild` | Rebuild the agent registry |
| POST | `/api/v1/agents/seed` | Seed default agents |
| GET | `/docs` | Interactive API docs |

## Tech stack

Python, FastAPI, Pydantic v2, MongoDB (Motor), LangChain, LangGraph, OpenAI, Docker

## Getting started

```bash
git clone https://github.com/mmiskatul/ai-agent-studio-backend.git
cd ai-agent-studio-backend
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Key environment variables:

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI key. If empty, agents use the deterministic fallback. |
| `OPENAI_AGENT_MODEL` | Model name (default `gpt-4.1-mini`) |

Quick checks:

```bash
python -m compileall app
python -m ruff check .
```

## Status and roadmap

Personal project, not deployed to production.

- Routing currently uses keywords and priority; it could become a LangGraph supervisor node.
- No RAG or evaluation suite yet.

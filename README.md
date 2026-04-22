# AgentHub Backend

FastAPI backend for a dynamic multi-agent platform. Agents are stored in MongoDB,
loaded per request, routed through a LangGraph workflow, and executed with a
LangChain/OpenAI-compatible LLM layer plus deterministic fallback behavior when
no provider key is configured.

## Stack

- FastAPI
- MongoDB with Motor
- Pydantic v2
- LangChain `create_agent(...)`
- LangGraph state graph orchestration
- Repository and service layers

## Architecture

```text
app/
  main.py
  api/
    v1/endpoints/chat.py
  agents/
    config.py
    factory.py
    platform.py
    registry.py
    routing/
    configs/
  graph/
    state.py
    builder.py
    nodes/
      load_context.py
      load_agents.py
      route_request.py
      run_selected_agent.py
      save_memory.py
      save_messages.py
      format_response.py
  core/
  db/
  models/
  repositories/
  schemas/
  services/
  tools/
```

The production chat flow is:

```text
POST /api/chat/send
  -> load_context
  -> load_agents
  -> route_request
  -> run_selected_agent
  -> save_memory
  -> save_messages
  -> format_response
```

No agent-specific workflow logic is required to add a new agent. Add a MongoDB
agent document or seed config with `tools`, `model`, `temperature`, and
`system_prompt`.

## Local Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

API docs:

```text
http://localhost:8000/docs
```

Health check:

```text
GET http://localhost:8000/api/v1/health
```

## Environment

See [.env.example](./.env.example).

```env
BACKEND_CORS_ORIGINS=http://localhost:3000
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=agenthub
JWT_SECRET_KEY=change-this-secret
OPENAI_API_KEY=
OPENAI_AGENT_MODEL=gpt-4.1-mini
```

If `OPENAI_API_KEY` is empty, agents still respond through deterministic
role-aware fallback logic. With a key, the factory attempts LangChain
`create_agent(...)`.

## Agent MongoDB Document

Collection: `agents`

```json
{
  "_id": "sales_bot",
  "user_id": "660fffffffffffffffffffff",
  "name": "Sales Bot",
  "role": "Sales Assistant",
  "purpose": "Handles sales inquiries, pricing, and lead qualification.",
  "description": "Handles sales inquiries, pricing, and lead qualification.",
  "system_prompt": "You are a highly professional sales assistant. Qualify needs, explain options clearly, and never invent prices.",
  "tools": ["pricing_lookup", "faq_search"],
  "model": "gpt-4.1-mini",
  "llm_engine": "gpt-4.1-mini",
  "temperature": 0.4,
  "routing_keywords": ["price", "pricing", "quote", "buy", "purchase", "demo"],
  "priority": 1,
  "status": "active",
  "is_active": true,
  "created_at": {"$date": "2026-04-22T00:00:00Z"},
  "updated_at": {"$date": "2026-04-22T00:00:00Z"}
}
```

## Add A New Agent By Configuration

Insert a document like this, or call `POST /api/v1/agents`:

```json
{
  "name": "SEO Content Agent",
  "role": "Marketing",
  "purpose": "Creates SEO content briefs and campaign copy.",
  "description": "Creates SEO content briefs and campaign copy.",
  "system_prompt": "You are an SEO content strategist. Produce practical content plans.",
  "tools": ["search", "summarizer"],
  "llm_engine": "gpt-4.1-mini",
  "model": "gpt-4.1-mini",
  "temperature": 0.6,
  "status": "active",
  "is_active": true
}
```

Then rebuild the registry:

```bash
curl -X POST http://localhost:8000/api/v1/agents/registry/rebuild \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

No factory, router, or workflow code changes are needed.

## API Examples

Create an agent:

```bash
curl -X POST http://localhost:8000/api/v1/agents \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Data Analyst Pro\",\"role\":\"Data Analyst\",\"purpose\":\"Turns metrics into insights.\",\"description\":\"Turns metrics into insights.\",\"system_prompt\":\"You analyze business data and provide concise recommendations.\",\"tools\":[\"calculator\",\"summarizer\"],\"model\":\"gpt-4.1-mini\",\"llm_engine\":\"gpt-4.1-mini\",\"temperature\":0.4,\"status\":\"active\",\"is_active\":true}"
```

List agents:

```bash
curl http://localhost:8000/api/v1/agents \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

List agent configs:

```bash
curl http://localhost:8000/api/v1/agents/configs \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

List tools:

```bash
curl http://localhost:8000/api/v1/agents/tools
```

Route a task through the supervisor:

```bash
curl -X POST http://localhost:8000/api/v1/agents/route \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"task\":\"Analyze revenue by channel\"}"
```

Route and chat through LangGraph:

```bash
curl -X POST http://localhost:8000/api/chat/send \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"session_123\",\"chat_id\":\"chat_123\",\"message\":\"Can I get pricing for 25 seats?\"}"
```

Example response:

```json
{
  "session_id": "session_123",
  "chat_id": "chat_123",
  "agent": {
    "id": "sales_bot",
    "name": "Sales Bot",
    "role": "Sales Assistant"
  },
  "system_summary": "Sales Bot handled the request using session context and available memory.",
  "response": "Here are the pricing details I can help clarify...",
  "routing_reason": "Matched 1 routing keyword(s) for Sales Bot.",
  "memory_updated": true,
  "metadata": {
    "model": "gpt-4.1-mini",
    "timestamp": "2026-04-22T00:00:00+00:00"
  }
}
```

Fetch session history:

```bash
curl http://localhost:8000/api/chat/history/session_123 \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

Seed default agents:

```bash
curl -X POST http://localhost:8000/api/v1/agents/seed \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

## LangGraph-Ready Design

The `AgentRouter` currently selects one agent from the registry. This can become
a LangGraph supervisor node later without changing config storage or tool
loading. Each registered agent is already a config-built runtime node candidate.

## Checks

```bash
python -m compileall app
python -m ruff check .
```

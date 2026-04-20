# AgentHub Backend

FastAPI backend scaffold for the AgentHub frontend.

## Stack

- FastAPI
- MongoDB with Motor
- Pydantic v2
- OOP layered architecture

## Architecture Patterns

- Repository Pattern: database access is isolated in `app/repositories`.
- Service Layer Pattern: business logic lives in `app/services`.
- Unit of Work Pattern: request-level access to repositories is grouped in `app/db/unit_of_work.py`.
- Singleton-style Client: MongoDB client lifecycle is owned by `MongoDatabase`.
- Factory Pattern: `app/factories/service_factory.py` wires services from repositories.

## Setup

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

# seerai

Observer service for LLM chat interactions. Any client can POST chat events (user messages, AI responses, errors) and browse them through a web dashboard.

**Live:** https://seerai-430011644943.europe-west1.run.app/

## API

### Ingest

**`POST /api/ingest`** — Record a single chat event.

```json
{
  "user_id": "alice",
  "session_id": "conv-42",
  "event_type": "user_message",
  "content": "What is GDPR?",
  "timestamp": "2026-04-10T10:30:00Z",
  "metadata": {"source": "slack-bot"}
}
```

`event_type` is one of: `user_message`, `ai_message`, `error`.
`timestamp` is optional — client-side time when the event occurred. Defaults to server receive time if omitted.
`metadata` is optional — use it for model name, token counts, latency, or anything else.

Returns:

```json
{
  "user_id": "alice",
  "session_id": "conv-42",
  "event_type": "user_message",
  "content": "What is GDPR?",
  "metadata": {"source": "slack-bot"},
  "event_id": "1ce180e9-46f0-4bce-9385-7e3d9d05a022",
  "timestamp": "2026-04-10T10:31:16.037886Z"
}
```

**`POST /api/ingest/batch`** — Record multiple events at once. Body is a JSON array of the same shape.

### Query

**`GET /api/users`** — List all users, most recently active first.

**`GET /api/users/{user_id}/sessions`** — List sessions for a user, most recent first.

**`GET /api/users/{user_id}/sessions/{session_id}`** — Full session with all events in chronological order.

### Dashboard

**`GET /`** — Users list.
**`GET /sessions/{user_id}`** — Sessions for a user.
**`GET /session/{user_id}/{session_id}`** — Chat-style conversation view.

## Quick start

```bash
# ingest a conversation
curl -X POST https://seerai-430011644943.europe-west1.run.app/api/ingest \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"demo","session_id":"s1","event_type":"user_message","content":"hello"}'

# view it
open https://seerai-430011644943.europe-west1.run.app/
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
gcloud auth application-default login   # one-time, for Firestore

uvicorn main:app --reload               # http://localhost:8000
pytest                                  # 20 tests
ruff check . && ruff format .           # lint
```

## Deploy

```bash
gcloud run deploy seerai --source . --project=covenance-469421 --region=europe-west1
```

## Stack

FastAPI, Firestore, Cloud Run. Python 3.13.

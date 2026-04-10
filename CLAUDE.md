# seerai — LLM Chat Observer

FastAPI service that ingests and displays LLM chat interactions. Firestore for storage. Deployed to Cloud Run.

## Commands

```bash
uvicorn main:app --reload          # local dev server
pytest                             # run tests
ruff check . && ruff format .      # lint
```

## Architecture

- `POST /api/ingest` — record chat events
- `GET /api/users`, `/api/users/{id}/sessions`, etc. — query data
- `GET /`, `/sessions/{id}`, `/session/{uid}/{sid}` — HTML dashboard
- Firestore: `users/{uid}/sessions/{sid}/events/{eid}` hierarchy

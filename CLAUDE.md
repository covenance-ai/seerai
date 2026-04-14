# seerai — LLM Chat Observer

FastAPI service that ingests and displays LLM chat interactions. Firestore for storage. Deployed to Cloud Run.

## Commands

```bash
uvicorn main:app --reload          # local dev server (auto-detects local data)
pytest                             # run tests
ruff check . && ruff format .      # lint
python -m seerai.snapshot          # download Firestore → data/snapshot.json
python -m seerai.plausibility      # check local data plausibility
python -m seerai.plausibility --fix # normalize violations in-place
```

## Architecture

- `POST /api/ingest` — record chat events
- `GET /api/users`, `/api/users/{id}/sessions`, etc. — query data
- `GET /`, `/sessions/{id}`, `/session/{uid}/{sid}` — HTML dashboard
- Firestore: `users/{uid}/sessions/{sid}/events/{eid}` hierarchy

## Data sources

Switchable in the UI navbar (local/firestore toggle). Auto-detects local if `data/snapshot.json` exists.
- `seerai/local_client.py` — duck-types Firestore Client API backed by JSON
- `seerai/snapshot.py` — downloads all Firestore data to `data/snapshot.json`
- `GET/POST /api/datasource` — runtime switching

## Current focus

Building demo with mock data. Most sessions are generated without events — 5 archetype sessions with real conversations serve as fallback content matched by `(provider, utility)`. See `seerai/archetypes.py`. Work locally first, sync to Firestore when needed.

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

## Infrastructure

### GCP

| Resource | Value |
|----------|-------|
| Project | `covenance-469421` (number `430011644943`) |
| Region | `europe-west1` |
| Cloud Run service | `seerai` |
| Service URL | https://seerai-430011644943.europe-west1.run.app/ |
| Service account | `430011644943-compute@developer.gserviceaccount.com` |
| Firestore | Native mode, `europe-west1` |
| Firestore collections | `users/{uid}/sessions/{sid}/events/{eid}` |
| Artifact Registry | `europe-west1-docker.pkg.dev/covenance-469421/cloud-run-source-deploy` |

### Cloud Run config

- Image: built from `Dockerfile` via `gcloud run deploy --source .`
- Port: 8080 (uvicorn)
- IAM invoker disabled (`run.googleapis.com/invoker-iam-disabled: true`) — publicly accessible
- No secrets required (Firestore auth via service account, no JWT)
- No Cloud Tasks (no async workers)

### Firestore

No setup needed — collections are created automatically on first write. The service account has default Firestore access.

Collections:
```
users/{user_id}                                    — user_id, last_active
users/{user_id}/sessions/{session_id}              — session_id, user_id, last_event_at, event_count, last_event_type
users/{user_id}/sessions/{session_id}/events/{eid} — event_id, event_type, content, metadata, timestamp
```

To inspect data: [Firestore Console](https://console.cloud.google.com/firestore/databases/-default-/data?project=covenance-469421)

To wipe all data (careful):
```bash
gcloud firestore databases delete --project=covenance-469421 --database="(default)"
# then recreate:
gcloud firestore databases create --project=covenance-469421 --location=europe-west1
```

### Deploy

Redeploy after code changes:

```bash
gcloud run deploy seerai --source . --project=covenance-469421 --region=europe-west1
```

This builds the Docker image in Cloud Build, pushes to Artifact Registry, and creates a new Cloud Run revision. Takes ~5 minutes. The `--source .` flag triggers a source-based build using the `Dockerfile`.

To check current state:

```bash
# service status
gcloud run services describe seerai --project=covenance-469421 --region=europe-west1

# recent logs
gcloud run services logs read seerai --project=covenance-469421 --region=europe-west1 --limit=50

# list revisions
gcloud run revisions list --service=seerai --project=covenance-469421 --region=europe-west1
```

To roll back to a previous revision:

```bash
gcloud run services update-traffic seerai --to-revisions=REVISION_NAME=100 \
  --project=covenance-469421 --region=europe-west1
```

### Custom domain (not yet configured)

To add `seerai.covenance.ai`:

1. Add CNAME record in GoDaddy: `seerai` → `ghs.googlehosted.com`
2. Map domain in Cloud Run:
   ```bash
   gcloud run domain-mappings create --service=seerai --domain=seerai.covenance.ai \
     --project=covenance-469421 --region=europe-west1
   ```
3. Wait for SSL certificate provisioning (~15 min)

### CI/CD (not yet configured)

No Cloud Build trigger exists yet. Deployments are manual via `gcloud run deploy`. To add auto-deploy on push, create a Cloud Build trigger pointing at this repo's `main` branch — see `autodpia/infrastructure/cloud-build/` for the pattern.

## Stack

FastAPI, Firestore, Cloud Run. Python 3.13.

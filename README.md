# DocBrain

DocBrain is a `Document360-lite` knowledge base demo built for an Azure AI Foundry interview flow.

The target architecture is intentionally `Azure-native`, with a small local safety net so the app can still boot while Azure setup is in progress:
- create docs
- publish docs
- search published docs
- ask grounded questions with citations
- see usage analytics

Azure-backed features activate once Foundry, Azure AI Search, and Blob Storage are configured.

## Current Architecture

```text
FastAPI
|- Server-rendered pages (Jinja2)
|- Article management + analytics (SQLite)
|- Azure AI Search retrieval
|- Azure AI Foundry chat + embeddings
`- Azure Blob source document storage
```

## Key Routes

### Product pages

- `/` home
- `/kb/search` search experience
- `/kb/ask` ask across the knowledge base
- `/kb/articles/{slug}` article page
- `/admin/articles` article management
- `/admin/articles/new` create article
- `/admin/analytics` analytics dashboard

### APIs

- `POST /api/v1/articles`
- `GET /api/v1/articles`
- `PUT /api/v1/articles/{article_id}`
- `POST /api/v1/articles/{article_id}/publish`
- `POST /api/v1/ingest`
- `POST /api/v1/search`
- `POST /api/v1/chat`
- `GET /api/v1/analytics/overview`
- `POST /api/v1/analytics/events`

## Local Run

```bash
cd docbrain
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

Open:
- `http://localhost:8000/`
- `http://localhost:8000/docs`

## Docker Run

```bash
cd docbrain
docker compose up --build
```

Open:
- `http://localhost:8000/`
- `http://localhost:8000/docs`

The compose file mounts `./data` into the container so your SQLite metadata survives rebuilds.
If port `8000` is already in use, run PowerShell with `$env:HOST_PORT=8001` before `docker compose up --build`.

## Azure Deploy

For the first Azure deploy from your machine:

```powershell
cd docbrain
.\scripts\push_image.ps1 -SubscriptionId "<subscription-id>" -AcrName "docbrainacr" -ImageName "docbrain" -ImageTag "latest" -AlsoTagLatest
.\scripts\deploy_container_app.ps1 -SubscriptionId "<subscription-id>" -EnvFile ".env"
```

What these scripts do:
- `push_image.ps1` logs into ACR, builds the Docker image locally, and pushes it
- `deploy_container_app.ps1` creates the Container Apps environment if needed, then creates or updates the Container App with the right secrets and environment variables

After deployment, the script prints the live Container App URL.

## GitHub Actions

The workflow in [`.github/workflows/deploy.yml`](/C:/Users/rprav/Claude/Azure/docbrain/.github/workflows/deploy.yml) reuses the same deployment logic and expects these GitHub secrets:
- `AZURE_CREDENTIALS`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_AI_PROJECT_ENDPOINT`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_KEY`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_AI_CHAT_MODEL`
- `AZURE_AI_EMBEDDING_MODEL`
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_KEY`
- `AZURE_SEARCH_INDEX`
- `AZURE_STORAGE_CONNECTION_STRING`
- `AZURE_STORAGE_CONTAINER`

### Pre-push checklist

- rotate any Azure keys that were pasted into chat or shared outside your local machine
- keep `.env`, `data/`, `.env.generated`, and local SQLite files untracked
- create the GitHub repo first, then add secrets before pushing `main`
- verify that the live app URL and `/ready` endpoint are healthy before turning CI loose on it

### Create `AZURE_CREDENTIALS`

The current workflow uses `azure/login` with a service principal secret. To create the JSON GitHub expects, run:

```powershell
az ad sp create-for-rbac `
  --name "docbrain-github-actions" `
  --role Contributor `
  --scopes /subscriptions/16a5b067-d3f7-45de-878b-64ca37903a03/resourceGroups/rg-docbrain `
  --json-auth
```

Copy the JSON output into the GitHub secret named `AZURE_CREDENTIALS`.

Safer note:
- official Azure Login guidance recommends OIDC over long-lived service principal secrets when possible
- this workflow is already compatible with a future OIDC switch because it requests `id-token: write`
- if you stay with `AZURE_CREDENTIALS`, keep the service principal scoped to `rg-docbrain` only and rotate it if the JSON is ever exposed

## Environment

Copy [`.env.example`](/C:/Users/rprav/Claude/Azure/docbrain/.env.example) to `.env` and fill values as needed.

`SQLITE_DB_PATH` keeps article metadata and analytics available locally.
Azure AI Foundry, Azure AI Search, and Blob Storage settings unlock search, grounded chat, and source-document storage.

## Interview Story

This repo is aiming at a simple demo narrative:

1. Create or ingest documentation
2. Publish it to a knowledge base
3. Search across published content
4. Ask grounded questions
5. Review analytics for views, searches, zero-result queries, and AI usage

## Azure Next

Planned Azure-first upgrades:
- add 1-2 Azure MCP integrations for enrichment and analytics copilots
- tighten ingest-time enrichment around Foundry and Azure Language tooling
- move the remaining local metadata-only pieces behind Azure-friendly deployment boundaries

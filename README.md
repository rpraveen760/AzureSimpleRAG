# DocBrain

DocBrain is an Azure-native knowledge base demo built for an Azure AI Foundry interview flow.

Live demo: [DocBrain on Azure Container Apps](https://docbrain-app.wittycliff-f46aafc4.eastus2.azurecontainerapps.io)

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
|- Article management + analytics (Azure PostgreSQL or SQLite fallback)
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

## Demo Walkthrough

Use this flow in the interview:

1. Open the home page and show the public knowledge base shell.
2. Create a draft article from `/admin/articles/new`.
3. Publish it and open the live article page.
4. Ask a grounded question from the article page or `/kb/ask`.
5. Show `/kb/search` returning article-level results.
6. Finish on `/admin/analytics` to show views, searches, and AI usage.

If you want a fast local seed, the [`sample_docs/`](sample_docs/) folder includes a couple of markdown docs that match the current Azure architecture story.

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

The workflow in [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) reuses the same deployment logic and expects these GitHub secrets:
- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
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
- `DATABASE_URL`

### Pre-push checklist

- rotate any Azure keys that were pasted into chat or shared outside your local machine
- keep `.env`, `data/`, `.env.generated`, and local SQLite files untracked
- create the GitHub repo first, then add secrets before pushing `main`
- verify that the live app URL and `/ready` endpoint are healthy before turning CI loose on it
- remove any leftover `AZURE_CREDENTIALS` secret after OIDC is working so GitHub Actions is no longer carrying a long-lived Azure secret

### Configure Azure OIDC For GitHub Actions

Create a service principal scoped to your subscription or resource group:

```powershell
az ad sp create-for-rbac `
  --name "docbrain-github-actions" `
  --role Contributor `
  --scopes /subscriptions/16a5b067-d3f7-45de-878b-64ca37903a03
```

Then add a federated credential that trusts your GitHub repo on `main`:

```powershell
$params = @'
{
  "name": "github-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:rpraveen760/AzureSimpleRAG:ref:refs/heads/main",
  "description": "GitHub Actions OIDC for AzureSimpleRAG main branch deployments",
  "audiences": [
    "api://AzureADTokenExchange"
  ]
}
'@

az ad app federated-credential create `
  --id "<app-id>" `
  --parameters $params
```

Add these GitHub secrets:
- `AZURE_CLIENT_ID`: the app ID from the service principal
- `AZURE_TENANT_ID`: your Azure tenant ID
- `AZURE_SUBSCRIPTION_ID`: your Azure subscription ID

This is the recommended setup for `azure/login` because GitHub exchanges an OIDC token for Azure access at runtime instead of storing a long-lived JSON credential in the repo secrets.

## Environment

Copy [`.env.example`](.env.example) to `.env` and fill values as needed.

`DATABASE_URL` is the recommended path for Azure PostgreSQL and now backs article metadata plus analytics.
`SQLITE_DB_PATH` remains as a local fallback when `DATABASE_URL` is empty.
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
- replace per-request DB connections with pooling once the Azure PostgreSQL instance is in place

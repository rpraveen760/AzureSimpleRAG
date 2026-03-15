# Azure Architecture Overview

DocBrain is designed to be Azure-native.

## Core Services

- Azure OpenAI powers chat completions and embedding generation.
- Azure AI Search stores chunked article content for hybrid search.
- Azure Blob Storage stores uploaded source documents.
- Azure Container Apps hosts the deployed web application.

## Retrieval Flow

1. An article or uploaded document is chunked.
2. Each chunk is embedded with Azure OpenAI.
3. The chunk text and vector are indexed into Azure AI Search.
4. User queries run as hybrid search using keyword and vector relevance.
5. The chat layer grounds answers on the retrieved chunks and returns citations.

## Interview Talking Points

- The app is Azure-native but still locally runnable for development.
- Search and chat degrade cleanly when Azure integrations are not configured.
- The current tradeoff is that article metadata and analytics remain on SQLite.
- A production next step would be Azure SQL or PostgreSQL for durable metadata.


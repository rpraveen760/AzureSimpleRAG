# Getting Started with DocBrain

DocBrain is an Azure-native knowledge base demo built to show the core Document360-style workflow:

- create and publish articles
- search across published content
- ask grounded questions with citations
- review usage analytics

For the interview demo, the fastest path is:

1. Create or ingest a document.
2. Publish it to the knowledge base.
3. Search for a key phrase from the document.
4. Ask a question and highlight the citations.
5. Open the analytics dashboard to show the resulting events.

The product layer is intentionally small, but the architecture is production-shaped:

- FastAPI for APIs and server-rendered pages
- Azure AI Search for hybrid retrieval
- Azure OpenAI for embeddings and chat
- Azure Blob Storage for uploaded source files
- SQLite for local article metadata and analytics


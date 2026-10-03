# UKNest AI 🇬🇧

An evidence-based assistant that helps newcomers navigate everyday life in the UK. It combines retrieval over official GOV.UK guidance, MCP tools for live local lookups, and source-cited answers with "last updated" dates.

> ⚠️ Informational only. Not legal or immigration advice. Always check the linked GOV.UK guidance or speak to an OISC-regulated adviser.

## Status

v0.1 in progress (7-day build).

| Day | Focus | Status |
|---|---|---|
| 1 | Repo, Qdrant in Docker, GOV.UK ingestion | 🟡 |
| 2 | Chunking, embeddings, retrieval, cited answers | ⬜ |
| 3 | MCP server (guidance search, postcode, nearby services) | ⬜ |
| 4 | Agent loop with LLM tool calling + guardrails | ⬜ |
| 5 | Streamlit UI | ⬜ |
| 6 | Docker Compose for all services | ⬜ |
| 7 | Deploy + README polish | ⬜ |

## Run in GitHub Codespaces (no local install)

Click **Code → Codespaces → Create codespace on main**. Dependencies install automatically, then run:

```bash
docker compose up -d
python -m ingest.fetch_govuk
```

## Quick start locally (Day 1)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

docker compose up -d             # starts Qdrant on :6333
python -m ingest.fetch_govuk     # writes data/raw/govuk_docs.jsonl
```

Qdrant dashboard: http://localhost:6333/dashboard

## Data sources

GOV.UK content via the Content API, used under the Open Government Licence v3.0.

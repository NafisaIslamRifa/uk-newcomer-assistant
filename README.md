# UKNest AI 🇬🇧

An evidence-based assistant that helps newcomers navigate everyday life in the UK. It combines retrieval over official GOV.UK guidance, MCP tools for live local lookups, and source-cited answers with "last updated" dates.


```

Qdrant dashboard: http://localhost:6333/dashboard

## Data sources

GOV.UK content via the Content API, used under the Open Government Licence v3.0.

## Run everything with Docker

```bash
cp .env.example .env      # add your LLM_API_KEY
docker compose up --build
```

Then open http://localhost:8501.

| Service | What it does | Port |
|---|---|---|
| `qdrant` | Vector database holding the GOV.UK chunks | 6333 |
| `init` | One-off job: fetches GOV.UK pages and builds the index if it's empty | – |
| `mcp` | MCP server exposing the three tools over HTTP | 8000 |
| `app` | Streamlit web interface, talks to `mcp` over HTTP | 8501 |

Rebuild the index after changing sources: `docker compose run --rm -e FORCE_REINDEX=1 init`

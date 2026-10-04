# UKNest AI - Day 6 setup: Dockerfile, full docker-compose, start-up job
set -e
mkdir -p scripts tests && touch scripts/__init__.py
cat > Dockerfile <<'UKNEST_EOF'
# One image for every UKNest service. docker-compose runs it three ways:
#   init -> python -m scripts.bootstrap      (build the index once)
#   mcp  -> python -m mcp_server.server      (tools over HTTP)
#   app  -> streamlit run app/streamlit_app.py (the web UI, default command)

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FASTEMBED_CACHE_PATH=/models

WORKDIR /app

# Dependencies first: this layer is cached until requirements.txt changes
COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the embedding model into the image, so containers start fast
# and never download it at runtime
RUN python -c "from fastembed import TextEmbedding; \
TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/models')"

COPY . .

# Run as a normal user, not root
RUN useradd --create-home --uid 1000 uknest && chown -R uknest:uknest /app /models
USER uknest

EXPOSE 8501 8000

CMD ["python", "-m", "streamlit", "run", "app/streamlit_app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
UKNEST_EOF
cat > .dockerignore <<'UKNEST_EOF'
# Keep secrets and local clutter out of the image
.env
.git
.github
.venv
venv
__pycache__
*.pyc
.pytest_cache
.devcontainer
data/processed
eval/results_*.json
docs
*.sh
UKNEST_EOF
cat > docker-compose.yml <<'UKNEST_EOF'
# UKNest AI: the whole system with one command.
#
#   docker compose up --build        start everything
#   open http://localhost:8501       the app
#   docker compose down              stop (data is kept)
#   docker compose down -v           stop and delete all data
#
#  ┌──────────┐  MCP over HTTP  ┌──────────┐   vectors   ┌──────────┐
#  │   app    │ ──────────────▶ │   mcp    │ ──────────▶ │  qdrant  │
#  │ :8501    │                 │ :8000    │             │ :6333    │
#  └──────────┘                 └──────────┘             └──────────┘
#        ▲ starts after `init` has built the index ──────────────┘

x-uknest: &uknest
  build: .
  image: uknest:latest
  env_file:
    - path: .env          # LLM_PROVIDER, LLM_API_KEY, LLM_MODEL, LLM_RPM
      required: false
  environment: &env
    QDRANT_URL: http://qdrant:6333   # service name, not localhost, inside Docker
  volumes:
    - uknest_data:/app/data

services:
  qdrant:
    image: qdrant/qdrant:latest
    container_name: uknest-qdrant
    ports:
      - "6333:6333"                  # REST API + dashboard
    volumes:
      - qdrant_data:/qdrant/storage
    restart: unless-stopped

  init:
    <<: *uknest
    container_name: uknest-init
    command: ["python", "-m", "scripts.bootstrap"]
    depends_on:
      - qdrant
    restart: "no"

  mcp:
    <<: *uknest
    container_name: uknest-mcp
    command: ["python", "-m", "mcp_server.server"]
    environment:
      <<: *env
      MCP_TRANSPORT: streamable-http
      MCP_HOST: 0.0.0.0
      MCP_PORT: "8000"
    ports:
      - "8000:8000"                  # optional: lets MCP Inspector connect from outside
    depends_on:
      init:
        condition: service_completed_successfully
    healthcheck:
      test: ["CMD", "python", "-c", "import socket; socket.create_connection(('localhost', 8000), 2)"]
      interval: 5s
      timeout: 3s
      retries: 20
      start_period: 10s
    restart: unless-stopped

  app:
    <<: *uknest
    container_name: uknest-app
    environment:
      <<: *env
      MCP_SERVER_URL: http://mcp:8000/mcp   # talk to the MCP container over HTTP
    ports:
      - "8501:8501"
    depends_on:
      mcp:
        condition: service_healthy
    restart: unless-stopped

volumes:
  qdrant_data:
  uknest_data:
UKNEST_EOF
cat > scripts/bootstrap.py <<'UKNEST_EOF'
"""One-off start-up job: make sure Qdrant has the GOV.UK index.

Runs as the `init` service in docker-compose before the MCP server and app start.
- Waits for Qdrant to accept connections.
- If the collection already has data, does nothing (fast restarts).
- Otherwise fetches GOV.UK pages (only if they're not already on disk) and
  builds the index.

Set FORCE_REINDEX=1 to rebuild anyway (e.g. after editing ingest/sources.py).

Usage:
    python -m scripts.bootstrap
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from qdrant_client import QdrantClient

from rag.config import COLLECTION, QDRANT_URL, RAW_DOCS_PATH


def wait_for_qdrant(url: str, attempts: int = 30, delay: float = 2.0) -> QdrantClient:
    for i in range(1, attempts + 1):
        try:
            client = QdrantClient(url=url, timeout=5)
            client.get_collections()
            print(f"Qdrant is ready at {url}")
            return client
        except Exception as exc:  # not up yet
            print(f"Waiting for Qdrant ({i}/{attempts}): {type(exc).__name__}")
            time.sleep(delay)
    sys.exit(f"Qdrant did not become ready at {url}")


def index_is_ready(client: QdrantClient) -> bool:
    if not client.collection_exists(COLLECTION):
        return False
    return client.count(COLLECTION).count > 0


def main(client: QdrantClient | None = None, fetch=None, build=None) -> str:
    client = client or wait_for_qdrant(QDRANT_URL)
    force = os.getenv("FORCE_REINDEX", "").lower() in ("1", "true", "yes")

    if index_is_ready(client) and not force:
        n = client.count(COLLECTION).count
        print(f"Index '{COLLECTION}' already has {n} chunks. Nothing to do.")
        return "skipped"

    if not Path(RAW_DOCS_PATH).exists():
        print("No GOV.UK data on disk yet, fetching it...")
        if fetch is None:
            from ingest.fetch_govuk import main as fetch
        fetch()

    print("Building the search index...")
    if build is None:
        from rag.build_index import build_index as build
    build(client=client)
    return "built"


if __name__ == "__main__":
    main()
UKNEST_EOF
cat > rag/embeddings.py <<'UKNEST_EOF'
"""Embeddings with fastembed (ONNX, CPU, no PyTorch).

bge models work best when queries and passages are embedded differently,
so we expose two functions. fastembed's query_embed adds the right
instruction prefix for us.
"""

from __future__ import annotations

import os
from functools import lru_cache

from fastembed import TextEmbedding

from rag.config import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def get_model() -> TextEmbedding:
    # First call downloads the model and caches it. In Docker the model is baked into
    # the image at FASTEMBED_CACHE_PATH, so containers start without downloading.
    return TextEmbedding(model_name=EMBEDDING_MODEL,
                         cache_dir=os.getenv("FASTEMBED_CACHE_PATH") or None)


def embed_passages(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in get_model().passage_embed(texts)]


def embed_query(text: str) -> list[float]:
    return next(iter(get_model().query_embed([text]))).tolist()
UKNEST_EOF
cat > tests/test_bootstrap.py <<'UKNEST_EOF'
"""Start-up job: builds the index only when needed."""

from qdrant_client import QdrantClient, models

from rag.config import COLLECTION
from scripts import bootstrap


def test_builds_when_collection_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "RAW_DOCS_PATH", str(tmp_path / "docs.jsonl"))
    calls = []
    out = bootstrap.main(client=QdrantClient(":memory:"),
                         fetch=lambda: calls.append("fetch"),
                         build=lambda client: calls.append("build"))
    assert out == "built" and calls == ["fetch", "build"]


def test_skips_when_index_exists(monkeypatch):
    monkeypatch.delenv("FORCE_REINDEX", raising=False)
    c = QdrantClient(":memory:")
    c.create_collection(COLLECTION, vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE))
    c.upsert(COLLECTION, points=[models.PointStruct(id=1, vector=[1, 0], payload={})])
    assert bootstrap.main(client=c, fetch=None, build=lambda client: 1 / 0) == "skipped"


def test_force_reindex_skips_fetch_if_data_on_disk(tmp_path, monkeypatch):
    raw = tmp_path / "docs.jsonl"
    raw.write_text("{}")
    monkeypatch.setattr(bootstrap, "RAW_DOCS_PATH", str(raw))
    monkeypatch.setenv("FORCE_REINDEX", "1")
    c = QdrantClient(":memory:")
    c.create_collection(COLLECTION, vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE))
    c.upsert(COLLECTION, points=[models.PointStruct(id=1, vector=[1, 0], payload={})])
    calls = []
    assert bootstrap.main(client=c, fetch=lambda: calls.append("fetch"),
                          build=lambda client: calls.append("build")) == "built"
    assert calls == ["build"]
UKNEST_EOF
grep -q "Run everything with Docker" README.md || cat >> README.md <<'UKNEST_EOF'

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
UKNEST_EOF
echo "✅ Day 6 files created"; ls Dockerfile .dockerignore docker-compose.yml scripts
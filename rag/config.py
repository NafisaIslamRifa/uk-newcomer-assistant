"""Central settings, read from .env so nothing is hard-coded."""

import os

from dotenv import load_dotenv

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
# Optional: Qdrant Cloud API key
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None
# Optional: embedded mode. If set, Qdrant runs inside the Python process and stores
# data in this folder, so no Qdrant server is needed (used for the free public demo).
QDRANT_PATH = os.getenv("QDRANT_PATH") or None
COLLECTION = os.getenv("QDRANT_COLLECTION", "uk_guidance")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

RAW_DOCS_PATH = "data/raw/govuk_docs.jsonl"
CHUNKS_PATH = "data/processed/chunks.jsonl"

# Chunking: ~350 words fits well within bge-small's 512-token limit
CHUNK_MAX_WORDS = 350
CHUNK_OVERLAP_WORDS = 50

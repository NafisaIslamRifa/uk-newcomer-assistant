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

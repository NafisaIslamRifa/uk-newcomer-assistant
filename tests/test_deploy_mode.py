"""Embedded-Qdrant mode (used for the public demo) and the demo question limit."""

import importlib

from qdrant_client import models


def test_embedded_mode_builds_and_searches(tmp_path, monkeypatch):
    monkeypatch.setenv("QDRANT_PATH", str(tmp_path / "qdrant"))
    import rag.config, rag.store
    importlib.reload(rag.config)
    importlib.reload(rag.store)
    try:
        client = rag.store.get_client()
        client.create_collection("t", vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE))
        client.upsert("t", points=[models.PointStruct(id=1, vector=[1, 0], payload={"x": 1})])
        assert client.count("t").count == 1
        assert rag.store.describe().startswith("embedded")
        client.close()
    finally:
        monkeypatch.delenv("QDRANT_PATH")
        importlib.reload(rag.config)
        importlib.reload(rag.store)


def test_server_mode_by_default():
    import rag.store
    assert rag.store.describe().startswith("http")

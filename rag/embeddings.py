"""Embeddings with fastembed (ONNX, CPU, no PyTorch).

bge models work best when queries and passages are embedded differently,
so we expose two functions. fastembed's query_embed adds the right
instruction prefix for us.
"""

from __future__ import annotations

from functools import lru_cache

from fastembed import TextEmbedding

from rag.config import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def get_model() -> TextEmbedding:
    # First call downloads the model (~130 MB) and caches it
    return TextEmbedding(model_name=EMBEDDING_MODEL)


def embed_passages(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in get_model().passage_embed(texts)]


def embed_query(text: str) -> list[float]:
    return next(iter(get_model().query_embed([text]))).tolist()

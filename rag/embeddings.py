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


# Chunks embedded per batch. fastembed's default (256) needs several GB of RAM for long
# chunks, which crashes small hosts like Streamlit Community Cloud; 16 stays well under 500 MB.
BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "16"))


def embed_passages(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in get_model().passage_embed(texts, batch_size=BATCH_SIZE)]


def embed_query(text: str) -> list[float]:
    return next(iter(get_model().query_embed([text]))).tolist()

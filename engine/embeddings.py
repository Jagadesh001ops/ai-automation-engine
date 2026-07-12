from __future__ import annotations

from functools import lru_cache
from typing import List

_MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(_MODEL_NAME)


def embed(text: str) -> List[float]:
    """Return a normalised float embedding for *text* using a local model.

    No external API call is made — the model runs entirely on-device.
    The first call downloads the model (~22 MB); subsequent calls use the
    cached instance.
    """
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_batch(texts: List[str]) -> List[List[float]]:
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, batch_size=32)
    return [v.tolist() for v in vectors]

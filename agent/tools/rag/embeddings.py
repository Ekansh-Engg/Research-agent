from functools import lru_cache

from sentence_transformers import SentenceTransformer


@lru_cache
def get_embedder() -> SentenceTransformer:
    return SentenceTransformer("BAAI/bge-small-en-v1.5")


def embed_text(text: str) -> list[float]:
    model = get_embedder()
    return model.encode(text, normalize_embeddings=True).tolist()
import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from agent.tools.rag.embeddings import embed_text

COLLECTION_NAME = "documents"
VECTOR_SIZE = 384  # BAAI/bge-small-en-v1.5 output dimension


def get_qdrant_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(url="http://qdrant:6333")


async def ensure_collection() -> None:
    client = get_qdrant_client()
    collections = await client.get_collections()
    exists = any(c.name == COLLECTION_NAME for c in collections.collections)
    if not exists:
        await client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


async def index_document(text: str, source: str) -> None:
    await ensure_collection()
    client = get_qdrant_client()

    vector = embed_text(text)
    point = PointStruct(
        id=str(uuid.uuid4()),
        vector=vector,
        payload={"text": text, "source": source},
    )
    await client.upsert(collection_name=COLLECTION_NAME, points=[point])


async def search_documents(query: str, limit: int = 3) -> list[dict]:
    await ensure_collection()
    client = get_qdrant_client()

    query_vector = embed_text(query)
    response = await client.query_points(
        collection_name=COLLECTION_NAME, query=query_vector, limit=limit
    )
    return [
        {"text": p.payload["text"], "source": p.payload["source"], "score": p.score}
        for p in response.points
    ]
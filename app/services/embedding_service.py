"""Embedding-based market matching via Qdrant vector search.

Embeds market questions using a local model (fastembed/BGE), stores vectors
in Qdrant, and finds semantically similar cross-platform market pairs.
"""

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)
from fastembed import TextEmbedding

from app.config import settings

logger = structlog.get_logger()

_embedding_model: TextEmbedding | None = None
_qdrant_client: QdrantClient | None = None


def get_embedding_model() -> TextEmbedding:
    """Lazy-load the embedding model."""
    global _embedding_model
    if _embedding_model is None:
        logger.info("embedding_model_loading", model=settings.EMBEDDING_MODEL)
        _embedding_model = TextEmbedding(model_name=settings.EMBEDDING_MODEL)
        logger.info("embedding_model_ready")
    return _embedding_model


def get_qdrant() -> QdrantClient:
    """Lazy-load the Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(
            url=settings.QDRANT_ENDPOINT,
            api_key=settings.QDRANT_API_KEY,
        )
        _ensure_collection(_qdrant_client)
        logger.info("qdrant_connected", endpoint=settings.QDRANT_ENDPOINT)
    return _qdrant_client


def _ensure_collection(client: QdrantClient) -> None:
    """Create the collection if it doesn't exist."""
    collections = [c.name for c in client.get_collections().collections]
    if settings.QDRANT_COLLECTION not in collections:
        client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config=VectorParams(
                size=settings.EMBEDDING_DIMENSION,
                distance=Distance.COSINE,
            ),
        )
        logger.info("qdrant_collection_created", name=settings.QDRANT_COLLECTION)
    # Ensure payload index exists for filtered search
    client.create_payload_index(
        collection_name=settings.QDRANT_COLLECTION,
        field_name="platform_id",
        field_schema=PayloadSchemaType.INTEGER,
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts using the local model."""
    model = get_embedding_model()
    embeddings = list(model.embed(texts))
    return [e.tolist() for e in embeddings]


def upsert_markets(markets: list[dict]) -> int:
    """Upsert market embeddings into Qdrant.

    Each market dict must have: id, question, platform_id, category, end_date.
    Returns number of points upserted.
    """
    if not markets:
        return 0

    client = get_qdrant()
    questions = [m["question"] for m in markets]
    vectors = embed_texts(questions)

    points = [
        PointStruct(
            id=m["id"],
            vector=vec,
            payload={
                "question": m["question"],
                "platform_id": m["platform_id"],
                "category": m.get("category"),
                "end_date": m.get("end_date"),
            },
        )
        for m, vec in zip(markets, vectors)
    ]

    # Upsert in batches of 100
    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        client.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=batch,
        )

    logger.info("qdrant_markets_upserted", count=len(points))
    return len(points)


def find_cross_platform_matches(
    market_id: int,
    platform_id: int,
    threshold: float | None = None,
    limit: int = 10,
) -> list[dict]:
    """Find markets on OTHER platforms similar to the given market.

    Returns list of {id, score, question, platform_id, category, end_date}.
    """
    if threshold is None:
        threshold = settings.EMBEDDING_MATCH_THRESHOLD

    client = get_qdrant()

    # Get the vector for this market
    points = client.retrieve(
        collection_name=settings.QDRANT_COLLECTION,
        ids=[market_id],
        with_vectors=True,
    )
    if not points:
        return []

    vector = points[0].vector

    # Search for similar markets on different platforms
    results = client.query_points(
        collection_name=settings.QDRANT_COLLECTION,
        query=vector,
        query_filter=Filter(
            must_not=[
                FieldCondition(key="platform_id", match=MatchValue(value=platform_id)),
            ]
        ),
        limit=limit,
        score_threshold=threshold,
    )

    return [
        {
            "id": hit.id,
            "score": hit.score,
            "question": hit.payload.get("question"),
            "platform_id": hit.payload.get("platform_id"),
            "category": hit.payload.get("category"),
            "end_date": hit.payload.get("end_date"),
        }
        for hit in results.points
    ]


def find_all_cross_platform_candidates(
    platform_ids: list[int],
    threshold: float | None = None,
    limit_per_market: int = 5,
) -> list[dict]:
    """Find all cross-platform candidate pairs above threshold.

    Iterates through markets on each platform and finds matches on other
    platforms. Returns deduplicated candidates with scores.
    """
    if threshold is None:
        threshold = settings.EMBEDDING_MATCH_THRESHOLD

    client = get_qdrant()
    seen_pairs: set[tuple[int, int]] = set()
    candidates: list[dict] = []

    for pid in platform_ids:
        # Scroll through all markets on this platform
        offset = None
        while True:
            scroll_result = client.scroll(
                collection_name=settings.QDRANT_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="platform_id", match=MatchValue(value=pid)),
                    ]
                ),
                limit=100,
                offset=offset,
                with_vectors=True,
                with_payload=True,
            )
            points, next_offset = scroll_result

            for point in points:
                matches = client.query_points(
                    collection_name=settings.QDRANT_COLLECTION,
                    query=point.vector,
                    query_filter=Filter(
                        must_not=[
                            FieldCondition(
                                key="platform_id",
                                match=MatchValue(value=pid),
                            ),
                        ]
                    ),
                    limit=limit_per_market,
                    score_threshold=threshold,
                )

                for hit in matches.points:
                    pair_key = (min(point.id, hit.id), max(point.id, hit.id))
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)

                    candidates.append({
                        "market_a_id": pair_key[0],
                        "market_a_question": point.payload["question"] if point.id == pair_key[0] else hit.payload["question"],
                        "market_a_platform_id": point.payload["platform_id"] if point.id == pair_key[0] else hit.payload["platform_id"],
                        "market_b_id": pair_key[1],
                        "market_b_question": hit.payload["question"] if hit.id == pair_key[1] else point.payload["question"],
                        "market_b_platform_id": hit.payload["platform_id"] if hit.id == pair_key[1] else point.payload["platform_id"],
                        "embedding_score": round(hit.score, 4),
                    })

            if next_offset is None:
                break
            offset = next_offset

    candidates.sort(key=lambda c: c["embedding_score"], reverse=True)
    logger.info("embedding_candidates_found", count=len(candidates))
    return candidates

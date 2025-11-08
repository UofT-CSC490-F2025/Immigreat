from typing import List, Dict, Any, Optional

try:
    # sentence-transformers provides a lightweight CrossEncoder wrapper
    from sentence_transformers import CrossEncoder
except ImportError as e:
    raise ImportError(
        "sentence-transformers is required for cross-encoder reranking. "
        "Install it with `pip install sentence-transformers`."
    ) from e


_MODEL_CACHE: Dict[str, CrossEncoder] = {}


def _get_model(model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> CrossEncoder:
    """Load and cache a CrossEncoder by name.

    Defaults to a small, fast MS MARCO cross-encoder suitable for reranking.
    """
    model = _MODEL_CACHE.get(model_name)
    if model is None:
        model = CrossEncoder(model_name, trust_remote_code=False)
        _MODEL_CACHE[model_name] = model
    return model


def rerank(
    query: str,
    passages: List[str],
    top_k: Optional[int] = None,
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
) -> List[Dict[str, Any]]:
    """Rerank passages for a query using a Cross-Encoder.

    Args:
        query: User question or search query string.
        passages: List of passage strings to rerank.
        top_k: If provided, return only the top_k highest-scoring passages.
        model_name: Hugging Face model id for CrossEncoder.

    Returns:
        A list of dicts sorted by descending score:
        [{"text": str, "score": float, "index": int}, ...]
    """
    if not passages:
        return []

    model = _get_model(model_name)
    pairs = [(query, p) for p in passages]
    scores = model.predict(pairs)  # type: ignore[attr-defined]

    ranked = [
        {"text": passages[i], "score": float(scores[i]), "index": i}
        for i in range(len(passages))
    ]
    ranked.sort(key=lambda x: x["score"], reverse=True)

    if top_k is not None:
        ranked = ranked[: max(0, int(top_k))]
    return ranked


def rerank_candidates(
    query: str,
    candidates: List[Dict[str, Any]],
    text_key: str = "content",
    top_k: Optional[int] = None,
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
) -> List[Dict[str, Any]]:
    """Rerank a list of candidate dicts by a text field.

    This is convenient when your retrieval returns rows with a `content` field
    (e.g., from Postgres) and you want the same objects back, sorted by a
    Cross-Encoder relevance score.

    Args:
        query: The user query string.
        candidates: List of dicts each containing a text field (default: "content").
        text_key: Key in each candidate dict that stores the text to rank.
        top_k: Return only the top_k items if provided.
        model_name: Cross-Encoder model id.

    Returns:
        The same candidate dicts, sorted by descending rerank_score, with an
        added key "rerank_score" for each element.
    """
    if not candidates:
        return []

    passages = [str(c.get(text_key, "")) for c in candidates]
    ranked = rerank(query, passages, top_k=None, model_name=model_name)

    # Map original index -> score
    score_map = {r["index"]: r["score"] for r in ranked}

    # Attach scores to candidates
    enriched = []
    for i, c in enumerate(candidates):
        c_copy = dict(c)
        c_copy["rerank_score"] = float(score_map.get(i, 0.0))
        enriched.append(c_copy)

    # Sort by score desc and slice
    enriched.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
    if top_k is not None:
        enriched = enriched[: max(0, int(top_k))]
    return enriched


__all__ = [
    "rerank",
    "rerank_candidates",
]


if __name__ == "__main__":
    # Minimal local smoke test
    q = "What documents are required for a Canadian study permit?"
    docs = [
        "Applicants must provide proof of acceptance and identity.",
        "Visitor visas require different documentation and processing times.",
        "Work permits have distinct eligibility requirements.",
        "Study permit requires proof of financial support and letter of acceptance.",
    ]
    for item in rerank(q, docs, top_k=3):
        print(f"score={item['score']:.4f} | {item['text']}")

"""
fusion.py — Reciprocal Rank Fusion (RRF) of several ranked chunk lists.

Pure function, no IO: takes the ranked lists produced by the semantic and BM25
retrievers and merges them into one ranking.

RRF idea: don't trust any single score scale (cosine similarity vs BM25 score
are incomparable). Instead only the RANK matters — a chunk that ranks 1st in
one list gets 1/(k + 1), 2nd gets 1/(k + 2), etc. Summing across lists rewards
chunks that rank well in BOTH retrievers, which is exactly what hybrid search
wants: a chunk both retrievers agree on beats one only one of them likes.
"""

from collections import defaultdict

from app.retriever import RetrievedChunk


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievedChunk]],
    rrf_k: int = 60,
) -> list[RetrievedChunk]:
    """Fuse ranked chunk lists with RRF; returns one deduplicated ranking.

    Args:
        ranked_lists: each list is chunks in descending relevance order
            (best first), as returned by a retriever.
        rrf_k: the smoothing constant in 1/(rrf_k + rank). Default 60 is the
            common choice (from Cormack et al.). Larger k flattens the rank
            advantage; smaller k sharpens it.

    Returns:
        Chunks sorted by fused RRF score, best first. Duplicates (the same
        chunk present in more than one list) appear exactly once, with their
        contributions summed. The chunk's .score is overwritten with its fused
        RRF score (original per-retriever scores are not comparable anyway).
    """

    # Deduplicate by chunk identity. RetrievedChunk has no id field, but
    # (file_path, node_type, name) is the exact triple chunk ids are keyed on
    # (see chunking.py), so it uniquely identifies a chunk across retrievers.
    def identity(chunk: RetrievedChunk) -> tuple[str, str, str]:
        return (chunk.file_path, chunk.node_type, chunk.name)

    fused_scores: dict[tuple[str, str, str], float] = defaultdict(float)
    chunks_by_id: dict[tuple[str, str, str], RetrievedChunk] = {}

    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked, start=1):  # rank is 1-based
            key = identity(chunk)
            fused_scores[key] += 1.0 / (rrf_k + rank)
            chunks_by_id.setdefault(key, chunk)  # keep first occurrence

    fused = list(chunks_by_id.values())
    fused.sort(key=lambda c: fused_scores[identity(c)], reverse=True)

    for chunk in fused:
        chunk.score = fused_scores[identity(chunk)]
    return fused

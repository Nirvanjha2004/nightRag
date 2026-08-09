"""
bm25_retriever.py — lexical (BM25) retriever over the same chunks the semantic
retriever searches. Pure stdlib (math + collections), no new dependency.

Why BM25 alongside the vector index: semantic search is great at paraphrases
but can miss exact identifiers/symbol names. BM25 is the classic sparse
lexical baseline that nails exact term matches (e.g. a function named
`_normalize`). Hybrid retrieval fuses the two — see hybrid_retriever.py.

Flow:
    BM25Index      — tokenizes documents, precomputes idf, scores a query.
    BM25Retriever  — thin wrapper that maps scored doc indices back to
                     RetrievedChunk (same shape the semantic retriever emits,
                     so the hybrid retriever can fuse the two lists directly).
"""

import math
import re
from collections import Counter
from dataclasses import replace

from app.retriever import RetrievedChunk

# Token: runs of letters/digits/underscore — keeps snake_case identifiers whole
# (a real token in Python code) while stripping operators and punctuation.
_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")

# Okapi BM25 standard tunings. k1 controls term-frequency saturation; b the
# amount of length normalization. These are the defaults everyone ships with.
_K1 = 1.5
_B = 0.75


def tokenize(text: str) -> list[str]:
    """Lowercase tokens of a chunk or query."""
    return [t.lower() for t in _TOKEN_RE.findall(text)]


class BM25Index:
    """In-memory Okapi BM25 index over a fixed list of documents."""

    def __init__(self, documents: list[str], k1: float = _K1, b: float = _B):
        self.k1 = k1
        self.b = b
        self.documents = list(documents)

        tokenized = [tokenize(doc) for doc in self.documents]
        doc_lengths = [len(tokens) for tokens in tokenized]
        num_docs = len(self.documents)

        # Document frequency: in how many documents does each term appear.
        df: Counter[str] = Counter()
        for tokens in tokenized:
            df.update(set(tokens))

        # Smooth idf (the +1 inside the log) — never negative, unlike the raw
        # Robertson-Sparck Jones formula when a term is in > half the docs.
        self.idf = {
            term: math.log(1.0 + (num_docs - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

        self._tokenized = tokenized
        self._doc_lengths = doc_lengths
        # Guard div-by-zero when every document is empty.
        self.avgdl = (sum(doc_lengths) / num_docs) if num_docs and sum(doc_lengths) else 1.0

    def _score(self, query_terms: list[str], doc_tokens: list[str], doc_len: int) -> float:
        """BM25 score of one document for one query. Higher = more relevant."""
        if not doc_tokens:
            return 0.0

        tf = Counter(doc_tokens)  # term frequency within this doc
        score = 0.0
        for term in set(query_terms):  # standard BM25: one contribution per term
            idf = self.idf.get(term)
            if idf is None:
                continue  # term not in corpus → contributes nothing
            freq = tf.get(term, 0)
            if not freq:
                continue

            # Length normalization: shorter docs get a boost.
            norm = 1.0 - self.b + self.b * doc_len / self.avgdl
            score += idf * (freq * (self.k1 + 1.0)) / (freq + self.k1 * norm)
        return score

    def retrieve(self, query: str, top_k: int = 5) -> list[tuple[int, float]]:
        """Return up to top_k (document_index, bm25_score) pairs, best first."""
        query_terms = tokenize(query)
        if not query_terms:
            return []

        scored = []
        for idx, (tokens, doc_len) in enumerate(zip(self._tokenized, self._doc_lengths)):
            score = self._score(query_terms, tokens, doc_len)
            if score > 0.0:
                scored.append((idx, score))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]


class BM25Retriever:
    """Searches the same chunks as the semantic Retriever, but lexically.

    Construct from the stored chunks once (see HybridRetriever / main.py), then
    call retrieve(query, top_k) — same interface as the semantic Retriever so
    hybrid_retriever.py can treat both identically.
    """

    def __init__(self, chunks: list[RetrievedChunk], k1: float = _K1, b: float = _B):
        self.chunks = list(chunks)
        self.index = BM25Index([c.text for c in self.chunks], k1=k1, b=b)

    def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        """Rank chunks by BM25 score for the query; return top_k chunks."""
        hits = self.index.retrieve(query, top_k=top_k)
        return [
            # Copy the chunk with the BM25 score attached — never mutate the
            # shared originals (the semantic retriever also holds them).
            replace(self.chunks[idx], score=score)
            for idx, score in hits
        ]

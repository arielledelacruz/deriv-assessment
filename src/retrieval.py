from __future__ import annotations

import math
import re
from collections import Counter

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
IGNORED_TERMS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "does", "for",
    "from", "how", "i", "if", "in", "is", "it", "of", "on", "or", "platform",
    "support", "the", "there", "to", "what", "when", "where", "which", "who",
    "why", "with", "api",
}


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in TOKEN_PATTERN.findall(text.casefold())
        if token not in IGNORED_TERMS
    ]


class TfidfIndex:
    """Small in-memory TF-IDF index built from the current source chunks."""

    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self.term_counts = [Counter(tokenize(chunk["text"])) for chunk in chunks]
        document_frequency: Counter[str] = Counter()
        for counts in self.term_counts:
            document_frequency.update(counts.keys())
        self.document_count = len(chunks)
        self.idf = {
            term: math.log((1 + self.document_count) / (1 + frequency)) + 1
            for term, frequency in document_frequency.items()
        }
        self.vectors = [self._vector(counts) for counts in self.term_counts]

    def _vector(self, counts: Counter[str]) -> dict[str, float]:
        weighted = {
            term: (1 + math.log(count)) * self.idf.get(
                term, math.log(1 + self.document_count) + 1
            )
            for term, count in counts.items()
        }
        norm = math.sqrt(sum(weight * weight for weight in weighted.values()))
        if norm:
            return {term: weight / norm for term, weight in weighted.items()}
        return {}

    def search(self, question: str, top_k: int = 3) -> list[dict]:
        query_counts = Counter(tokenize(question))
        query_vector = self._vector(query_counts)
        scored = []
        for chunk, vector in zip(self.chunks, self.vectors):
            score = sum(weight * vector.get(term, 0.0) for term, weight in query_vector.items())
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda item: (-item[0], item[1]["chunk_id"]))

        return [
            {
                "chunk_id": chunk["chunk_id"],
                "doc_id": chunk["doc_id"],
                "score": round(score, 6),
                "text": chunk["text"],
            }
            for score, chunk in scored[:top_k]
        ]


def retrieve_all(index: TfidfIndex, questions: list[dict], top_k: int = 3) -> list[dict]:
    if top_k < 0:
        raise ValueError("top_k must be non-negative.")
    return [
        {
            "id": question["id"],
            "question": question["question"],
            "retrieved_chunks": index.search(question["question"], top_k=top_k),
        }
        for question in questions
    ]

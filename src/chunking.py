from __future__ import annotations

import hashlib

CHUNK_SIZE = 700
CHUNK_OVERLAP = 120


def create_chunks(documents: list[dict]) -> list[dict]:
    if CHUNK_SIZE <= 0 or CHUNK_OVERLAP < 0 or CHUNK_OVERLAP >= CHUNK_SIZE:
        raise ValueError("Chunk overlap must be non-negative and smaller than chunk size.")

    chunks = []
    for document in documents:
        text = document["text"]
        start = 0
        while start < len(text):
            end = min(start + CHUNK_SIZE, len(text))
            if end < len(text):
                boundary = text.rfind(" ", start + CHUNK_SIZE // 2, end)
                if boundary > start:
                    end = boundary
            chunk_text = text[start:end]
            identity = f"{document['doc_id']}:{start}:{end}:{chunk_text}".encode("utf-8")
            chunk_id = f"chunk_{hashlib.sha1(identity).hexdigest()[:12]}"
            chunks.append({
                "chunk_id": chunk_id,
                "doc_id": document["doc_id"],
                "text": chunk_text,
                "start_char": start,
                "end_char": end,
            })
            if end == len(text):
                break
            start = max(start + 1, end - CHUNK_OVERLAP)

    return chunks

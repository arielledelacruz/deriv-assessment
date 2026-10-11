# Local Knowledge Base Assistant

A small end-to-end RAG-style pipeline for answering questions from local Markdown/text documents with grounded citations.

## Quick start

Requires Python 3.10+ and no third-party packages. The pipeline can use Groq when `GROQ_API_KEY` is configured, and automatically falls back to local extractive answers if the call fails or its response fails grounding validation.

```bash
python run.py
python validate.py
```

The pipeline reads `docs/` and `questions.json` at runtime and regenerates files in `artifacts/`.

To enable Groq, set `GROQ_API_KEY` in the environment or add `GROQ_API_KEY=...` to `.env`. A single raw key line in `.env` is also supported. The default model is `llama-3.3-70b-versatile`; override it with `GROQ_MODEL`. The key is never written to artifacts, and `.env` is excluded by `.gitignore`. Without a key, the run uses local answers without making a network request.

## What it does

1. loads `.md` and `.txt` documents
2. chunks them while retaining source attribution
3. builds a local TF-IDF retrieval index
4. loads questions
5. retrieves the top 3 chunks per question
6. tries Groq for grounded answers when configured; otherwise uses local sentence extraction
7. validates citations and grounding
8. exports final answers
9. runs structural validation

Local fallback is deterministic and extractive: it copies relevant sentences from retrieved chunks, cites the chunks used, and returns the required unsupported response when no evidence matches. The LLM response is accepted only when its format, citations, numeric claims, and evidence overlap pass local validation. Failed or ungrounded responses are replaced by local answers. Attempts are recorded in `artifacts/llm_calls.jsonl`; it is absent when no provider key is configured.

The files in `docs/` are the local knowledge base (Markdown documents discovered recursively at runtime). They contain sample facts for the fictional Example Developer Platform; change or replace them with the approved product information before using the assistant for real decisions. No separate database server or network connection is required.

See `SPECS.md` for design decisions.

## Generated artifacts

- `artifacts/documents.json`
- `artifacts/chunks.json`
- `artifacts/retrieval_results.json`
- `artifacts/answers.json`
- `artifacts/citation_validation.json`
- `artifacts/final_answers.json`
- `artifacts/pipeline_state.json`
- `artifacts/llm_calls.jsonl` (only when a provider call is attempted)

## Replacing the fixtures

You can replace all files under `docs/` and replace `questions.json`, then run:

```bash
python run.py
```

No answer or filename is hardcoded.

Documents are split into overlapping character chunks, then ranked with a standard-library TF-IDF cosine-similarity index. Citation validation checks retrieved-chunk membership, answer/evidence term overlap, and numeric claims.

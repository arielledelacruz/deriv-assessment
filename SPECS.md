# RAG Assistant — Specs and Design Notes

## 1. Goal
Build a small, readable retrieval-augmented question answering pipeline that answers questions only from a local knowledge base and returns machine-readable citations.

The evaluator may replace `docs/` and `questions.json`, so no logic may depend on fixed filenames, fixed question order, or hardcoded answers.

## 2. Design priorities
1. Correctness and traceability over complexity.
2. Runtime document discovery from `docs/`.
3. Stable source attribution from document -> chunk -> retrieval -> answer.
4. Saved intermediate artifacts for every important stage.
5. Deterministic validation after answer generation.
6. Graceful handling of unsupported questions.
7. Minimal dependencies so a clean checkout is easy to run.

## 3. Pipeline stages
The implementation keeps the required stages explicit:

```text
INIT
 -> DOCUMENTS_LOADED
 -> CHUNKS_CREATED
 -> INDEX_BUILT
 -> QUESTIONS_LOADED
 -> RETRIEVAL_COMPLETE
 -> ANSWERS_GENERATED
 -> CITATIONS_VALIDATED
 -> RESULTS_EXPORTED
 -> VALIDATION_COMPLETE
```

`run.py` advances through these stages and writes `artifacts/pipeline_state.json` so the execution path is visible.

## 4. Inputs

### `docs/`
- Read all `.md` and `.txt` files recursively.
- Each loaded document contains:
  - `doc_id`
  - `path`
  - `text`
- `doc_id` is based on the relative path, making it stable for the same input file.

### `questions.json`
Expected schema:

```json
[
  {"id": 1, "question": "What authentication methods are supported?"}
]
```

Validation rejects missing IDs, missing question text, or duplicate IDs.

## 5. Document ingestion
Implementation: `src/documents.py`

All supported files are loaded from disk at runtime and saved to:

`artifacts/documents.json`

No document content is embedded in source code.

## 6. Chunking
Implementation: `src/chunking.py`

Initial settings:
- `CHUNK_SIZE = 700` characters
- `CHUNK_OVERLAP = 120` characters

Why:
- Small enough for focused retrieval.
- Large enough to preserve short policy paragraphs and surrounding context.
- Overlap reduces the chance that a relevant statement is split at a boundary.

Chunks include:
- `chunk_id`
- `doc_id`
- `text`
- `start_char`
- `end_char`

Chunk IDs are stable SHA-1-based IDs derived from document ID, character offsets, and chunk text.

Output:

`artifacts/chunks.json`

## 7. Retrieval
Implementation: `src/retrieval.py`

Initial retrieval method: a small local TF-IDF cosine-similarity index written with the Python standard library.

Why TF-IDF:
- no API key required
- no network access required
- easy to explain
- generated from the evaluator's replacement documents at runtime
- suitable for a small product knowledge base

For every question:
1. tokenize question and chunks
2. compute document frequencies and IDF values from current chunks
3. create normalized TF-IDF vectors
4. score each chunk with cosine similarity
5. return the top 3 chunks

Output:

`artifacts/retrieval_results.json`

## 8. Answer generation
Implementation: `src/answering.py`

Answer generation optionally uses Groq when `GROQ_API_KEY` is configured in the environment or `.env`. The default model is `llama-3.3-70b-versatile`, configurable with `GROQ_MODEL`. Each model answer is checked locally for citation membership, evidence-term overlap, and numeric claims. If a request fails or an answer fails validation, deterministic extractive generation uses the retrieved chunks instead. Without a key, generation runs locally without a network call. Provider attempts are logged to `artifacts/llm_calls.jsonl`; API keys and response bodies are not logged.

Unsupported response:

`The knowledge base does not provide enough information to answer this.`

This avoids hallucinating product features and keeps the starter fully runnable from a clean checkout.

`src/prompts.py` contains the grounding prompt. The retrieval and validation stages remain independent of the LLM provider and use the same answer schema.

## 9. Initial grounding prompt

System instruction:

```text
You are a knowledge-base assistant. Answer the user's question using ONLY the provided context chunks.

Rules:
1. Do not use outside knowledge.
2. Do not invent product features, prices, limits, policies, or behavior.
3. If the context does not provide enough evidence, say exactly:
   "The knowledge base does not provide enough information to answer this."
4. When supported, cite only chunk IDs that appear in the supplied context.
5. Return valid JSON only with this schema:
   {
     "answer": "string",
     "supported": true,
     "citations": ["chunk_id"]
   }
6. `supported` must be false and `citations` must be [] when the answer is not supported.
7. Keep the answer concise and faithful to the wording of the source.
```

User prompt shape:

```text
QUESTION:
{question}

CONTEXT CHUNKS:
[{chunk_id, doc_id, text}, ...]
```

## 10. Citation validation
Implementation: `src/citation_validation.py`

Deterministic checks:
1. every citation exists in that question's retrieved chunks
2. supported answers contain at least one citation
3. unsupported answers contain no citations
4. numeric claims in an answer must also appear in cited chunk text
5. supported answers must have a minimum token overlap with cited evidence

Output:

`artifacts/citation_validation.json`

## 11. Final output
Implementation: `run.py`

`artifacts/final_answers.json` combines:
- question ID
- question
- answer
- supported flag
- citations
- retrieved chunk IDs
- validation result

## 12. Validation command
Implementation: `validate.py`

Checks:
- required artifacts exist
- LLM call log contains one record per question
- all JSON files parse
- exactly one answer exists per input question
- at most 3 chunks are retrieved per question
- citations belong to retrieved chunks
- unsupported answers have no citations
- supported answers have citations

Run with:

```bash
python validate.py
```

## 13. Expected repository structure

```text
.
├── docs/
│   ├── api.md
│   ├── billing.md
│   ├── data.md
│   └── webhooks.md
├── artifacts/
├── src/
│   ├── __init__.py
│   ├── answering.py
│   ├── chunking.py
│   ├── citation_validation.py
│   ├── documents.py
│   ├── prompts.py
│   ├── questions.py
│   ├── retrieval.py
│   └── utils.py
├── .gitignore
├── questions.json
├── README.md
├── SPECS.md
├── run.py
└── validate.py
```

## 14. What I would explain during the assessment
- I chose TF-IDF because the dataset is small and the task values clarity over framework complexity.
- I save each intermediate artifact so retrieval and generation are independently inspectable.
- I keep chunk IDs stable and carry them through retrieval, answers, and validation.
- Answer generation is constrained to retrieved evidence and has an explicit unsupported path.
- Citation validation is deterministic and happens after generation, so a malformed or ungrounded answer can be detected instead of blindly trusted.
- The code never assumes the sample filenames or sample questions will remain unchanged.

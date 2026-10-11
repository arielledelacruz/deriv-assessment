from __future__ import annotations

import json
import os
from pathlib import Path

from src.answering import generate_answers
from src.chunking import create_chunks
from src.citation_validation import validate_citations
from src.documents import load_documents
from src.questions import load_questions
from src.retrieval import TfidfIndex, retrieve_all
from src.utils import write_json

ROOT = Path(__file__).resolve().parent
DOCS_DIR = ROOT / "docs"
QUESTIONS_PATH = ROOT / "questions.json"
ARTIFACTS_DIR = ROOT / "artifacts"
ENV_PATH = ROOT / ".env"


def load_groq_api_key() -> str | None:
    key = os.environ.get("GROQ_API_KEY")
    if key:
        return key
    if not ENV_PATH.exists():
        return None

    assigned_keys = []
    bare_values = []
    for line_number, raw_line in enumerate(ENV_PATH.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            bare_values.append(line)
            continue

        name, value = line.split("=", 1)
        if name.strip() != "GROQ_API_KEY":
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if not value:
            raise ValueError(f"GROQ_API_KEY is empty in {ENV_PATH.name} on line {line_number}.")
        assigned_keys.append(value)

    if assigned_keys:
        return assigned_keys[-1]
    if len(bare_values) == 1:
        return bare_values[0]
    if len(bare_values) > 1:
        raise ValueError(f"Multiple unlabelled values found in {ENV_PATH.name}; use GROQ_API_KEY=<key>.")
    return None

STAGES = [
    "INIT",
    "DOCUMENTS_LOADED",
    "CHUNKS_CREATED",
    "INDEX_BUILT",
    "QUESTIONS_LOADED",
    "RETRIEVAL_COMPLETE",
    "ANSWERS_GENERATED",
    "CITATIONS_VALIDATED",
    "RESULTS_EXPORTED",
    "VALIDATION_COMPLETE",
]


def save_stage(stage: str) -> None:
    if stage not in STAGES:
        raise ValueError(f"Unknown pipeline stage: {stage}")
    write_json(ARTIFACTS_DIR / "pipeline_state.json", {"stage": stage, "stage_index": STAGES.index(stage)})
    print(f"[{stage}]")


def main() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    save_stage("INIT")
    llm_log = ARTIFACTS_DIR / "llm_calls.jsonl"
    if llm_log.exists():
        llm_log.unlink()
    for name in ("answers.json", "citation_validation.json", "final_answers.json"):
        write_json(ARTIFACTS_DIR / name, [])

    documents = load_documents(DOCS_DIR)
    write_json(ARTIFACTS_DIR / "documents.json", documents)
    save_stage("DOCUMENTS_LOADED")

    chunks = create_chunks(documents)
    write_json(ARTIFACTS_DIR / "chunks.json", chunks)
    save_stage("CHUNKS_CREATED")

    index = TfidfIndex(chunks)
    save_stage("INDEX_BUILT")

    questions = load_questions(QUESTIONS_PATH)
    save_stage("QUESTIONS_LOADED")

    retrieval_results = retrieve_all(index, questions, top_k=3)
    write_json(ARTIFACTS_DIR / "retrieval_results.json", retrieval_results)
    save_stage("RETRIEVAL_COMPLETE")

    api_key = load_groq_api_key()
    if api_key:
        print("Answer mode: Groq with local fallback")
    else:
        print("Answer mode: local (GROQ_API_KEY not configured)")
    answers = generate_answers(
        retrieval_results,
        api_key=api_key,
        model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        log_path=ARTIFACTS_DIR / "llm_calls.jsonl",
    )
    if api_key:
        call_log = ARTIFACTS_DIR / "llm_calls.jsonl"
        calls = []
        if call_log.exists():
            calls = [
                json.loads(line)
                for line in call_log.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        failed_call = next((call for call in calls if call.get("used_fallback")), None)
        if failed_call:
            local_count = 1 + failed_call.get("remaining_local_fallbacks", 0)
            print(f"Groq requests attempted: {len(calls)}")
            print(f"Answers using local fallback: {local_count}")
            print(f"Fallback reason: {failed_call['fallback_reason']}")
        else:
            print(f"Groq requests completed: {len(calls)}")
            print("Answers using local fallback: 0")
    else:
        print(f"Answers using local mode: {len(answers)}")
    write_json(ARTIFACTS_DIR / "answers.json", answers)
    save_stage("ANSWERS_GENERATED")

    validations = validate_citations(answers, retrieval_results)
    write_json(ARTIFACTS_DIR / "citation_validation.json", validations)
    save_stage("CITATIONS_VALIDATED")

    retrieval_by_id = {r["id"]: r for r in retrieval_results}
    validation_by_id = {v["id"]: v for v in validations}
    final_answers = []
    for answer in answers:
        retrieval = retrieval_by_id[answer["id"]]
        final_answers.append({
            **answer,
            "retrieved_chunk_ids": [c["chunk_id"] for c in retrieval["retrieved_chunks"]],
            "validation": validation_by_id[answer["id"]],
        })

    write_json(ARTIFACTS_DIR / "final_answers.json", final_answers)
    save_stage("RESULTS_EXPORTED")

    failures = sum(not v["passed"] for v in validations)
    supported = sum(bool(a["supported"]) for a in answers)

    # The structural validator is intentionally separate (`python validate.py`).
    # This stage marks completion of the pipeline's own citation validation.
    save_stage("VALIDATION_COMPLETE")

    print("\nPipeline summary")
    print(f"Documents:           {len(documents)}")
    print(f"Chunks:              {len(chunks)}")
    print(f"Questions:           {len(questions)}")
    print(f"Supported answers:   {supported}")
    print(f"Validation failures: {failures}")


if __name__ == "__main__":
    main()

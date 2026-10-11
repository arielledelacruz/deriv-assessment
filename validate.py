from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"

REQUIRED = [
    ROOT / "questions.json",
    ARTIFACTS / "documents.json",
    ARTIFACTS / "chunks.json",
    ARTIFACTS / "retrieval_results.json",
    ARTIFACTS / "answers.json",
    ARTIFACTS / "citation_validation.json",
    ARTIFACTS / "final_answers.json",
]


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    errors: list[str] = []

    for path in REQUIRED:
        if not path.exists():
            errors.append(f"Missing required file: {path.relative_to(ROOT)}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    try:
        questions = load_json(ROOT / "questions.json")
        retrieval = load_json(ARTIFACTS / "retrieval_results.json")
        answers = load_json(ARTIFACTS / "answers.json")
        validations = load_json(ARTIFACTS / "citation_validation.json")
        documents = load_json(ARTIFACTS / "documents.json")
        chunks = load_json(ARTIFACTS / "chunks.json")
        final_answers = load_json(ARTIFACTS / "final_answers.json")
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: Invalid JSON or unreadable file: {exc}")
        return 1

    if not all(isinstance(value, list) for value in (
        questions, retrieval, answers, validations, documents, chunks, final_answers
    )):
        print("ERROR: Input and output JSON files must contain arrays.")
        return 1

    if any(not isinstance(question, dict) or "id" not in question for question in questions):
        print("ERROR: Every question must be an object with an id.")
        return 1

    question_ids = [q["id"] for q in questions]
    answer_ids = [a["id"] for a in answers]
    retrieval_ids = [r["id"] for r in retrieval]
    validation_ids = [v["id"] for v in validations]

    if len(set(map(str, question_ids))) != len(question_ids):
        errors.append("Question IDs must be unique.")
    if len(answer_ids) != len(question_ids) or sorted(map(str, answer_ids)) != sorted(map(str, question_ids)):
        errors.append("Every question must have exactly one answer.")
    if sorted(map(str, retrieval_ids)) != sorted(map(str, question_ids)):
        errors.append("Every question must have exactly one retrieval result.")
    if sorted(map(str, validation_ids)) != sorted(map(str, question_ids)):
        errors.append("Every question must have exactly one citation validation result.")
    if len(documents) == 0:
        errors.append("At least one source document must be loaded.")
    if len(final_answers) != len(question_ids):
        errors.append("Every question must have exactly one final answer.")

    retrieval_by_id = {r["id"]: r for r in retrieval}
    validation_by_id = {v["id"]: v for v in validations}
    answer_by_id = {a["id"]: a for a in answers}
    known_chunk_ids = {chunk["chunk_id"] for chunk in chunks}
    for answer in answers:
        if not isinstance(answer, dict) or "id" not in answer:
            errors.append("Every answer must be an object with an id.")
            continue
        if not isinstance(answer.get("answer"), str) or not answer["answer"].strip():
            errors.append(f"Question {answer['id']} has an empty or invalid answer.")
        if not isinstance(answer.get("supported"), bool):
            errors.append(f"Question {answer['id']} has a non-boolean supported flag.")
        if not isinstance(answer.get("citations"), list):
            errors.append(f"Question {answer['id']} citations must be an array.")
            continue

        result = retrieval_by_id.get(answer["id"])
        if result is None:
            continue
        chunks = result.get("retrieved_chunks", [])
        if not isinstance(chunks, list):
            errors.append(f"Question {answer['id']} retrieved_chunks must be an array.")
            continue
        if len(chunks) > 3:
            errors.append(f"Question {answer['id']} retrieved more than 3 chunks.")
        valid_ids = {c["chunk_id"] for c in chunks}
        bad = [c for c in answer.get("citations", []) if c not in valid_ids]
        if bad:
            errors.append(f"Question {answer['id']} has invalid citations: {bad}")
        if answer.get("supported") and not answer.get("citations"):
            errors.append(f"Question {answer['id']} is supported but has no citations.")
        if not answer.get("supported") and answer.get("citations"):
            errors.append(f"Question {answer['id']} is unsupported but has citations.")
        if not answer.get("supported") and answer.get("answer") != (
            "The knowledge base does not provide enough information to answer this."
        ):
            errors.append(f"Question {answer['id']} has an invalid unsupported-answer message.")
        if any(chunk_id not in known_chunk_ids for chunk_id in valid_ids):
            errors.append(f"Question {answer['id']} retrieved a chunk missing from chunks.json.")
        validation = validation_by_id.get(answer["id"])
        if validation is not None and not validation.get("passed"):
            errors.append(f"Question {answer['id']} failed citation validation: {validation.get('issues', [])}")

    if len(validation_by_id) != len(validation_ids):
        errors.append("Citation validation result IDs must be unique.")

    final_by_id = {result["id"]: result for result in final_answers}
    for question_id, answer in answer_by_id.items():
        final = final_by_id.get(question_id)
        if final is None:
            continue
        if final.get("answer") != answer.get("answer") or final.get("citations") != answer.get("citations"):
            errors.append(f"Final answer for question {question_id} does not match answers.json.")
        expected_retrieved = [
            chunk["chunk_id"]
            for chunk in retrieval_by_id[question_id]["retrieved_chunks"]
        ] if question_id in retrieval_by_id else []
        if final.get("retrieved_chunk_ids") != expected_retrieved:
            errors.append(f"Final answer for question {question_id} has incorrect retrieved chunk IDs.")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"\nValidation failed with {len(errors)} issue(s).")
        return 1

    print("Validation passed.")
    print(f"Questions checked: {len(questions)}")
    print("All required artifacts are valid and citation rules are satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

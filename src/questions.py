from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_questions(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as source:
        questions = json.load(source)

    if not isinstance(questions, list):
        raise ValueError("questions.json must contain a JSON array.")

    seen_ids: set[str] = set()
    normalized_questions = []
    for position, question in enumerate(questions):
        if not isinstance(question, dict) or "id" not in question:
            raise ValueError(f"Question at index {position} must be an object with an id.")
        question_id = question["id"]
        if isinstance(question_id, bool) or not isinstance(question_id, (int, str)):
            raise ValueError(f"Question at index {position} has an invalid id.")
        if not str(question_id).strip() or str(question_id) in seen_ids:
            raise ValueError(f"Question at index {position} has an empty or duplicate id.")
        seen_ids.add(str(question_id))

        text = question.get("question")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Question {question_id} must have non-empty question text.")
        normalized_questions.append({"id": question_id, "question": text.strip()})

    return normalized_questions

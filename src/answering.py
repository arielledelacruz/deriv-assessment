from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from src.prompts import SYSTEM_PROMPT, build_user_prompt
from src.retrieval import tokenize

UNSUPPORTED_ANSWER = "The knowledge base does not provide enough information to answer this."

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "can", "does", "for", "from",
    "happens", "how", "i", "if", "in", "is", "it", "long", "me", "of", "on",
    "or", "platform", "the", "there", "to", "what", "when", "where", "which",
    "who", "why", "with", "support", "api",
}

SYNONYMS = {
    "authentication": "auth",
    "authenticate": "auth",
    "methods": "method",
    "supports": "support",
    "supporting": "support",
    "limits": "limit",
    "logs": "log",
    "retained": "retain",
    "retention": "retain",
    "exceeds": "exceed",
    "exceeded": "exceed",
    "subscriptions": "subscription",
    "startups": "startup",
    "deletion": "delete",
    "deletions": "delete",
    "requests": "request",
    "immediately": "immediate",
}

SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")
DEFAULT_MODEL = "llama-3.3-70b-versatile"


def _terms(text: str) -> set[str]:
    return {
        SYNONYMS.get(token, token)
        for token in tokenize(text)
        if token not in STOP_WORDS
    }


def _candidate_sentences(question: str, chunks: list[dict]) -> list[tuple[float, str, str]]:
    question_terms = _terms(question)
    if not question_terms:
        return []

    candidates = []
    for chunk in chunks:
        for sentence in SENTENCE_PATTERN.split(chunk["text"]):
            sentence = sentence.strip()
            overlap = question_terms & _terms(sentence)
            if not overlap:
                continue
            if len(question_terms) >= 4 and len(overlap) < 2:
                continue
            coverage = len(overlap) / len(question_terms)
            score = coverage + chunk["score"] * 0.1
            candidates.append((score, chunk["chunk_id"], sentence))

    return sorted(candidates, key=lambda item: (-item[0], item[1], item[2]))


def _generate_local_answer(result: dict) -> dict:
    candidates = _candidate_sentences(result["question"], result["retrieved_chunks"])
    if not candidates:
        return {
            "id": result["id"],
            "question": result["question"],
            "answer": UNSUPPORTED_ANSWER,
            "supported": False,
            "citations": [],
        }

    best_score = candidates[0][0]
    selected = [
        candidate for candidate in candidates
        if candidate[0] >= best_score * 0.8
    ][:2]
    return {
        "id": result["id"],
        "question": result["question"],
        "answer": " ".join(candidate[2] for candidate in selected),
        "supported": True,
        "citations": list(dict.fromkeys(candidate[1] for candidate in selected)),
    }


def _request_completion(api_key: str, model: str, question: str, context: list[dict]) -> dict:
    user_prompt = build_user_prompt(question, context)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        error_code = None
        try:
            provider_error = json.loads(details).get("error", {})
            if isinstance(provider_error, dict):
                candidate_code = provider_error.get("code")
                if isinstance(candidate_code, (str, int)):
                    error_code = str(candidate_code)
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
        reason = f" (error code: {error_code})" if error_code else ""
        raise RuntimeError(f"Groq API returned HTTP {exc.code}{reason}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("Groq API request could not be completed.") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Groq API returned invalid JSON.") from exc

    try:
        content = response_data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Groq API returned an unexpected response shape.") from exc
    if not isinstance(content, str):
        raise RuntimeError("Groq API returned an empty answer.")
    try:
        generated = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Groq returned an answer that was not valid JSON.") from exc
    if not isinstance(generated, dict):
        raise RuntimeError("Groq answer JSON must be an object.")
    return generated


def _validate_generated_answer(generated: dict, result: dict) -> dict:
    answer = generated.get("answer")
    supported = generated.get("supported")
    citations = generated.get("citations")
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Groq answer is missing non-empty answer text.")
    if not isinstance(supported, bool):
        raise RuntimeError("Groq answer has an invalid supported flag.")
    if not isinstance(citations, list) or any(not isinstance(item, str) for item in citations):
        raise RuntimeError("Groq answer has an invalid citations array.")

    if not supported:
        answer = UNSUPPORTED_ANSWER
        citations = []

    validated = {
        "id": result["id"],
        "question": result["question"],
        "answer": answer.strip(),
        "supported": supported,
        "citations": citations,
    }
    from src.citation_validation import validate_citations

    validation = validate_citations([validated], [result])[0]
    if not validation["passed"]:
        raise RuntimeError("Groq answer failed local grounding checks.")
    return validated


def _append_call_log(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(record, ensure_ascii=False) + "\n")


def generate_answers(
    retrieval_results: list[dict],
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    log_path: Path | None = None,
) -> list[dict]:
    """Try Groq per question, using grounded local extraction whenever it fails."""
    api_key = api_key or os.environ.get("GROQ_API_KEY")
    if log_path is None:
        log_path = Path("artifacts/llm_calls.jsonl")
    if not api_key and log_path.exists():
        log_path.unlink()

    answers = []
    provider_available = bool(api_key)
    for index, result in enumerate(retrieval_results):
        if not provider_available:
            answers.append(_generate_local_answer(result))
            continue

        context = [
            {key: chunk[key] for key in ("chunk_id", "doc_id", "text")}
            for chunk in result["retrieved_chunks"]
        ]
        user_prompt = build_user_prompt(result["question"], context)
        record = {
            "stage": "answer_generation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": "groq",
            "model": model,
            "question_id": result["id"],
            "prompt_hash": hashlib.sha256(
                f"{SYSTEM_PROMPT}\n{user_prompt}".encode("utf-8")
            ).hexdigest(),
            "input_artifacts": ["artifacts/retrieval_results.json"],
            "output_artifact": "artifacts/answers.json",
            "used_fallback": False,
        }
        try:
            generated = _request_completion(api_key, model, result["question"], context)
            answer = _validate_generated_answer(generated, result)
        except RuntimeError as exc:
            answer = _generate_local_answer(result)
            record["used_fallback"] = True
            record["fallback_reason"] = str(exc)
            record["remaining_local_fallbacks"] = len(retrieval_results) - index - 1
            provider_available = False
        finally:
            _append_call_log(log_path, record)
        answers.append(answer)

    return answers

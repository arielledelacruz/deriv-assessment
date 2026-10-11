from __future__ import annotations

import re

from src.answering import UNSUPPORTED_ANSWER, _terms

NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?%?\b")


def validate_citations(answers: list[dict], retrieval_results: list[dict]) -> list[dict]:
    retrieval_by_id = {result["id"]: result for result in retrieval_results}
    validations = []

    for answer in answers:
        issues = []
        retrieval = retrieval_by_id.get(answer["id"])
        if retrieval is None:
            validations.append({"id": answer["id"], "passed": False, "issues": ["Missing retrieval result."]})
            continue

        retrieved_chunks = {
            chunk["chunk_id"]: chunk
            for chunk in retrieval["retrieved_chunks"]
        }
        citations = answer.get("citations", [])
        invalid = [chunk_id for chunk_id in citations if chunk_id not in retrieved_chunks]
        if invalid:
            issues.append(f"Citations are not in retrieved chunks: {invalid}.")

        supported = answer.get("supported") is True
        if supported and not citations:
            issues.append("Supported answer has no citations.")
        if not supported and citations:
            issues.append("Unsupported answer has citations.")
        if not supported and answer.get("answer") != UNSUPPORTED_ANSWER:
            issues.append("Unsupported answer does not use the required fallback text.")

        cited_text = " ".join(
            retrieved_chunks[chunk_id]["text"]
            for chunk_id in citations
            if chunk_id in retrieved_chunks
        )
        answer_terms = _terms(answer.get("answer", ""))
        evidence_terms = _terms(cited_text)
        if supported and not answer_terms.intersection(evidence_terms):
            issues.append("Answer has no meaningful term overlap with cited evidence.")

        answer_numbers = set(NUMBER_PATTERN.findall(answer.get("answer", "")))
        evidence_numbers = set(NUMBER_PATTERN.findall(cited_text))
        unsupported_numbers = sorted(answer_numbers - evidence_numbers)
        if unsupported_numbers:
            issues.append(f"Numeric claims are absent from cited evidence: {unsupported_numbers}.")

        validations.append({
            "id": answer["id"],
            "passed": not issues,
            "issues": issues,
        })

    return validations

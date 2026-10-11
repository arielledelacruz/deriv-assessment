from pathlib import Path


def load_documents(docs_dir="docs"):
    documents = []

    root = Path(docs_dir)
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
            continue

        text = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(root).as_posix()
        doc_id = Path(relative_path).with_suffix("").as_posix()

        documents.append({
            "doc_id": doc_id,
            "path": relative_path,
            "text": text
        })

    return documents
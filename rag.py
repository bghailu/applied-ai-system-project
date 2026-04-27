"""
Lightweight RAG layer for PawPal+.

Indexes two kinds of knowledge into a single ChromaDB collection,
distinguished by metadata `source_type`:

- "calendar"  — owner's calendar events
- "health"    — pet health records

Expected JSON shapes:
    Calendar: [{"title", "date", "start", "end", "notes"}]
    Health:   [{"pet", "date", "type", "notes"}]

Markdown files are split on `\n---\n`; if there are no `---` separators,
they are split on top-level `# ` headings. Each block becomes one document.
"""

from __future__ import annotations

import re
from typing import Any

import chromadb


COLLECTION_NAME = "pawpal_kb"


def _split_markdown(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if "\n---\n" in text:
        blocks = [b.strip() for b in text.split("\n---\n")]
    else:
        # Split on lines that start with a single `# ` heading
        parts = re.split(r"(?m)^(?=#\s)", text)
        blocks = [b.strip() for b in parts]
    return [b for b in blocks if b]


def _format_calendar_doc(entry: dict) -> str:
    title = entry.get("title", "(untitled)")
    date = entry.get("date", "")
    start = entry.get("start", "")
    end = entry.get("end", "")
    notes = entry.get("notes", "")
    when = f"{date} {start}–{end}".strip()
    return f"{title} — {when}: {notes}".strip(": ").strip()


def _format_health_doc(entry: dict) -> str:
    pet = entry.get("pet", "")
    date = entry.get("date", "")
    kind = entry.get("type", "")
    notes = entry.get("notes", "")
    return f"{pet} {date} {kind}: {notes}".strip()


class RagIndex:
    def __init__(self, persist_dir: str = ".chromadb"):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(name=COLLECTION_NAME)
        self.persist_dir = persist_dir

    def index_markdown(self, text: str, source_type: str, source_name: str) -> int:
        blocks = _split_markdown(text)
        if not blocks:
            return 0
        ids = [f"{source_name}:{source_type}:{i}" for i in range(len(blocks))]
        metadatas = [
            {"source_type": source_type, "source_name": source_name, "format": "markdown"}
            for _ in blocks
        ]
        self.collection.upsert(ids=ids, documents=blocks, metadatas=metadatas)
        return len(blocks)

    def index_json(self, data: list[dict], source_type: str, source_name: str) -> int:
        if not data:
            return 0
        formatter = _format_calendar_doc if source_type == "calendar" else _format_health_doc
        documents = [formatter(entry) for entry in data]
        ids = [f"{source_name}:{source_type}:{i}" for i in range(len(data))]
        metadatas = []
        for entry in data:
            md: dict[str, Any] = {
                "source_type": source_type,
                "source_name": source_name,
                "format": "json",
            }
            # Flatten primitive fields into metadata for filtering / display
            for k, v in entry.items():
                if isinstance(v, (str, int, float, bool)):
                    md[k] = v
            metadatas.append(md)
        self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        return len(documents)

    def query(self, text: str, source_type: str | None = None, k: int = 4) -> list[dict]:
        if self.collection.count() == 0:
            return []
        kwargs: dict[str, Any] = {"query_texts": [text], "n_results": k}
        if source_type is not None:
            kwargs["where"] = {"source_type": source_type}
        result = self.collection.query(**kwargs)
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]
        return [
            {"document": d, "metadata": m, "distance": dist}
            for d, m, dist in zip(docs, metas, dists)
        ]

    def count(self) -> int:
        return self.collection.count()

    def reset(self) -> None:
        self.client.delete_collection(name=COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(name=COLLECTION_NAME)

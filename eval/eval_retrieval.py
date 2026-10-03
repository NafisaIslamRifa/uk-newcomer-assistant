"""Retrieval evaluation: does the right GOV.UK page come back in the top k?

Metrics (over "answerable" questions only):
- Recall@k  : share of questions where the expected page is in the top k
- MRR       : mean of 1/rank of the first correct hit (0 if not found)

Usage:
    python -m eval.eval_retrieval
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from rag.retriever import retrieve

QUESTIONS_PATH = Path("eval/questions.json")
RESULTS_PATH = Path("eval/results_retrieval.json")
K = 5


def to_doc_id(path: str) -> str:
    # matches doc_id in ingest/fetch_govuk.py
    return path.replace("/", "__")


def evaluate(retrieve_fn=retrieve, k: int = K) -> dict:
    questions = json.loads(QUESTIONS_PATH.read_text())
    rows = []

    for q in questions:
        if q.get("type") != "answerable" or not q.get("expected_doc"):
            continue
        expected = to_doc_id(q["expected_doc"])
        hits = retrieve_fn(q["question"], k=k)
        ranked_docs = [h["doc_id"] for h in hits]
        rank = ranked_docs.index(expected) + 1 if expected in ranked_docs else None
        rows.append({
            "id": q["id"],
            "question": q["question"],
            "expected": expected,
            "rank": rank,
            "top1": ranked_docs[0] if ranked_docs else None,
        })

    n = len(rows)
    recall = sum(r["rank"] is not None for r in rows) / n if n else 0.0
    mrr = sum(1 / r["rank"] for r in rows if r["rank"]) / n if n else 0.0

    print(f"\n{'id':<5}{'rank':<6}question")
    for r in rows:
        mark = r["rank"] if r["rank"] else "MISS"
        print(f"{r['id']:<5}{str(mark):<6}{r['question']}")
        if not r["rank"]:
            print(f"{'':<11}expected {r['expected']}, got {r['top1']}")
    print(f"\nRecall@{k}: {recall:.2f}   MRR: {mrr:.2f}   (n={n})")

    summary = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "k": k,
        "n_questions": n,
        f"recall@{k}": round(recall, 3),
        "mrr": round(mrr, 3),
        "rows": rows,
    }
    RESULTS_PATH.write_text(json.dumps(summary, indent=2))
    print(f"Saved to {RESULTS_PATH}")
    return summary


if __name__ == "__main__":
    evaluate()

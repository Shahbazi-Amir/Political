from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable


def evaluate_records(records: Iterable[dict]) -> dict[str, float | int | None]:
    rows = list(records)
    if not rows:
        return {"cases": 0, "verdict_accuracy": None, "high_confidence_accuracy": None, "false_high_confidence_rate": None, "citation_validity": None}
    verdict_correct = high = high_correct = false_high = citation_checks = citation_valid = 0
    for row in rows:
        expected = row.get("expected_verdict")
        actual = row.get("actual_verdict")
        if expected == actual:
            verdict_correct += 1
        confidence = float(row.get("confidence", 0))
        if confidence >= 0.80:
            high += 1
            if expected == actual:
                high_correct += 1
            else:
                false_high += 1
        available = set(row.get("available_evidence_ids", []))
        for cid in row.get("citation_ids", []):
            citation_checks += 1
            if cid in available:
                citation_valid += 1
    return {
        "cases": len(rows), "verdict_accuracy": verdict_correct / len(rows),
        "high_confidence_accuracy": (high_correct / high) if high else None,
        "false_high_confidence_rate": (false_high / high) if high else 0.0,
        "citation_validity": (citation_valid / citation_checks) if citation_checks else 1.0,
        "verdict_distribution": dict(Counter(row.get("actual_verdict") for row in rows)),
    }


def evaluate_jsonl(path: str | Path) -> dict:
    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return evaluate_records(records)

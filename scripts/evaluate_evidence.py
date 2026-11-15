"""Evaluate SkillProof's evidence-level baseline against a manually labeled CSV."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.main import score_evidence  # noqa: E402

LABELS = ("weak", "medium", "strong")


def evaluate(path: Path) -> dict:
    confusion = {actual: Counter() for actual in LABELS}
    rows = 0
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"skill", "text", "label"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("CSV must have skill,text,label columns")
        for row_number, row in enumerate(reader, start=2):
            actual = (row.get("label") or "").strip().lower()
            skill = (row.get("skill") or "").strip()
            text = row.get("text") or ""
            if actual not in LABELS or not skill or not text.strip():
                raise ValueError(f"Invalid or empty value on CSV row {row_number}")
            predictions = score_evidence(text)
            match = next((item for item in predictions if item["skill"].casefold() == skill.casefold()), None)
            if match is None:
                raise ValueError(f"Skill {skill!r} was not extracted on CSV row {row_number}")
            confusion[actual][match["level"]] += 1
            rows += 1

    if not rows:
        raise ValueError("CSV contains no labeled examples")
    per_class = {}
    f1_values = []
    correct = 0
    for label in LABELS:
        tp = confusion[label][label]
        fp = sum(confusion[other][label] for other in LABELS if other != label)
        fn = sum(confusion[label][other] for other in LABELS if other != label)
        support = sum(confusion[label].values())
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4), "support": support}
        f1_values.append(f1)
        correct += tp
    return {
        "examples": rows,
        "accuracy": round(correct / rows, 4),
        "macro_f1": round(sum(f1_values) / len(f1_values), 4),
        "per_class": per_class,
        "confusion_matrix": {label: dict(confusion[label]) for label in LABELS},
        "warning": "Metrics describe this labeled sample only; use a held-out set and diverse resumes/READMEs before making general claims.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="CSV with skill,text,label columns")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.csv_path), indent=2))


if __name__ == "__main__":
    main()

"""Train and evaluate the evidence-depth classifier on manually reviewed examples.

Input CSV columns: skill,text,label where label is weak, medium, or strong.
The script requires at least 100 reviewed examples (at least 10 per class), holds
out a stratified test split, and saves a model only after reporting test metrics.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

LABELS = {"weak", "medium", "strong"}


def read_examples(path: Path) -> tuple[list[str], list[str]]:
    texts, labels = [], []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"skill", "text", "label"}.issubset(reader.fieldnames or []):
            raise ValueError("CSV must contain skill,text,label columns")
        for row_number, row in enumerate(reader, start=2):
            skill, text = (row.get("skill") or "").strip(), (row.get("text") or "").strip()
            label = (row.get("label") or "").strip().lower()
            if not skill or not text or label not in LABELS:
                raise ValueError(f"Invalid skill, text, or label on row {row_number}")
            texts.append(f"{skill}: {text}")
            labels.append(label)
    counts = Counter(labels)
    if len(labels) < 100:
        raise ValueError(f"Need at least 100 manually reviewed examples; found {len(labels)}")
    if any(counts[label] < 10 for label in LABELS):
        raise ValueError("Need at least 10 reviewed examples for each of weak, medium, and strong")
    return texts, labels


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--model-out", type=Path, default=Path("evaluation/evidence_classifier.joblib"))
    args = parser.parse_args()
    try:
        from joblib import dump
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
        from sklearn.model_selection import train_test_split
        from sklearn.pipeline import Pipeline
    except ImportError as exc:
        raise SystemExit("Install project requirements, including scikit-learn, before training.") from exc

    texts, labels = read_examples(args.csv_path)
    train_texts, test_texts, train_labels, test_labels = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels,
    )
    model = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, strip_accents="unicode")),
        ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)),
    ])
    model.fit(train_texts, train_labels)
    predictions = model.predict(test_texts)
    report = {
        "reviewed_examples": len(texts), "training_examples": len(train_texts),
        "held_out_examples": len(test_texts), "accuracy": round(accuracy_score(test_labels, predictions), 4),
        "per_class": classification_report(test_labels, predictions, labels=["weak", "medium", "strong"],
                                             output_dict=True, zero_division=0),
        "confusion_matrix_labels": ["weak", "medium", "strong"],
        "confusion_matrix": confusion_matrix(test_labels, predictions, labels=["weak", "medium", "strong"]).tolist(),
        "warning": "Metrics describe this held-out sample only; do not generalize without diverse external evaluation.",
    }
    args.model_out.parent.mkdir(parents=True, exist_ok=True)
    dump(model, args.model_out)
    metrics_path = args.model_out.with_suffix(".metrics.json")
    metrics_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({**report, "model": str(args.model_out), "metrics_file": str(metrics_path)}, indent=2))


if __name__ == "__main__":
    main()

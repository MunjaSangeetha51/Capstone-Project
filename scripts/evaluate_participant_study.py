"""Summarize anonymized SkillProof participant-study CSV data without inventing results.

Use one row per participant and skill for mismatch/diagnostic analysis. Profile-level
matching and leverage metrics are deduplicated by participant_id. Collect informed
consent and use pseudonymous IDs; do not place names or contact details in this file.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

REQUIRED = {"participant_id", "claimed_skill", "claimed_score", "quiz_score", "diagnostic_group",
            "pre_score", "post_score", "raw_match_count", "corrected_match_count",
            "ready_ranked", "ready_random", "consent_recorded"}


def number(value: str, name: str, row_number: int, *, optional: bool = False) -> float | None:
    if optional and not value.strip():
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected a number for {name} on row {row_number}") from exc


def mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def evaluate(path: Path) -> dict:
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError(f"CSV must contain: {', '.join(sorted(REQUIRED))}")
        for row_number, raw in enumerate(reader, start=2):
            row = {key: (raw.get(key) or "").strip() for key in REQUIRED}
            if not row["participant_id"] or not row["claimed_skill"]:
                raise ValueError(f"Missing pseudonymous participant_id or claimed_skill on row {row_number}")
            if row["consent_recorded"].lower() not in {"yes", "true", "1"}:
                raise ValueError(f"Consent must be recorded as yes/true/1 on row {row_number}")
            values = {}
            for name in ("claimed_score", "quiz_score", "pre_score", "post_score", "raw_match_count",
                         "corrected_match_count", "ready_ranked", "ready_random"):
                values[name] = number(row[name], name, row_number,
                                      optional=name in {"pre_score", "post_score", "raw_match_count", "corrected_match_count", "ready_ranked", "ready_random"})
            if not 0 <= values["claimed_score"] <= 100 or not 0 <= values["quiz_score"] <= 100:
                raise ValueError(f"Skill scores must be between 0 and 100 on row {row_number}")
            rows.append({**row, **values})
    if not rows:
        raise ValueError("CSV contains no participant responses")

    mismatch_rows = [row for row in rows if abs(row["claimed_score"] - row["quiz_score"]) >= 20]
    groups = {name: [row["post_score"] - row["pre_score"] for row in rows
                     if row["diagnostic_group"].casefold() == name and row["pre_score"] is not None and row["post_score"] is not None]
              for name in ("targeted", "generic")}
    by_participant: dict[str, list[dict]] = {}
    for row in rows:
        by_participant.setdefault(row["participant_id"], []).append(row)
    raw_corrected = []
    ranked_random = []
    inflated_profiles = 0
    for participant_rows in by_participant.values():
        first = participant_rows[0]
        if first["raw_match_count"] is not None and first["corrected_match_count"] is not None:
            raw_corrected.append(first["raw_match_count"] - first["corrected_match_count"])
            inflated_profiles += first["raw_match_count"] > first["corrected_match_count"]
        if first["ready_ranked"] is not None and first["ready_random"] is not None:
            ranked_random.append(first["ready_ranked"] - first["ready_random"])

    return {
        "participants": len(by_participant), "participant_skill_rows": len(rows),
        "claimed_quiz_mismatches": {"threshold_points": 20, "rows": len(mismatch_rows),
                                     "rate": round(len(mismatch_rows) / len(rows), 4)},
        "diagnostic_feedback": {group: {"rows_with_pre_post_scores": len(values), "mean_score_change": mean(values)}
                                for group, values in groups.items()},
        "matching": {"profiles_with_counts": len(raw_corrected), "mean_raw_minus_corrected_matches": mean(raw_corrected),
                      "profiles_with_more_raw_matches": inflated_profiles},
        "leverage_order": {"profiles_with_both_simulations": len(ranked_random),
                           "mean_ranked_minus_random_ready_count": mean(ranked_random)},
        "warning": "Descriptive results for this convenience sample only; they do not prove causation or generalize to all students.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.csv_path), indent=2))


if __name__ == "__main__":
    main()

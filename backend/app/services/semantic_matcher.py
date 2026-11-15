"""Skill-aware semantic ranking with a local SentenceTransformers model and fallback."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from backend.data import ALIASES


@lru_cache(maxsize=1)
def _encoder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(os.getenv("SKILLPROOF_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))


def _tfidf_scores(query: str, documents: list[str]) -> list[float]:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    matrix = TfidfVectorizer(ngram_range=(1, 2), stop_words="english").fit_transform([query, *documents])
    return [round(float(value) * 100, 1) for value in cosine_similarity(matrix[0:1], matrix[1:]).ravel()]


def rank(query: str, documents: list[str]) -> tuple[list[float], str]:
    """Rank descriptions against a profile/query; never silently claim embeddings if unavailable."""
    try:
        model = _encoder()
        vectors = model.encode([query, *documents], normalize_embeddings=True, convert_to_numpy=True)
        import numpy as np
        scores = np.clip(vectors[1:] @ vectors[0], 0, 1) * 100
        return [round(float(score), 1) for score in scores], "sentence-transformers"
    except Exception:
        return _tfidf_scores(query, documents), "tf-idf-fallback"


def match_profile_to_postings(skills: dict[str, int], postings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Combine semantic description similarity with explicit required-skill coverage."""
    if not postings:
        return []
    profile = "; ".join(
        f"{name} {' '.join(ALIASES.get(name, []))} (verified proficiency {max(0,min(100,score))}/100)"
        for name, score in skills.items()
    )
    descriptions = [f"{item.get('title','')} {item.get('description','')} Required skills: {', '.join(item.get('skills', []))}" for item in postings]
    semantic, engine = rank(profile, descriptions)
    skill_scores = {}
    for name, score in skills.items():
        for alias in [name, *ALIASES.get(name, [])]:
            skill_scores[alias.casefold()] = max(0, min(100, int(score)))
    output = []
    for item, similarity in zip(postings, semantic):
        required = [str(skill) for skill in item.get("skills", [])]
        covered = [skill for skill in required if skill.casefold() in skill_scores and skill_scores[skill.casefold()] >= 60]
        coverage = round(100 * len(covered) / len(required)) if required else similarity
        readiness = round(0.65 * coverage + 0.35 * similarity) if required else similarity
        bucket = "ready_now" if readiness >= 75 and (not required or coverage >= 60) else "stretch" if readiness >= 45 else "not_yet"
        output.append({**item, "semantic_similarity": similarity, "skill_coverage": coverage,
                       "readiness_score": readiness, "readiness_bucket": bucket,
                       "matched_skills": covered, "missing_skills": [skill for skill in required if skill not in covered],
                       "matching_engine": engine})
    return sorted(output, key=lambda item: (-item["readiness_score"], -item["semantic_similarity"]))

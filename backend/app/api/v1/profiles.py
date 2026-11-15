"""Single-user prototype persistence for profile basics and extracted evidence."""
from __future__ import annotations

from json import dumps
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.core.mysql import connect_mysql
from backend.app.core.auth import current_identity, require_own_profile
from fastapi import Depends

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


class ProfileIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    display_name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=254)
    branch: str | None = Field(default=None, max_length=160)


class EvidenceItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    skill: str = Field(min_length=1, max_length=120)
    evidence_score: int = Field(ge=0, le=100)
    evidence_level: Literal["weak", "medium", "strong"]
    source_type: Literal["RESUME", "GITHUB", "PROJECT", "LINKEDIN", "MANUAL"] = "RESUME"
    source_label: str | None = Field(default=None, max_length=255)
    excerpt: str = Field(default="", max_length=2000)


class EvidenceBatch(BaseModel):
    skills: list[EvidenceItem] = Field(max_length=100)


class QuizAttemptIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    skill: str = Field(min_length=1, max_length=120)
    score: int = Field(ge=0, le=100)
    question_ids: list[str] = Field(min_length=1, max_length=20)
    sub_scores: dict[str, int] = Field(default_factory=dict)

    @field_validator("sub_scores")
    @classmethod
    def validate_subscores(cls, value):
        if any(not key.strip() or len(key) > 120 or score < 0 or score > 100 for key, score in value.items()):
            raise ValueError("Sub-concept scores must have a name and be between 0 and 100.")
        return value


@router.get("/{profile_id}")
def get_profile(profile_id: int, identity: dict = Depends(current_identity)) -> dict:
    require_own_profile(profile_id, identity)
    connection = connect_mysql()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, display_name, email, branch FROM student_profiles WHERE id = %s", (profile_id,))
            profile = cursor.fetchone()
            if not profile:
                raise HTTPException(status_code=404, detail="Profile not found")
            cursor.execute(
                """SELECT s.name AS skill, e.evidence_score, e.evidence_level, e.source_type,
                          e.source_label, e.excerpt
                   FROM evidence_items e JOIN skills s ON s.id = e.skill_id
                   WHERE e.profile_id = %s ORDER BY e.created_at DESC""",
                (profile_id,),
            )
            evidence = cursor.fetchall()
        return {"profile": profile, "evidence": evidence}
    finally:
        connection.close()


@router.put("/{profile_id}")
def save_profile(profile_id: int, profile: ProfileIn, identity: dict = Depends(current_identity)) -> dict:
    require_own_profile(profile_id, identity)
    connection = connect_mysql()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO student_profiles (id, display_name, email, branch)
                   VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE display_name=VALUES(display_name),
                     email=VALUES(email), branch=VALUES(branch)""",
                (profile_id, profile.display_name, profile.email, profile.branch),
            )
        connection.commit()
        return {"id": profile_id, **profile.model_dump()}
    except Exception as exc:
        connection.rollback()
        raise HTTPException(status_code=503, detail="Could not save the profile. Apply the MySQL schema and retry.") from exc
    finally:
        connection.close()


@router.put("/{profile_id}/evidence")
def save_evidence(profile_id: int, batch: EvidenceBatch, identity: dict = Depends(current_identity)) -> dict:
    require_own_profile(profile_id, identity)
    connection = connect_mysql()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM student_profiles WHERE id = %s", (profile_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Save the profile before saving evidence")
            cursor.execute("DELETE FROM evidence_items WHERE profile_id = %s", (profile_id,))
            for item in batch.skills:
                cursor.execute(
                    """INSERT INTO skills (name, cluster_name, aliases, active)
                       VALUES (%s, 'Uncategorized', JSON_ARRAY(), TRUE)
                       ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)""",
                    (item.skill,),
                )
                cursor.execute("SELECT id FROM skills WHERE name = %s", (item.skill,))
                skill_id = cursor.fetchone()["id"]
                cursor.execute(
                    """INSERT INTO evidence_items
                       (profile_id, skill_id, source_type, source_label, excerpt, evidence_level, evidence_score)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (profile_id, skill_id, item.source_type, item.source_label, item.excerpt,
                     item.evidence_level.upper(), item.evidence_score),
                )
        connection.commit()
        return {"saved": len(batch.skills)}
    except HTTPException:
        connection.rollback()
        raise
    except Exception as exc:
        connection.rollback()
        raise HTTPException(status_code=503, detail="Could not save skill evidence. Apply the MySQL schema and retry.") from exc
    finally:
        connection.close()


@router.post("/{profile_id}/evidence")
def add_linkedin_evidence(profile_id: int, batch: EvidenceBatch, identity: dict = Depends(current_identity)) -> dict:
    require_own_profile(profile_id, identity)
    """Replace LinkedIn-export evidence only, preserving resume/GitHub sources."""
    if any(item.source_type != "LINKEDIN" for item in batch.skills):
        raise HTTPException(status_code=422, detail="This append endpoint accepts LinkedIn evidence only")
    connection = connect_mysql()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM student_profiles WHERE id = %s", (profile_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Save the profile before saving evidence")
            cursor.execute("DELETE FROM evidence_items WHERE profile_id = %s AND source_type = 'LINKEDIN'", (profile_id,))
            for item in batch.skills:
                cursor.execute(
                    """INSERT INTO skills (name, cluster_name, aliases, active)
                       VALUES (%s, 'Uncategorized', JSON_ARRAY(), TRUE)
                       ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)""",
                    (item.skill,),
                )
                cursor.execute("SELECT id FROM skills WHERE name = %s", (item.skill,))
                skill_id = cursor.fetchone()["id"]
                cursor.execute(
                    """INSERT INTO evidence_items
                       (profile_id, skill_id, source_type, source_label, excerpt, evidence_level, evidence_score)
                       VALUES (%s, %s, 'LINKEDIN', %s, %s, %s, %s)""",
                    (profile_id, skill_id, item.source_label, item.excerpt,
                     item.evidence_level.upper(), item.evidence_score),
                )
        connection.commit()
        return {"saved": len(batch.skills), "source_type": "LINKEDIN"}
    except HTTPException:
        connection.rollback()
        raise
    except Exception as exc:
        connection.rollback()
        raise HTTPException(status_code=503, detail="Could not save LinkedIn evidence. Apply the MySQL schema and retry.") from exc
    finally:
        connection.close()


@router.post("/{profile_id}/quiz-attempts")
def save_quiz_attempt(profile_id: int, attempt: QuizAttemptIn, identity: dict = Depends(current_identity)) -> dict:
    require_own_profile(profile_id, identity)
    """Persist one completed quiz attempt when MySQL storage is configured."""
    connection = connect_mysql()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM student_profiles WHERE id = %s", (profile_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Save the profile before saving quiz results")
            cursor.execute(
                """INSERT INTO quiz_attempts
                   (profile_id, skill_name, score, question_ids, sub_scores)
                   VALUES (%s, %s, %s, %s, %s)""",
                (profile_id, attempt.skill, attempt.score, dumps(attempt.question_ids), dumps(attempt.sub_scores)),
            )
            attempt_id = cursor.lastrowid
        connection.commit()
        return {"id": attempt_id, "profile_id": profile_id, **attempt.model_dump()}
    except HTTPException:
        connection.rollback()
        raise
    except Exception as exc:
        connection.rollback()
        raise HTTPException(status_code=503, detail="Could not save the quiz attempt. Apply the quiz-attempt schema and retry.") from exc
    finally:
        connection.close()


@router.get("/{profile_id}/quiz-attempts")
def get_quiz_attempts(profile_id: int, skill: str | None = None, limit: int = 100,
                      identity: dict = Depends(current_identity)) -> dict:
    require_own_profile(profile_id, identity)
    """Return recent durable attempts for the local demo profile."""
    limit = max(1, min(limit, 500))
    connection = connect_mysql()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM student_profiles WHERE id = %s", (profile_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Profile not found")
            query = "SELECT id, skill_name AS skill, score, question_ids, sub_scores, created_at FROM quiz_attempts WHERE profile_id = %s"
            params: list[object] = [profile_id]
            if skill:
                query += " AND skill_name = %s"
                params.append(skill)
            query += " ORDER BY created_at DESC, id DESC LIMIT %s"
            params.append(limit)
            cursor.execute(query, tuple(params))
            attempts = cursor.fetchall()
        return {"attempts": attempts}
    finally:
        connection.close()

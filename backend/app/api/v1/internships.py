"""MySQL-backed curated internship listing endpoints."""
from __future__ import annotations

from datetime import date
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.core.mysql import connect_mysql
from backend.app.core.auth import current_identity

router = APIRouter(prefix="/api/internships", tags=["internships"])


class InternshipIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    company_name: str = Field(min_length=1, max_length=200)
    internship_title: str = Field(min_length=1, max_length=200)
    required_skills: str = Field(min_length=1, max_length=1000)
    job_description: str = Field(min_length=1, max_length=12000)
    location: str | None = Field(default=None, max_length=300)
    work_mode: str = Field(default="UNSPECIFIED", max_length=100)
    stipend: str | None = Field(default=None, max_length=200)
    apply_url: str = Field(min_length=1, max_length=2048)
    deadline: date | None = None
    status: Literal["OPEN", "CLOSED", "NEEDS_REVIEW"] = "NEEDS_REVIEW"
    source: str = Field(min_length=1, max_length=500)
    source_checked_at: date | None = None

    @field_validator("apply_url")
    @classmethod
    def require_https_apply_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("apply_url must be a valid HTTPS URL")
        return value

    @field_validator("work_mode", mode="before")
    @classmethod
    def normalize_work_mode(cls, value: str | None) -> str:
        normalized = str(value or "UNSPECIFIED").strip().upper().replace("-", "")
        aliases = {"REMOTE": "REMOTE", "HYBRID": "HYBRID", "ONSITE": "ONSITE", "ON SITE": "ONSITE", "UNSPECIFIED": "UNSPECIFIED", "": "UNSPECIFIED"}
        if normalized not in aliases:
            raise ValueError("work_mode must be Remote, Hybrid, On-site, or Unspecified")
        return aliases[normalized]

    @model_validator(mode="after")
    def require_review_date_for_open_listing(self):
        if self.status == "OPEN" and not self.source_checked_at:
            raise ValueError("source_checked_at is required before a listing can be marked OPEN")
        return self


def _listing(row: dict) -> dict:
    return {
        "id": row["id"],
        "company": row["company_name"],
        "title": row["internship_title"],
        "requiredSkills": row["required_skills"] or "",
        "jobDescription": row["job_description"],
        "location": row["location"] or "",
        "workMode": row["work_mode"],
        "stipend": row["stipend"] or "",
        "applyUrl": row["apply_url"],
        "deadline": row["deadline"].isoformat() if row["deadline"] else "",
        "status": row["status"],
        "source": row["source"],
        "sourceCheckedAt": row["source_checked_at"].isoformat() if row["source_checked_at"] else "",
    }


@router.get("")
def list_internships(status: str | None = Query(default=None, pattern="^(OPEN|CLOSED|NEEDS_REVIEW)$")) -> dict:
    connection = connect_mysql()
    try:
        with connection.cursor() as cursor:
            sql = """SELECT p.*, GROUP_CONCAT(s.name ORDER BY s.name SEPARATOR ', ') AS required_skills
                     FROM internship_postings p
                     LEFT JOIN posting_skills ps ON ps.posting_id = p.id
                     LEFT JOIN skills s ON s.id = ps.skill_id"""
            params: tuple = ()
            if status:
                sql += " WHERE p.status = %s"
                params = (status,)
            sql += " GROUP BY p.id ORDER BY p.created_at DESC LIMIT 500"
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return {"internships": [_listing(row) for row in rows]}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Could not read internship listings. Apply the MySQL schema and retry.") from exc
    finally:
        connection.close()


@router.post("", status_code=201)
def create_internship(listing: InternshipIn, identity: dict = Depends(current_identity)) -> dict:
    connection = connect_mysql()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO internship_postings
                   (company_name, internship_title, job_description, location, work_mode,
                    stipend, apply_url, deadline, status, source, source_checked_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (listing.company_name, listing.internship_title, listing.job_description,
                 listing.location, listing.work_mode, listing.stipend, listing.apply_url,
                 listing.deadline, listing.status, listing.source, listing.source_checked_at),
            )
            posting_id = cursor.lastrowid
            for name in dict.fromkeys(skill.strip() for skill in listing.required_skills.split(",") if skill.strip()):
                cursor.execute(
                    """INSERT INTO skills (name, cluster_name, aliases, active)
                       VALUES (%s, 'Uncategorized', JSON_ARRAY(), TRUE)
                       ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)""",
                    (name[:120],),
                )
                cursor.execute("SELECT id FROM skills WHERE name = %s", (name[:120],))
                skill_id = cursor.fetchone()["id"]
                cursor.execute(
                    "INSERT INTO posting_skills (posting_id, skill_id, importance) VALUES (%s, %s, 'REQUIRED')",
                    (posting_id, skill_id),
                )
            connection.commit()
            cursor.execute(
                """SELECT p.*, GROUP_CONCAT(s.name ORDER BY s.name SEPARATOR ', ') AS required_skills
                   FROM internship_postings p
                   LEFT JOIN posting_skills ps ON ps.posting_id = p.id
                   LEFT JOIN skills s ON s.id = ps.skill_id
                   WHERE p.id = %s GROUP BY p.id""",
                (posting_id,),
            )
            return _listing(cursor.fetchone())
    except Exception as exc:
        connection.rollback()
        if getattr(exc, "args", [None])[0] == 1062:
            raise HTTPException(status_code=409, detail="This application URL is already in the internship database.") from exc
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=503, detail="Could not save internship. Confirm the MySQL schema is installed.") from exc
    finally:
        connection.close()

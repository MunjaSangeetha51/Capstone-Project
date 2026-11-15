import csv
import json
from io import BytesIO
from pathlib import Path

from docx import Document
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from backend.data import POSTINGS, QUIZ
from backend.main import app


client = TestClient(app)


def test_health_and_frontend_are_served():
    assert client.get("/api/health").json() == {"status": "ok"}
    response = client.get("/")
    assert response.status_code == 200
    assert "SkillProof" in response.text
    assert "Entries save to MySQL when configured" in response.text
    assert "https://internshala.com/internship/detail/" in response.text
    assert 'id="resumeFile" type="file"' in response.text
    assert 'id="surveyCsv" type="file"' in response.text
    assert "File → Download → Comma-separated values (.csv)" in response.text
    assert "Survey Data File" in response.text
    assert "toggleInternshipReport" in response.text
    assert "internshipReport(p)" in response.text
    assert 'id="internshipCsv" type="file"' in response.text
    assert "parseInternshipCsv" in response.text
    assert "loadVerifiedInternships" in response.text
    assert "internship_listings_verified_2026-11-11.csv" in response.text
    snapshot = client.get("/internship_listings_verified_2026-11-11.csv")
    assert snapshot.status_code == 200
    assert "Nexicat,Software Development Intern" in snapshot.text
    assert "Apply URL" in response.text
    assert 'id="rt"' not in response.text
    for section in (
        "Personal Information", "Academic Details", "Technical Skills", "Project Details",
        "Internship Experience", "Certifications and Achievements",
        "Resume and Professional Links", "Career Preferences",
    ):
        assert section in response.text


def test_researched_internship_snapshot_has_import_schema_and_secure_links():
    snapshot = Path(__file__).resolve().parents[1] / "frontend" / "internship_listings_verified_2026-11-11.csv"
    with snapshot.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    assert reader.fieldnames == [
        "Company Name", "Internship Title", "Required Skills", "Job Description",
        "Location", "Work Mode", "Stipend", "Apply URL", "Posted Date",
        "Deadline", "Status", "Source",
    ]
    assert [row["Company Name"] for row in rows] == ["Nexicat", "Qubixo", "PayPal"]
    assert all(row["Apply URL"].startswith("https://") for row in rows)
    assert all(row["Job Description"] and row["Source"] for row in rows)


def test_parse_scores_contextual_evidence():
    response = client.post(
        "/api/parse",
        json={
            "resume": "Built a Python Flask attendance tracker serving 200+ records.",
            "github": "Python project with a documented API.",
        },
    )
    assert response.status_code == 200
    python = next(skill for skill in response.json()["skills"] if skill["skill"] == "Python")
    assert python["evidence"] > 0
    assert python["mentions"] == 2
    assert python["context"]


def test_upload_parses_resume_and_optional_github_readme():
    response = client.post(
        "/api/parse/upload",
        files=[
            ("resume_file", ("resume.txt", b"Built a Python Flask attendance tracker.", "text/plain")),
            ("github_file", ("README.md", b"Implemented a JavaScript React portfolio.", "text/markdown")),
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["files"] == {"resume": "resume.txt", "github": "README.md"}
    assert {skill["skill"] for skill in body["skills"]} >= {"Python", "JavaScript"}


def test_upload_extracts_docx_resume_text():
    document = Document()
    document.add_paragraph("Built a Python Flask attendance tracker.")
    content = BytesIO()
    document.save(content)

    response = client.post(
        "/api/parse/upload",
        files={"resume_file": ("resume.docx", content.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert response.status_code == 200
    assert response.json()["skills"][0]["skill"] == "Python"


def test_upload_extracts_pdf_resume_text():
    content = BytesIO()
    pdf = canvas.Canvas(content)
    pdf.drawString(72, 720, "Built a Python Flask attendance tracker.")
    pdf.save()

    response = client.post(
        "/api/parse/upload",
        files={"resume_file": ("resume.pdf", content.getvalue(), "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["skills"][0]["skill"] == "Python"


def test_upload_reports_scanned_or_textless_pdf():
    content = BytesIO()
    pdf = canvas.Canvas(content)
    pdf.showPage()
    pdf.save()

    response = client.post(
        "/api/parse/upload",
        files={"resume_file": ("scanned-resume.pdf", content.getvalue(), "application/pdf")},
    )
    assert response.status_code == 422
    assert "Scanned PDFs need OCR" in response.json()["detail"]


def test_upload_rejects_unsupported_and_oversized_files():
    unsupported = client.post(
        "/api/parse/upload",
        files={"resume_file": ("resume.rtf", b"Python", "text/rtf")},
    )
    oversized = client.post(
        "/api/parse/upload",
        files={"resume_file": ("resume.txt", b"x" * (5 * 1024 * 1024 + 1), "text/plain")},
    )
    assert unsupported.status_code == 400
    assert oversized.status_code == 413


def test_job_match_compares_resume_skills_and_keywords_without_returning_source_text():
    resume = "Built a Python Flask attendance tracker serving 200 students."
    response = client.post(
        "/api/job-match",
        json={
            "resume": resume,
            "job_description": "Python developer role. Must know SQL and Django, plus database design.",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["required_skills"] == ["Python", "SQL"]
    assert body["matched_skills"] == [{
        "skill": "Python",
        "evidence": 30,
        "quiz_score": None,
        "verified": 12,
        "status": "unverified",
    }]
    assert body["missing_skills"] == ["SQL"]
    assert body["skill_score"] == 8
    assert body["skill_analysis"][1]["status"] == "not_yet"
    assert "python" in body["matched_keywords"]
    assert "developer" in body["missing_keywords"]
    assert "developer." not in body["missing_keywords"]
    assert body["score_type"] == "skill_and_keyword_overlap"
    assert "resume" not in body and resume not in response.text


def test_job_match_can_use_optional_github_project_evidence():
    response = client.post(
        "/api/job-match/upload",
        data={"job_description": "JavaScript developer role."},
        files=[
            ("resume_file", ("resume.txt", b"Student seeking an internship.", "text/plain")),
            ("github_file", ("README.md", b"Built a JavaScript React portfolio.", "text/markdown")),
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["github_file"] == "README.md"
    assert body["skill_analysis"][0]["skill"] == "JavaScript"
    assert body["skill_analysis"][0]["evidence"] > 0


def test_job_match_uses_quiz_scores_and_surfaces_hidden_strengths():
    response = client.post(
        "/api/job-match",
        json={
            "resume": "Built a Python web application.",
            "job_description": "Python and SQL developer.",
            "quiz": {"Python": 100, "SQL": 90},
        },
    )
    assert response.status_code == 200
    body = response.json()
    python, sql = body["skill_analysis"]
    assert python == {
        "skill": "Python",
        "evidence": 30,
        "quiz_score": 100,
        "verified": 79,
        "status": "ready",
    }
    assert sql == {
        "skill": "SQL",
        "evidence": 0,
        "quiz_score": 90,
        "verified": 63,
        "status": "hidden_strength",
    }
    assert body["skill_score"] == 92
    assert body["missing_skills"] == []
    assert any("hidden strengths" in suggestion for suggestion in body["suggestions"])


def test_job_match_upload_and_validation():
    response = client.post(
        "/api/job-match/upload",
        data={
            "job_description": "Python developer with SQL and project experience.",
            "quiz_scores": '{"Python": 85}',
        },
        files={"resume_file": ("my-resume.txt", b"Built a Python web application.", "text/plain")},
    )
    assert response.status_code == 200
    assert response.json()["resume_file"] == "my-resume.txt"
    assert response.json()["skill_analysis"][0]["quiz_score"] == 85
    assert "resume" not in response.json()

    empty_job = client.post(
        "/api/job-match/upload",
        data={"job_description": " "},
        files={"resume_file": ("resume.txt", b"Python", "text/plain")},
    )
    oversized_job = client.post(
        "/api/job-match/upload",
        data={"job_description": "x" * 30_001},
        files={"resume_file": ("resume.txt", b"Python", "text/plain")},
    )
    oversized_resume = client.post(
        "/api/job-match/upload",
        data={"job_description": "Python developer role."},
        files={"resume_file": ("resume.txt", b"x" * 100_001, "text/plain")},
    )
    invalid_quiz = client.post(
        "/api/job-match/upload",
        data={"job_description": "Python developer role.", "quiz_scores": '{"Rust": 80}'},
        files={"resume_file": ("resume.txt", b"Python", "text/plain")},
    )
    assert empty_job.status_code == 422
    assert oversized_job.status_code == 422
    assert oversized_resume.status_code == 422
    assert invalid_quiz.status_code == 422


def test_job_match_upload_rejects_non_object_quiz_payloads():
    response = client.post(
        "/api/job-match/upload",
        data={"job_description": "Python developer role.", "quiz_scores": "[]"},
        files={"resume_file": ("resume.txt", b"Python", "text/plain")},
    )
    assert response.status_code == 422
    assert "JSON object" in response.json()["detail"]


def test_quiz_does_not_expose_answers_and_scores_all_questions():
    skill = "Python"
    quiz = client.get(f"/api/quiz/{skill}")
    assert quiz.status_code == 200
    questions = quiz.json()["questions"]
    assert all("a" not in question for question in questions)
    assert len(questions) == 4
    answer_key = {question["id"]: question["a"] for question in QUIZ[skill]}

    result = client.post(
        "/api/score",
        json={
            "skill": skill,
            "question_ids": [question["id"] for question in questions],
            "answers": {question["id"]: answer_key[question["id"]] for question in questions},
        },
    )
    assert result.status_code == 200
    assert result.json()["score"] == 100
    assert result.json()["weakest"] is None


def test_adaptive_quiz_targets_weak_subconcept_without_repeating_questions():
    skill = "Python"
    first = client.get(f"/api/quiz/{skill}").json()["questions"]
    seen = [question["id"] for question in first]
    second_response = client.get(
        f"/api/quiz/{skill}",
        params={"sub_scores": '{"Loops":20,"OOP":80,"Error handling":80}', "seen_ids": json.dumps(seen)},
    )
    assert second_response.status_code == 200
    second = second_response.json()
    assert second["adaptive"] is True
    assert not (set(seen) & {question["id"] for question in second["questions"]})
    assert second["questions"][0]["sub"] == "Loops"


def test_score_rejects_incomplete_answers():
    response = client.post("/api/score", json={"skill": "Python", "answers": {}})
    assert response.status_code == 422


def test_analyze_returns_complete_dashboard_data():
    response = client.post(
        "/api/analyze",
        json={"evidence": {"Python": 80}, "quiz": {"Python": 90}},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "verified", "mismatches", "ready", "stretch", "notyet", "readiness",
        "leverage", "simulation", "roles", "skills_verified",
    }
    assert body["verified"]["Python"] == 87
    assert len(body["ready"]) + len(body["stretch"]) + len(body["notyet"]) == len(POSTINGS)


def test_analyze_rejects_invalid_scores_and_unknown_skills():
    assert client.post("/api/analyze", json={"evidence": {"Python": 101}}).status_code == 422
    assert client.post("/api/analyze", json={"quiz": {"Rust": 80}}).status_code == 422

"""SkillProof backend. Run from the project root: uvicorn backend.main:app --reload."""
import re
import base64
from collections import Counter
from contextlib import asynccontextmanager
from io import BytesIO
from json import JSONDecodeError, loads
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile, Depends
from fastapi.responses import FileResponse
import httpx
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError, field_validator
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .data import PATTERNS, QUIZ, RESOURCES, POSTINGS, ROLES
from .app.api.v1.jobs import router as jobs_router
from .app.api.v1.internships import router as internships_router
from .app.api.v1.profiles import router as profiles_router
from .app.api.v1.auth import router as auth_router
from .app.core.free_llm import close_free_llm_client
from .app.core.mysql import is_mysql_configured, connect_mysql
from .app.services.free_job_engine import close_job_harvester
from .app.services.semantic_matcher import match_profile_to_postings
from .app.core.auth import current_identity
from .app.services.free_job_engine import get_job_harvester


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize external-data/LLM clients only when their feature is requested.
    # The core dashboard must start without API keys or network access.
    yield
    # Shutdown: close clients
    await close_job_harvester()
    await close_free_llm_client()


app = FastAPI(title="SkillProof", version="1.0.0", lifespan=lifespan)

# Include the new jobs router
app.include_router(jobs_router)
app.include_router(internships_router)
app.include_router(profiles_router)
app.include_router(auth_router)

VERBS = re.compile(r"\b(built|developed|implemented|deployed|designed|trained|created|optimi[sz]ed|"
                   r"integrated|engineered|automated)\b", re.I)
METRIC = re.compile(r"\d+\s*(%|\+|k\b|users|rows|records|ms|x\b)|github\.com|https?://", re.I)
PROVEN = 75  # level assumed once a skill is "fixed and proven"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
_EVIDENCE_MODEL = None
_EVIDENCE_MODEL_LOADED = False
ALLOWED_UPLOAD_TYPES = {".docx", ".md", ".pdf", ".txt"}
JOB_DESCRIPTION_MAX_CHARS = 30_000
JOB_MATCH_STOPWORDS = {
    "about", "able", "across", "also", "and", "any", "are", "as", "at", "be", "but",
    "can", "candidate", "company", "could", "day", "demonstrate", "desired", "each",
    "experience", "for", "from", "good", "have", "help", "including", "into", "is",
    "job", "join", "knowledge", "looking", "make", "more", "must", "our", "other",
    "people", "plus", "position", "preferred", "provide", "role", "should", "skill",
    "skills", "strong", "such", "team", "that", "the", "their", "them", "they",
    "this", "those", "through", "time", "to", "use", "using", "various", "want",
    "we", "well", "what", "when", "who", "will", "with", "work", "working", "you",
    "your", "year",
}


# ---------- 1. Evidence-depth scoring ----------
def evidence_for(lines, patterns):
    total, hits, ctx = 0, 0, []
    for ln in lines:
        if not any(p.search(ln) for p in patterns):
            continue
        hits += 1
        if ln.count(",") >= 4:            # bare skills-list line -> weak evidence
            pts = 8
        else:
            pts = 12 + (18 if VERBS.search(ln) else 0) + (12 if METRIC.search(ln) else 0) + (8 if len(ln) > 80 else 0)
        total += pts
        if len(ctx) < 2:
            ctx.append(ln.strip()[:150])
    return min(100, total), hits, ctx


class ParseIn(BaseModel):
    resume: str = ""
    github: str = ""

    @field_validator("resume", "github")
    @classmethod
    def limit_text_size(cls, value):
        if len(value) > 100_000:
            raise ValueError("Text must be 100,000 characters or fewer.")
        return value


class GithubProfileIn(BaseModel):
    username: str = Field(min_length=1, max_length=255)

    @field_validator("username")
    @classmethod
    def validate_github_username(cls, value):
        value = value.strip().rstrip("/")
        if value.startswith("https://github.com/"):
            value = value.removeprefix("https://github.com/").split("/", 1)[0]
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", value):
            raise ValueError("Enter a public GitHub username or profile URL.")
        return value


class JobMatchIn(BaseModel):
    resume: str
    job_description: str
    github: str = ""
    quiz: dict[str, int] = Field(default_factory=dict)

    @field_validator("resume", "github")
    @classmethod
    def limit_source_size(cls, value, info):
        if info.field_name == "resume" and not value.strip():
            raise ValueError("Resume text cannot be empty.")
        if len(value) > 100_000:
            raise ValueError("Each source text must be 100,000 characters or fewer.")
        return value

    @field_validator("job_description")
    @classmethod
    def validate_job_description(cls, value):
        if not value.strip():
            raise ValueError("Job description cannot be empty.")
        if len(value) > JOB_DESCRIPTION_MAX_CHARS:
            raise ValueError("Job description must be 30,000 characters or fewer.")
        return value

    @field_validator("quiz")
    @classmethod
    def validate_quiz_scores(cls, scores):
        if not isinstance(scores, dict):
            raise ValueError("Quiz scores must be a JSON object.")
        unknown_skills = set(scores) - set(QUIZ)
        if unknown_skills:
            raise ValueError(f"Unknown skill(s): {', '.join(sorted(unknown_skills))}")
        if any(isinstance(score, bool) or not isinstance(score, int) or score < 0 or score > 100 for score in scores.values()):
            raise ValueError("Quiz scores must be between 0 and 100.")
        return scores


class SemanticPostingIn(BaseModel):
    id: int | str | None = None
    company: str = Field(default="", max_length=200)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=30_000)
    skills: list[str] = Field(default_factory=list, max_length=100)
    apply_url: str | None = Field(default=None, max_length=2048)


class SemanticMatchIn(BaseModel):
    skills: dict[str, int] = Field(min_length=1, max_length=100)
    postings: list[SemanticPostingIn] | None = Field(default=None, max_length=500)

    @field_validator("skills")
    @classmethod
    def validate_semantic_skills(cls, skills):
        if any(not name.strip() or not 0 <= score <= 100 for name, score in skills.items()):
            raise ValueError("Provide skill names and scores from 0 to 100.")
        return skills


@app.post("/api/parse")
def parse(b: ParseIn):
    text = b.resume + "\n" + b.github
    return {"skills": score_evidence(text)}


@app.post("/api/parse/github")
async def parse_public_github(b: GithubProfileIn):
    """Analyze recent public repository READMEs via GitHub's public REST API."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SkillProof-Student-Prototype",
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0), follow_redirects=False) as client:
            response = await client.get(
                f"https://api.github.com/users/{b.username}/repos",
                params={"sort": "updated", "per_page": 12, "type": "owner"},
                headers=headers,
            )
            if response.status_code == 404:
                raise HTTPException(404, "GitHub user was not found.")
            if response.status_code == 403:
                raise HTTPException(429, "GitHub API rate limit reached. Try later or upload a README instead.")
            response.raise_for_status()
            repositories = response.json()
            chunks, sources, total_chars = [], [], 0
            for repo in repositories:
                if repo.get("fork") or repo.get("archived"):
                    continue
                name = repo.get("name", "")
                readme_url = f"https://api.github.com/repos/{b.username}/{name}/readme"
                readme = await client.get(readme_url, headers=headers)
                if readme.status_code == 404:
                    continue
                readme.raise_for_status()
                payload = readme.json()
                if payload.get("encoding") != "base64" or not payload.get("content"):
                    continue
                try:
                    text = base64.b64decode(payload["content"], validate=False).decode("utf-8", errors="ignore")
                except (ValueError, TypeError):
                    continue
                text = text[:20_000]
                if not text.strip():
                    continue
                remaining = 100_000 - total_chars
                text = text[:remaining]
                if not text:
                    break
                chunks.append(text)
                total_chars += len(text)
                sources.append({"name": name, "url": repo.get("html_url", "")})
                if len(sources) >= 8 or total_chars >= 100_000:
                    break
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "GitHub did not respond in time. Upload a README instead.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "Could not read public GitHub repositories. Upload a README instead.") from exc

    if not chunks:
        raise HTTPException(422, "No readable README files were found in the user's recent public repositories.")
    github_text = "\n".join(chunks)
    skills = score_evidence(github_text)
    evidence_items = [{
        "skill": item["skill"], "evidence_score": item["evidence"],
        "evidence_level": item["level"], "source_type": "GITHUB",
        "source_label": ", ".join(source["name"] for source in sources[:3]),
        "excerpt": "\n".join(item["context"]),
    } for item in skills]
    return {"skills": skills, "evidence_items": evidence_items, "repositories": sources}


@app.post("/api/parse/linkedin-export")
async def parse_linkedin_export(linkedin_file: UploadFile = File(...)):
    """Analyze a user's own LinkedIn data export; this does not use LinkedIn OAuth or scrape profiles."""
    filename = Path(linkedin_file.filename or "").name
    extension = Path(filename).suffix.lower()
    if extension not in {".zip", ".csv"}:
        raise HTTPException(400, "Upload a LinkedIn data-export ZIP or a Skills.csv file.")
    content = await linkedin_file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(400, "The selected LinkedIn export is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "LinkedIn exports must be 5 MB or smaller.")

    sources: list[tuple[str, bytes]] = []
    if extension == ".csv":
        if Path(filename).name.casefold() != "skills.csv":
            raise HTTPException(400, "For a CSV upload, choose the Skills.csv file from your LinkedIn export.")
        sources.append((filename, content))
    else:
        try:
            with ZipFile(BytesIO(content)) as archive:
                total_uncompressed = 0
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    basename = Path(member.filename.replace("\\", "/")).name.casefold()
                    if basename not in {"skills.csv", "profile.csv", "projects.csv", "positions.csv", "certifications.csv"}:
                        continue
                    total_uncompressed += member.file_size
                    if total_uncompressed > 2 * 1024 * 1024:
                        raise HTTPException(413, "Supported LinkedIn CSV files exceed the 2 MB expanded-data limit.")
                    if member.file_size > 1024 * 1024:
                        continue
                    sources.append((basename, archive.read(member)))
        except BadZipFile as exc:
            raise HTTPException(400, "The LinkedIn export is not a valid ZIP archive.") from exc
        if not any(Path(name).name.casefold() == "skills.csv" for name, _ in sources):
            raise HTTPException(422, "No Skills.csv was found. Export your LinkedIn data and include the Skills file.")

    text_parts = []
    for source_name, raw in sources:
        try:
            decoded = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(400, f"{source_name} must use UTF-8 encoding.") from exc
        if len(decoded) > 100_000:
            decoded = decoded[:100_000]
        text_parts.append(f"LinkedIn export file: {source_name}\n{decoded}")
    skills = score_evidence("\n".join(text_parts))
    if not skills:
        raise HTTPException(422, "No skills from SkillProof's current supported skill list were found in this export.")
    evidence_items = [{
        "skill": item["skill"], "evidence_score": item["evidence"],
        "evidence_level": item["level"], "source_type": "LINKEDIN",
        "source_label": filename, "excerpt": "\n".join(item["context"]),
    } for item in skills]
    return {"skills": skills, "evidence_items": evidence_items, "source": filename,
            "notice": "LinkedIn-listed skills are self-reported profile claims, not independent proof of proficiency."}


def score_evidence(text):
    lines = [l.strip() for l in re.split(r"\n+|(?<=[.!?])\s+", text) if l.strip()]
    out = []
    for skill, pats in PATTERNS.items():
        score, hits, ctx = evidence_for(lines, pats)
        if hits:
            level = "weak" if score < 30 else "medium" if score < 60 else "strong"
            method = "rule_based"
            model = _load_evidence_model()
            if model is not None:
                try:
                    level = str(model.predict([f"{skill}: {' '.join(ctx)}"])[0]).lower()
                    method = "trained_classifier"
                except Exception:
                    # Keep the transparent baseline available if a local model is stale or incompatible.
                    pass
            out.append({"skill": skill, "evidence": score, "mentions": hits, "level": level,
                        "method": method, "context": ctx})
    return sorted(out, key=lambda x: -x["evidence"])


def _load_evidence_model():
    global _EVIDENCE_MODEL, _EVIDENCE_MODEL_LOADED
    if _EVIDENCE_MODEL_LOADED:
        return _EVIDENCE_MODEL
    _EVIDENCE_MODEL_LOADED = True
    model_path = Path(__file__).resolve().parent.parent / "evaluation" / "evidence_classifier.joblib"
    if model_path.is_file():
        try:
            from joblib import load
            _EVIDENCE_MODEL = load(model_path)
        except Exception:
            _EVIDENCE_MODEL = None
    return _EVIDENCE_MODEL


def meaningful_terms(text):
    tokens = re.findall(r"[a-z][a-z0-9+#.]{2,}", text.lower())
    terms = (token.rstrip(".") for token in tokens)
    return Counter(term for term in terms if term and term not in JOB_MATCH_STOPWORDS)


def build_job_match(resume_text, job_description, quiz_scores=None, github_text=""):
    source_text = resume_text + "\n" + github_text
    resume_skills = {item["skill"]: item for item in score_evidence(source_text)}
    quiz_scores = quiz_scores or {}
    required_skills = [
        skill for skill, patterns in PATTERNS.items()
        if any(pattern.search(job_description) for pattern in patterns)
    ]
    evidence_scores = {skill: item["evidence"] for skill, item in resume_skills.items()}
    corrected_scores = verified_levels(evidence_scores, quiz_scores)
    skill_analysis = []
    for skill in required_skills:
        evidence = evidence_scores.get(skill, 0)
        quiz = quiz_scores.get(skill)
        verified = corrected_scores[skill]
        if not evidence and quiz is not None and quiz >= 60:
            status = "hidden_strength"
        elif verified >= PROVEN:
            status = "ready"
        elif verified >= 40:
            status = "stretch"
        elif evidence and quiz is None:
            status = "unverified"
        else:
            status = "not_yet"
        skill_analysis.append({
            "skill": skill,
            "evidence": evidence,
            "quiz_score": quiz,
            "verified": verified,
            "status": status,
        })
    matched_skills = [
        {key: item[key] for key in ("skill", "evidence", "quiz_score", "verified", "status")}
        for item in skill_analysis if item["evidence"] or (item["quiz_score"] or 0) >= 60
    ]
    missing_skills = [
        item["skill"] for item in skill_analysis
        if not item["evidence"] and (item["quiz_score"] or 0) < 60
    ]

    job_terms = meaningful_terms(job_description)
    resume_terms = meaningful_terms(source_text)
    keywords = sorted(job_terms, key=lambda term: (-job_terms[term], term))[:20]
    matched_keywords = [term for term in keywords if term in resume_terms]
    missing_keywords = [term for term in keywords if term not in resume_terms]
    keyword_score = round(100 * len(matched_keywords) / len(keywords)) if keywords else 0
    skill_score = (
        round(100 * sum(min(item["verified"] / PROVEN, 1) for item in skill_analysis) / len(skill_analysis))
        if skill_analysis else None
    )
    score = round(0.7 * skill_score + 0.3 * keyword_score) if skill_score is not None else keyword_score

    suggestions = []
    if missing_skills:
        suggestions.append(
            "Build evidence for missing skills before adding them to your resume: "
            + ", ".join(missing_skills) + "."
        )
    unverified_skills = [
        item["skill"] for item in skill_analysis
        if item["evidence"] and item["quiz_score"] is None
    ]
    if unverified_skills:
        suggestions.append(
            "These resume claims are discounted until verified with a SkillProof quiz: "
            + ", ".join(unverified_skills) + "."
        )
    hidden_strengths = [item["skill"] for item in skill_analysis if item["status"] == "hidden_strength"]
    if hidden_strengths:
        suggestions.append(
            "Quiz results show hidden strengths not detected in this resume: "
            + ", ".join(hidden_strengths) + ". Add accurate project evidence for them."
        )
    if missing_keywords:
        suggestions.append(
            "If accurate, reflect relevant job-description terms in your project or experience details: "
            + ", ".join(missing_keywords[:8]) + "."
        )
    if not suggestions:
        suggestions.append("Your resume includes the detected skills and keywords. Review every claim for accuracy.")

    return {
        "score": score,
        "score_type": "skill_and_keyword_overlap" if required_skills else "keyword_overlap_only",
        "skill_score": skill_score,
        "keyword_score": keyword_score,
        "required_skills": required_skills,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "skill_analysis": skill_analysis,
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "suggestions": suggestions,
    }


@app.post("/api/job-match")
def job_match(b: JobMatchIn):
    return build_job_match(b.resume, b.job_description, b.quiz, b.github)


@app.post("/api/semantic-match")
async def semantic_match(b: SemanticMatchIn, identity: dict = Depends(current_identity)):
    """Rank opportunities using SentenceTransformer embeddings with a disclosed TF-IDF fallback."""
    postings = b.postings
    if postings is None:
        curated = [{
            "id": item["id"], "company": item["company"], "title": item["title"],
            "description": item.get("description", ""), "skills": list(item.get("req", {}).keys()),
        } for item in POSTINGS]
        harvester = await get_job_harvester()
        live = [{"id": item.id, "company": item.company, "title": item.title,
                 "description": item.description, "skills": list(item.skills.keys()),
                 "apply_url": item.source_url, "source": item.source}
                for item in harvester._postings.values()]
        durable = []
        if is_mysql_configured():
            connection = connect_mysql()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("""SELECT p.id, p.company_name, p.internship_title, p.job_description,
                                             p.apply_url, GROUP_CONCAT(s.name ORDER BY s.name SEPARATOR ',') AS skills
                                      FROM internship_postings p
                                      LEFT JOIN posting_skills ps ON ps.posting_id=p.id
                                      LEFT JOIN skills s ON s.id=ps.skill_id
                                      WHERE p.status='OPEN' AND (p.deadline IS NULL OR p.deadline >= CURRENT_DATE())
                                      GROUP BY p.id ORDER BY p.created_at DESC LIMIT 500""")
                    durable = [{"id": f"db-{row['id']}", "company": row["company_name"],
                                "title": row["internship_title"], "description": row["job_description"],
                                "apply_url": row["apply_url"],
                                "skills": [name for name in (row["skills"] or "").split(",") if name]}
                               for row in cursor.fetchall()]
            finally:
                connection.close()
        postings = curated + live + durable
    else:
        postings = [posting.model_dump(exclude_none=True) for posting in postings]
    return {"matches": match_profile_to_postings(b.skills, postings), "count": len(postings)}


async def extract_upload(upload: UploadFile) -> str:
    filename = Path(upload.filename or "").name
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(400, "Upload a PDF, DOCX, Markdown, or TXT file.")

    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Each upload must be 5 MB or smaller.")
    if not content:
        raise HTTPException(400, "The selected file is empty.")

    if extension in {".txt", ".md"}:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(400, "Text files must use UTF-8 encoding.") from exc
    elif extension == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise HTTPException(400, "The uploaded file is not a valid PDF.")
        try:
            text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
        except (PdfReadError, ValueError) as exc:
            raise HTTPException(400, "Could not read the PDF. Please upload a valid PDF.") from exc
    else:
        try:
            text = "\n".join(paragraph.text for paragraph in Document(BytesIO(content)).paragraphs)
        except (BadZipFile, PackageNotFoundError) as exc:
            raise HTTPException(400, "Could not read the DOCX. Please upload a valid DOCX file.") from exc

    if not text.strip():
        raise HTTPException(
            422,
            "No readable text was found. Scanned PDFs need OCR before they can be analyzed.",
        )
    return text


@app.post("/api/parse/upload")
async def parse_upload(
    resume_file: UploadFile = File(...),
    github_file: UploadFile | None = File(default=None),
):
    resume_text = await extract_upload(resume_file)
    github_text = await extract_upload(github_file) if github_file else ""
    skills = score_evidence(resume_text + "\n" + github_text)
    evidence_items = []
    sources = [
        ("RESUME", Path(resume_file.filename or "resume").name, resume_text),
        ("PROJECT", Path(github_file.filename).name if github_file and github_file.filename else "", github_text),
    ]
    for source_type, source_label, source_text in sources:
        if not source_text:
            continue
        evidence_items.extend({
            "skill": item["skill"],
            "evidence_score": item["evidence"],
            "evidence_level": item["level"],
            "source_type": source_type,
            "source_label": source_label,
            "excerpt": "\n".join(item["context"]),
        } for item in score_evidence(source_text))
    return {
        "skills": skills,
        "evidence_items": evidence_items,
        "files": {
            "resume": Path(resume_file.filename or "").name,
            "github": Path(github_file.filename).name if github_file and github_file.filename else None,
        },
    }


@app.post("/api/job-match/upload")
async def job_match_upload(
    resume_file: UploadFile = File(...),
    job_description: str = Form(...),
    quiz_scores: str = Form("{}"),
    github_file: UploadFile | None = File(default=None),
):
    if not job_description.strip():
        raise HTTPException(422, "Job description cannot be empty.")
    if len(job_description) > JOB_DESCRIPTION_MAX_CHARS:
        raise HTTPException(422, "Job description must be 30,000 characters or fewer.")
    try:
        raw_quiz = loads(quiz_scores)
        if not isinstance(raw_quiz, dict):
            raise ValueError("Quiz scores must be a JSON object.")
        quiz = JobMatchIn(resume="quiz validation", job_description=job_description, quiz=raw_quiz).quiz
    except (JSONDecodeError, TypeError) as exc:
        raise HTTPException(422, "Quiz scores must be a JSON object.") from exc
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, str(exc)) from exc
    resume_text = await extract_upload(resume_file)
    if len(resume_text) > 100_000:
        raise HTTPException(422, "Extracted resume text must be 100,000 characters or fewer.")
    github_text = await extract_upload(github_file) if github_file else ""
    if len(github_text) > 100_000:
        raise HTTPException(422, "Extracted project text must be 100,000 characters or fewer.")
    return {
        **build_job_match(resume_text, job_description, quiz, github_text),
        "resume_file": Path(resume_file.filename or "").name,
        "github_file": Path(github_file.filename).name if github_file and github_file.filename else None,
    }


# ---------- 2. Adaptive-style quiz + sub-concept diagnosis ----------
@app.get("/api/skills")
def skills():
    return {"skills": list(QUIZ.keys())}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def runtime_config():
    return {"mysql_configured": is_mysql_configured()}


@app.get("/api/quiz/{skill:path}")
def quiz(skill: str, sub_scores: str | None = Query(default=None, max_length=2000),
         seen_ids: str | None = Query(default=None, max_length=2000)):
    if skill not in QUIZ:
        raise HTTPException(404, "Unknown skill")
    scores = {}
    seen = set()
    try:
        if sub_scores:
            scores = loads(sub_scores)
            if not isinstance(scores, dict) or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 100 for value in scores.values()):
                raise ValueError
        if seen_ids:
            parsed_seen = loads(seen_ids)
            if not isinstance(parsed_seen, list) or len(parsed_seen) > 100:
                raise ValueError
            seen = {str(question_id) for question_id in parsed_seen}
    except (JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(422, "sub_scores and seen_ids must be valid JSON values") from exc

    pool = QUIZ[skill]
    candidates = [question for question in pool if question["id"] not in seen] or pool
    if scores:
        candidates.sort(key=lambda question: (scores.get(question["sub"], 50), question["id"]))
    else:
        # First attempt samples across concepts before repeating one.
        by_sub = {}
        for question in candidates:
            by_sub.setdefault(question["sub"], []).append(question)
        candidates = [group[index] for index in range(max(map(len, by_sub.values())))
                     for group in by_sub.values() if index < len(group)]
    selected = candidates[:4]
    return {"skill": skill, "adaptive": bool(scores or seen),
            "questions": [{k: v for k, v in q.items() if k != "a"} for q in selected]}


class ScoreIn(BaseModel):
    skill: str
    question_ids: list[str] = Field(default_factory=list, max_length=4)
    answers: dict[str, int]


@app.post("/api/score")
def score(b: ScoreIn):
    if b.skill not in QUIZ:
        raise HTTPException(404, "Unknown skill")
    pool = QUIZ[b.skill]
    bank = {q["id"]: q for q in pool}
    selected_ids = b.question_ids or [q["id"] for q in pool[:4]]
    if not 1 <= len(selected_ids) <= 4 or len(set(selected_ids)) != len(selected_ids) or not set(selected_ids) <= set(bank):
        raise HTTPException(422, "Submit a valid set of one to four quiz question IDs.")
    questions = [bank[question_id] for question_id in selected_ids]
    if set(b.answers) != set(selected_ids):
        raise HTTPException(422, "Answer every delivered question before submitting.")
    if any(b.answers[q["id"]] < 0 or b.answers[q["id"]] >= len(q["options"]) for q in questions):
        raise HTTPException(422, "Each answer must select a valid option.")
    subs, correct = {}, 0
    for q in questions:
        s = subs.setdefault(q["sub"], [0, 0])
        s[1] += 1
        if b.answers.get(q["id"]) == q["a"]:
            s[0] += 1
            correct += 1
    pct = {k: round(100 * c / t) for k, (c, t) in subs.items()}
    weakest = min(pct, key=pct.get)
    res = None
    if pct[weakest] < 100:
        r = RESOURCES.get(b.skill, {})
        title, url = r.get(weakest) or r.get("_") or ("Search official docs", "https://www.google.com/search?q=" + b.skill)
        res = {"title": title, "url": url}
    return {"skill": b.skill, "score": round(100 * correct / len(questions)), "subs": pct,
            "weakest": weakest if pct[weakest] < 100 else None, "resource": res}


# ---------- 3-7. Mismatch, matching, leverage, simulation, roles ----------
class AnalyzeIn(BaseModel):
    evidence: dict[str, int] = Field(default_factory=dict)
    quiz: dict[str, int] = Field(default_factory=dict)

    @field_validator("evidence", "quiz")
    @classmethod
    def validate_scores(cls, scores):
        if any(isinstance(score, bool) or not isinstance(score, int) or score < 0 or score > 100 for score in scores.values()):
            raise ValueError("Skill scores must be between 0 and 100.")
        return scores


def verified_levels(ev, qz):
    v = {}
    for s in QUIZ:
        e, q = ev.get(s), qz.get(s)
        if q is not None:
            v[s] = round(0.7 * q + 0.3 * (e or 0))      # trust-corrected
        elif e is not None:
            v[s] = round(0.4 * e)                        # unverified claim is discounted
        else:
            v[s] = 0
    return v


def bucket(v):
    ready, stretch, notyet = [], [], []
    for p in POSTINGS:
        cov = sum(min(v[s] / need, 1) for s, need in p["req"].items()) / len(p["req"])
        missing = [s for s, need in p["req"].items() if v[s] < need]
        item = {**p, "coverage": round(cov * 100), "missing": missing}
        (ready if not missing else stretch if cov >= 0.7 else notyet).append(item)
    return ready, stretch, notyet


@app.post("/api/analyze")
def analyze(b: AnalyzeIn):
    unknown_skills = (set(b.evidence) | set(b.quiz)) - set(QUIZ)
    if unknown_skills:
        raise HTTPException(422, f"Unknown skill(s): {', '.join(sorted(unknown_skills))}")
    v = verified_levels(b.evidence, b.quiz)

    mism = []
    for s in QUIZ:
        e, q = b.evidence.get(s), b.quiz.get(s)
        if e is not None and q is not None:
            if e - q >= 20:
                mism.append({"skill": s, "type": "overclaimed", "evidence": e, "quiz": q,
                             "msg": f"Resume evidence ({e}) is much higher than your quiz result ({q})."})
            elif q - e >= 20:
                mism.append({"skill": s, "type": "hidden", "evidence": e, "quiz": q,
                             "msg": f"Hidden strength! Quiz ({q}) beats resume evidence ({e}). Add it to your projects."})
        elif e is not None and e >= 40:
            mism.append({"skill": s, "type": "unverified", "evidence": e, "quiz": None,
                         "msg": "Claimed with strong evidence but not verified yet. Take the quiz."})
        elif q is not None and e is None and q >= 60:
            mism.append({"skill": s, "type": "hidden", "evidence": 0, "quiz": q,
                         "msg": f"You scored {q} but never mention it. Add it to your resume."})

    ready, stretch, notyet = bucket(v)
    readiness = round(sum(i["coverage"] for i in ready + stretch + notyet) / len(POSTINGS))

    # Leverage: how many extra postings become Ready if skill s is proven
    base_ids = {p["id"] for p in ready}
    lev = []
    for s in QUIZ:
        if v[s] >= PROVEN:
            continue
        v2 = {**v, s: PROVEN}
        r2, _, _ = bucket(v2)
        new = [p for p in r2 if p["id"] not in base_ids]
        lev.append({"skill": s, "current": v[s], "unlocks": len(new),
                    "names": [f'{p["company"]} – {p["title"]}' for p in new]})
    lev.sort(key=lambda x: -x["unlocks"])

    # Simulation: greedily fix the best skill each step
    sim, cur, left = [{"step": 0, "skill": "Today", "ready": len(ready)}], dict(v), [x["skill"] for x in lev]
    while left:
        best = max(left, key=lambda s: len(bucket({**cur, s: PROVEN})[0]))
        cur[best] = PROVEN
        left.remove(best)
        sim.append({"step": len(sim), "skill": best, "ready": len(bucket(cur)[0])})

    roles = []
    for r, req in ROLES.items():
        fit = round(sum(v[s] for s in req) / len(req))
        weakest = min(req, key=lambda s: v[s])
        roles.append({"role": r, "fit": fit, "skills": req, "next": weakest if v[weakest] < 70 else None})
    roles.sort(key=lambda x: -x["fit"])

    return {"verified": v, "mismatches": mism, "ready": ready, "stretch": stretch, "notyet": notyet,
            "readiness": readiness, "leverage": lev, "simulation": sim, "roles": roles,
            "skills_verified": len(b.quiz)}


# Serve the React build at /app when generated; keep the original prototype at /.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
REACT_BUILD = PROJECT_ROOT / "frontend" / "react-build"
if REACT_BUILD.exists():
    app.mount("/react-assets", StaticFiles(directory=REACT_BUILD), name="react-assets")


@app.get("/app", include_in_schema=False)
def react_app():
    if not (REACT_BUILD / "index.html").exists():
        raise HTTPException(503, "React client is not built. Run npm install and npm run build in frontend-react.")
    return FileResponse(REACT_BUILD / "index.html")


@app.get("/project-checklist", include_in_schema=False)
def project_checklist():
    return FileResponse(PROJECT_ROOT / "PROJECT_CHECKLIST.md", media_type="text/markdown")


# Serve the original dashboard after API routes so `/api` endpoints remain reachable.
app.mount("/", StaticFiles(directory=PROJECT_ROOT / "frontend", html=True), name="web")

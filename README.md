# SkillProof â€“ Prove â€¢ Grow â€¢ Achieve

## Run locally

Python 3.10 or newer is required.

```
python -m venv venv
venv\Scripts\activate        # Windows  (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
py -3 -m uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000. The API health check is at `/api/health`.

## React client, account isolation, and semantic matching

The original dashboard remains at `/`. A React account workspace and project feature hub are available at `/app` after its production bundle has been built. Registration/sign-in, profile editing, built-in quizzes with durable attempt history, Google sign-in, and semantic opportunity ranking are available from the React client. Use **Explore demo workspace** to browse without creating an account; demo quiz results last only for that session.

1. In MySQL Workbench, execute `backend/sql/001_internships.sql`, then `backend/sql/002_accounts.sql`.
2. Copy `.env.example` to `.env`. Set the MySQL values and set `APP_SECRET_KEY` to a fresh random secret of at least 32 characters. For example, generate one with `py -3 -c "import secrets; print(secrets.token_urlsafe(48))"`; keep the result private and do not commit `.env`.
3. To enable **Sign in with Google**, create a Web OAuth client in Google Cloud Console, add the exact local origin `http://127.0.0.1:8001` to its Authorized JavaScript origins (also add the Vite origin if using it), and set `GOOGLE_CLIENT_ID` in `.env`. Install `requirements.txt` again after adding Google support, then restart FastAPI. The backend verifies Google's signed ID token and verified email, then creates or loads the matching SkillProof account. No email address is trusted from the browser alone. Without this credential, the Google option explains the required setup and password sign-in remains available.
4. Build the React client: `cd frontend-react`, `npm install`, `npm run build`.
5. Start the backend from the project root: `py -3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8001`.
6. Open `http://127.0.0.1:8001/app` and register a separate account for each student, or use Google sign-in. Course/branch is not requested by the React account forms. The original prototype remains available at `http://127.0.0.1:8001/`.

For React development with live reload, start the backend on port 8001, then run `npm run dev` inside `frontend-react` and open the Vite URL (normally `http://127.0.0.1:5173`). API requests are proxied to port 8001.

Passwords are stored as salted PBKDF2 hashes. The React account workspace uses 12-hour signed bearer tokens; profile, evidence, and quiz-history APIs check that a token owns the requested profile. Quiz attempts and profile data are stored in MySQL. Semantic matching uses SentenceTransformers (`SKILLPROOF_EMBEDDING_MODEL`, default `all-MiniLM-L6-v2`) when model weights are available; if loading fails, it transparently reports and uses a local TF-IDF fallback. The endpoint ranks the included roles and any harvested postings held by the job service. The old `/api/analyze` prototype flow remains heuristic.

This adds account separation for student profile data, but it is not a production security certification. Before public deployment, add HTTPS termination, rate limiting and abuse controls, token revocation/rotation, a secure session-storage strategy, database backups/monitoring, and operational secret management. User-supplied participant data is still required for the evaluation claims; the code does not generate research results.

## MySQL-backed prototype data

The manual internship form, saved student profile basics, extracted skill evidence, and built-in quiz-attempt history can use MySQL. Current quiz scores and adaptive state are also cached in this browser; custom-skill practice quiz banks and scores are browser-local and are not independent verification. Use MySQL-backed authentication for multi-user account data; the original dashboard at `/` remains a browser-local prototype.

1. In MySQL Workbench, open and execute `backend/sql/001_internships.sql` and `backend/sql/002_accounts.sql`.
2. Copy `.env.example` to `.env`, then set `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `APP_SECRET_KEY` for your local account. Do not commit `.env`.
3. Install updated Python dependencies with `python -m pip install -r requirements.txt` and restart Uvicorn.
4. Save your profile or extracted evidence, then add a listing in **Internship Matcher**. New records default to `NEEDS_REVIEW`; choose `OPEN` only after checking the source listing.

The listing API is `GET /api/internships` and authenticated `POST /api/internships`. Register/sign in through `POST /api/auth/register` and `/api/auth/login`; the returned bearer token is required for `/api/profiles/{id}` and that profile's evidence and quiz-attempt endpoints. The service does not scrape job boards. Keep the source URL and check the listing status and deadline before marking it open.

## Working model status

See [PROJECT_CHECKLIST.md](./PROJECT_CHECKLIST.md) for implemented features and research/deployment gaps. Quiz rounds use the student's previous sub-concept scores to prioritize weaker topics; this is a small rule-based adaptive flow, not a calibrated adaptive-testing model. Evidence-depth scoring is also rule-based, not a trained classifier.

To evaluate evidence labels, copy [evidence_labels_template.csv](./evaluation/evidence_labels_template.csv), add manually reviewed examples with `skill,text,label` columns, then run:

```
python scripts/evaluate_evidence.py evaluation/evidence_labels.csv
```

The evaluator reports accuracy, per-class precision/recall/F1, macro-F1, and a confusion matrix. No evaluation scores are claimed until a real held-out labeled dataset is supplied. To train an optional TF-IDF/logistic-regression evidence classifier, prepare at least 100 reviewed examples (at least 10 per class) using the same CSV, then run:

```
py -3 scripts/train_evidence_classifier.py evaluation/evidence_labels.csv
```

The script reports held-out metrics and writes `evaluation/evidence_classifier.joblib`; the API uses that model if present. Review it on diverse data before relying on predictions. This is an experimental baseline, not a validated classifier.

## Demo flow
In **Resume & GitHub**, you can enter a GitHub username/profile URL to analyze up to eight recent public repository READMEs through GitHub's public API. Private repositories are not accessed. You can upload your own LinkedIn data export ZIP (containing `Skills.csv`) or that CSV directly. The importer does not request your password or scrape LinkedIn; listed skills remain self-reported claims. Direct OAuth requires an approved LinkedIn application.

1. Dashboard â†’ **Run demo with sample resume**, or upload a resume from *Resume & GitHub*
2. **Skill Verification** â†’ take quizzes
3. Check Mismatch Report, Skill Gap Analysis, Internship Matcher, Skill Leverage, Career Roadmap
4. Upload a PDF, DOCX, Markdown, or TXT resume, and optionally upload a project README or your LinkedIn data export. Source files are parsed in memory and not retained; extracted skill scores and short excerpts are saved to MySQL only when configured.
5. From **Resume / Job Match**, upload a resume and paste a job description. The comparison combines resume evidence and saved quiz results, showing trust-corrected skill readiness, hidden strengths, and exact keyword overlap.
6. In **Internship Matcher**, choose **Fetch public ATS/API listings** to refresh permitted public feeds (Greenhouse, Lever, Ashby, Remotive, Arbeitnow, and The Muse); listings are labeled for source-site verification before applying. You can also load the three manually researched listings checked on 2026-11-11 or import a CSV. Browser CSV imports are local to that browser; manual form entries save to MySQL when configured. The researched CSV is at `frontend/internship_listings_verified_2026-11-11.csv`.
7. Open **View match report** for a posting to see required-skill thresholds, resume evidence, quiz results, corrected levels, job-description keyword overlap, apply link, and next steps.
8. In **Career Roadmap**, choose a skill preset or adjust the sliders, filter 23 role profiles, inspect missing skill levels, and simulate which skills could unlock matches across 69 sample job profiles. These are illustrative planning data, not verified vacancies; the slider scenario is separate from quiz-verified scores.
9. To connect the student survey sheet as a file, open **Survey Data File**, download that tab from Google Sheets as CSV, and load it for a browser-only preview. Survey rows are not used as quiz answers or internship listings.
10. Student profile basics and evidence excerpts can be saved in MySQL for the local single-user prototype. Quiz scores, imported CSV listings, and upload filenames remain in this browser; source files, job-description contents, and survey CSV contents are not retained.
11. Skill Verification and Skill Leverage expose quizzes for all 25 listed skills. Newly added built-in skill banks start with four tagged questions; existing banks have eight. Students may also add a custom skill and author a four-question practice quiz; because the author controls its answer key, that result is not independent verification and is excluded from job matching. Built-in quiz results are learning checks, not formal certifications.
12. For a real participant study, copy `evaluation/participant_study_template.csv`, collect only consented responses with pseudonymous IDs, and run `py -3 scripts/evaluate_participant_study.py your-study.csv`. The report is descriptive and only reflects the data you provide.

## Structure
- backend/main.py  â€“ FastAPI app and API routes
- backend/data.py  â€“ quiz bank (sub-concept tagged), postings, roles, resources
- frontend/index.html â€“ dashboard UI and researched-listing loader
- frontend-react/ â€“ React account workspace source and Vite configuration
- backend/app/services/semantic_matcher.py â€“ embedding ranker with reported offline fallback
- backend/sql/002_accounts.sql â€“ account-to-profile schema migration
- frontend/internship_listings_verified_2026-11-11.csv â€“ importable public listing snapshot

## API
 - `POST /api/parse/github` analyzes recent public README files for one GitHub username/profile URL.
- `GET /api/config` reports whether optional MySQL profile/listing persistence is configured.
- `GET /api/health` â€“ service health check
- `GET /api/skills` and `GET /api/quiz/{skill}` â€“ available skills and quiz questions
- `POST /api/parse` â€“ extract skills and score resume/GitHub text evidence
- `POST /api/parse/upload` â€“ upload a resume and optional project-description file for extraction and evidence scoring
- `POST /api/job-match` â€“ compare resume text, optional GitHub/project text, a job description, and optional quiz scores
- `POST /api/job-match/upload` â€“ compare an uploaded resume, optional GitHub/project file, job description, and optional quiz scores (each file maximum 5 MB)
- `POST /api/semantic-match` â€“ authenticated SentenceTransformers ranking over curated, harvested, and open MySQL postings; returns the embedding engine or TF-IDF fallback used
- `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` â€“ account access and identity
- `POST /api/score` â€“ score a completed skill quiz and return sub-topic feedback
- `POST /api/analyze` â€“ compute verified levels, mismatches, posting buckets, leverage, and role fit
- `GET /api/internships` / `POST /api/internships` â€“ read or add MySQL internship records
- `GET /api/profiles/{id}` / `PUT /api/profiles/{id}` / `PUT /api/profiles/{id}/evidence` â€“ persist the local demo profile and extracted evidence in MySQL
- `POST /jobs/harvest-free` (authenticated) / `GET /jobs/postings` â€“ refresh and list postings from permitted public ATS/job APIs (no job-board scraping)

## Current scope
- The parser and scoring are transparent rule-based baselines; they do not call an external AI service.
- Resume / Job Match calculates rule-based skill readiness from resume evidence plus quiz results and exact keyword overlap. Unverified claims are discounted; quiz-backed strengths omitted from the resume are surfaced. This is not a semantic/ATS score or hiring prediction; no resume or job-description text is sent to a third-party service. Uploaded content is processed in memory and omitted from browser storage.
- Internship matching can use local sample records in `backend/data.py`, the public listing snapshot checked on 2026-11-11, CSV imports, manually entered records, or listings refreshed from permitted public ATS/job APIs (Greenhouse, Lever, Ashby, Remotive, Arbeitnow, The Muse). The app does not scrape Internshala, LinkedIn, Wellfound, or AICTE; use their authorized access paths or enter/import listings manually. Public listings are time-sensitive; confirm availability, eligibility, and application details on source sites.
- Internship match reports compare supported listed skill thresholds against project/resume evidence and quiz-backed corrected levels. The postings do not contain employer ATS metadata or complete job descriptions, so reports are not ATS-specific scores.
- Resume upload supports text-based PDF, DOCX, Markdown, and TXT files up to 5 MB each. Scanned PDFs need OCR before upload.
- Direct OAuth, repository crawling, and LinkedIn integration are not included.
- MySQL persistence is optional and limited to profile basics, evidence snippets, and internship records. Quiz scores and other demo state remain in this browser's local storage.
- The linked Google Sheet is a student survey response form, not a quiz bank or internship-postings dataset. Its response data is intentionally not used as student quiz answers or job data.
- Google Sheets CSV import is a manual file workflow: export the sheet as CSV (Google Sheets â†’ File â†’ Download â†’ CSV), then load it in **Survey Data File**. The project cannot directly fetch the linked sheet because it requires Google authorization. CSV preview is client-side, limited to 5 MB, 100 columns, and 10,000 rows, and is cleared on page reload.
- Internship CSV import expects the 12 columns `Company Name`, `Internship Title`, `Required Skills`, `Job Description`, `Location`, `Work Mode`, `Stipend`, `Apply URL`, `Posted Date`, `Deadline`, `Status`, and `Source`. Import is client-side, accepts HTTPS apply links, and is limited to 1 MB / 500 rows. Imported listing records are saved to this browserâ€™s local storage; verify each source, active status, and deadline before applying. This project does not scrape or independently verify listing sites.
- The tab-separated header row to paste into Google Sheets cell A1 is:
  `Company Name	Internship Title	Required Skills	Job Description	Location	Work Mode	Stipend	Apply URL	Posted Date	Deadline	Status	Source`
- Imported listing match reports recognize the projectâ€™s supported skill set; unrecognized skills still appear in the required-skills text for manual review. A 60/100 baseline is used because CSV listings do not provide numeric skill weights. The resulting fit is a transparent heuristic, not a detected employer ATS score.

## Tests

```
pip install -r requirements-dev.txt
python -m pytest
```


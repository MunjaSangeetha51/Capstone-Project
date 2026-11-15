# SkillProof Technical Build Plan

## Build direction

Keep the existing FastAPI backend and vanilla HTML/JavaScript frontend for the 10-week capstone. The repository already has resume parsing, evidence scoring, quiz delivery/scoring, mismatch analysis, job matching, and readiness calculations in `backend/main.py`; the frontend is `frontend/index.html`. Replacing the frontend with React is optional and is not required to validate the project idea.

Use MySQL for persistent curated data and user results. Do not scrape job boards. Add listings manually or through permitted public feeds, retain the source URL and checked date, and mark a listing `NEEDS_REVIEW` until a person confirms it.

## MySQL schema

Use `utf8mb4`, InnoDB, UTC timestamps, foreign keys, and migrations. Authentication can be deferred; `student_profiles` may initially contain one local/demo profile.

```sql
CREATE DATABASE IF NOT EXISTS skillproof
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE skillproof;

CREATE TABLE student_profiles (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  display_name VARCHAR(160) NOT NULL,
  email VARCHAR(254) UNIQUE,
  branch VARCHAR(160),
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE skills (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(120) NOT NULL UNIQUE,
  cluster_name VARCHAR(120) NOT NULL,
  aliases JSON NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE
) ENGINE=InnoDB;

CREATE TABLE evidence_items (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  profile_id BIGINT UNSIGNED NOT NULL,
  skill_id BIGINT UNSIGNED NOT NULL,
  source_type ENUM('RESUME','GITHUB','PROJECT','LINKEDIN','MANUAL') NOT NULL,
  source_label VARCHAR(255),
  excerpt TEXT,
  evidence_level ENUM('WEAK','MEDIUM','STRONG') NOT NULL,
  evidence_score TINYINT UNSIGNED NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (profile_id) REFERENCES student_profiles(id) ON DELETE CASCADE,
  FOREIGN KEY (skill_id) REFERENCES skills(id),
  INDEX idx_evidence_profile_skill (profile_id, skill_id)
) ENGINE=InnoDB;

CREATE TABLE quiz_questions (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  skill_id BIGINT UNSIGNED NOT NULL,
  sub_concept VARCHAR(120) NOT NULL,
  prompt TEXT NOT NULL,
  options JSON NOT NULL,
  answer_key TINYINT UNSIGNED NOT NULL,
  explanation TEXT NOT NULL,
  difficulty ENUM('FOUNDATION','INTERMEDIATE','ADVANCED') NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  version INT UNSIGNED NOT NULL DEFAULT 1,
  FOREIGN KEY (skill_id) REFERENCES skills(id),
  INDEX idx_question_skill_concept (skill_id, sub_concept, active)
) ENGINE=InnoDB;

CREATE TABLE quiz_attempts (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  profile_id BIGINT UNSIGNED NOT NULL,
  skill_id BIGINT UNSIGNED NOT NULL,
  question_set_version INT UNSIGNED NOT NULL,
  score TINYINT UNSIGNED NOT NULL,
  started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP NULL,
  FOREIGN KEY (profile_id) REFERENCES student_profiles(id) ON DELETE CASCADE,
  FOREIGN KEY (skill_id) REFERENCES skills(id),
  INDEX idx_attempt_profile_skill (profile_id, skill_id, completed_at)
) ENGINE=InnoDB;

CREATE TABLE quiz_answers (
  attempt_id BIGINT UNSIGNED NOT NULL,
  question_id BIGINT UNSIGNED NOT NULL,
  selected_option TINYINT UNSIGNED NOT NULL,
  is_correct BOOLEAN NOT NULL,
  PRIMARY KEY (attempt_id, question_id),
  FOREIGN KEY (attempt_id) REFERENCES quiz_attempts(id) ON DELETE CASCADE,
  FOREIGN KEY (question_id) REFERENCES quiz_questions(id)
) ENGINE=InnoDB;

CREATE TABLE internship_postings (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  company_name VARCHAR(200) NOT NULL,
  internship_title VARCHAR(200) NOT NULL,
  job_description TEXT NOT NULL,
  location VARCHAR(300),
  work_mode ENUM('REMOTE','HYBRID','ONSITE','UNSPECIFIED') NOT NULL DEFAULT 'UNSPECIFIED',
  stipend VARCHAR(200),
  apply_url VARCHAR(2048) NOT NULL,
  deadline DATE NULL,
  status ENUM('OPEN','CLOSED','NEEDS_REVIEW') NOT NULL DEFAULT 'NEEDS_REVIEW',
  source VARCHAR(500) NOT NULL,
  source_checked_at DATE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_posting_source_url (apply_url(512)),
  INDEX idx_posting_status_deadline (status, deadline)
) ENGINE=InnoDB;

CREATE TABLE posting_skills (
  posting_id BIGINT UNSIGNED NOT NULL,
  skill_id BIGINT UNSIGNED NOT NULL,
  importance ENUM('REQUIRED','PREFERRED') NOT NULL DEFAULT 'REQUIRED',
  minimum_score TINYINT UNSIGNED NOT NULL DEFAULT 60,
  PRIMARY KEY (posting_id, skill_id),
  FOREIGN KEY (posting_id) REFERENCES internship_postings(id) ON DELETE CASCADE,
  FOREIGN KEY (skill_id) REFERENCES skills(id)
) ENGINE=InnoDB;
```

Do not store uploaded resume or job-description file contents in MySQL by default. Process uploads in memory, retain only extracted evidence needed for the student's profile, and let the user remove that evidence.

## API contract

Prefix new endpoints with `/api/v1`. Keep compatibility aliases for the current routes while migrating the frontend.

| Method and path | Purpose | Current repository equivalent |
| --- | --- | --- |
| `GET /health` | Service readiness | `GET /api/health` |
| `GET /skills` | Skill list and supported sub-concepts | `GET /api/skills` |
| `POST /evidence/parse` | Parse pasted resume/project text and return evidence by skill | `POST /api/parse` |
| `POST /evidence/upload` | Parse resume and optional project file in memory | `POST /api/parse/upload` |
| `GET /quizzes/{skill_id}` | Deliver active questions; never expose answer keys | `GET /api/quiz/{skill}` |
| `POST /quiz-attempts` | Score submitted answers and return per-sub-concept feedback | `POST /api/score` |
| `GET /profiles/{profile_id}/skills` | Return claimed, evidence, quiz, corrected scores and mismatch labels | Extend current `/api/analyze` |
| `GET /profiles/{profile_id}/readiness` | Return Ready Now / Stretch / Not Yet postings | Extend current `/api/analyze` |
| `GET /profiles/{profile_id}/leverage` | Rank next skills and return unlock simulation | Extend current `/api/analyze` |
| `GET /profiles/{profile_id}/roles` | Role-cluster fit and next-tier skill gaps | Extend current `/api/analyze` |
| `GET /internships?status=OPEN` | List curated open postings with source/check date | Add; current imported listings are browser-only |
| `POST /internships` | Add a manually verified listing with skills | Add; require HTTPS `apply_url` and source |
| `PATCH /internships/{id}` | Update status, deadline, or verification date | Add; no scraping |
| `GET /internships/{id}/match?profile_id=…` | Explain skill thresholds, evidence, quiz contribution, and gaps | Extend current match report |

Return `422` for invalid input, `404` for missing records, and `409` for a duplicate application URL. Apply pagination and maximum text/file sizes. The quiz response must omit answer keys and explanations until the attempt is scored.

## Quiz question format

Maintain quiz content as JSON fixtures, then seed `quiz_questions`. Every question tests one sub-concept and includes a version so prior results remain interpretable when content changes.

```json
{
  "skill": "Python",
  "sub_concept": "Error handling",
  "difficulty": "INTERMEDIATE",
  "prompt": "Which clause handles an exception raised by the try block?",
  "options": ["else", "except", "finally", "raise"],
  "answer_key": 1,
  "explanation": "An except clause handles a matching exception.",
  "version": 1
}
```

Use stable skill and sub-concept identifiers in APIs. Start with 8–12 questions per skill, balanced across concepts and difficulty. Select a short mix per attempt; calculate an overall score plus concept scores, and label low-sample concept results as provisional. Do not claim adaptivity until question selection changes based on prior answers and that behavior is evaluated.

## Ten-week delivery plan

| Week | Deliverable |
| --- | --- |
| 1 | Confirm requirements, data flow, consent/privacy decisions, evaluation metrics, and current-code baseline. Freeze initial skill taxonomy. |
| 2 | Add MySQL configuration through environment variables, migrations, repository layer, seed skills, and database health checks. |
| 3 | Implement posting CRUD and curation workflow; manually add a small sourced dataset with checked dates and status review. |
| 4 | Persist profiles and evidence records; connect parser output to evidence items while keeping file contents transient. |
| 5 | Normalize quiz bank and seed questions; deliver questions without answer keys; store attempts and answers. |
| 6 | Compute sub-concept feedback, corrected skill levels, mismatch labels, and remove unsupported claims of adaptive behavior. |
| 7 | Connect posting-skill thresholds to readiness buckets and explainable match reports; validate status/deadline filtering. |
| 8 | Add leverage ranking, unlock simulation, and role-cluster alignment using persisted corrected scores. |
| 9 | Run evaluation: label 100–150 evidence mentions, compare claimed vs verified matches, and test targeted diagnostics with students. Fix findings and document limits. |
| 10 | Polish UI/accessibility, deploy a demo, seed repeatable sample data, prepare architecture/evaluation results, and rehearse the capstone presentation. |

## Current gaps to track

- The current UI is a static HTML/JavaScript application rather than React.
- CSV imports remain in browser storage. Manual internship entries now use `POST /api/internships` when MySQL is configured; `GET /api/internships` supplies saved postings to the matcher. Apply `backend/sql/001_internships.sql` and configure `.env` before using the database-backed form.
- The current API includes core parse, quiz, score, analyze, and job-match operations. Persistent profile and quiz-attempt storage, posting updates, and admin curation still remain to be built.
- The app has rule-based evidence scoring and exact/heuristic matching. Describe these accurately; only claim a trained evidence classifier or adaptive quiz after implementing and evaluating them.
- Do not scrape Internshala, LinkedIn, Wellfound, or AICTE without authorized access. A listing is not verified merely because a URL works; record the source and review date, and recheck availability before applying.

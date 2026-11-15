# SkillProof Working Model Checklist

Status describes the code in this repository. A checked item is implemented in the prototype; it does not imply production readiness or a measured research result.

## Implemented

- [x] FastAPI service and browser dashboard with profile, resume, quiz, analysis, job match, internship, gap, leverage, and role views.
- [x] PDF, DOCX, Markdown, and TXT resume/project upload with a 5 MB per-file limit and in-memory source-file processing.
- [x] Public GitHub profile import through the GitHub REST API, limited to recent public repository READMEs; no credentials or private repository access.
- [x] User-authorized LinkedIn export import for Skills.csv (or LinkedIn ZIP archives containing Skills.csv and selected profile/project CSVs); exports are handled in memory and remain self-reported claims. LinkedIn OAuth is still unavailable.
- [x] Rule-based evidence-depth scores with weak / medium / strong labels and short evidence context.
- [x] Quiz banks cover all 25 skills shown in Skill Leverage. The original nine skills have eight questions each; the 16 expanded skills currently have four-question starter banks. Questions are tagged by sub-concept and later rounds prioritize lower-scoring concepts.
- [x] Custom skills can have a student-authored four-question practice quiz saved in browser storage. These scores are labeled as self-authored practice and are not independent verification or used for job matching.
- [x] Per-skill quiz score, sub-concept feedback, and targeted study resource.
- [x] Overclaim, hidden-strength, and unverified-claim detection using evidence and quiz scores.
- [x] Corrected-profile readiness buckets, posting-level match explanations, leverage ranking, unlock simulation, and role-cluster alignment for the supported skills and sample data.
- [x] Dedicated Skill Leverage view with a ranked “Prove these next” list, 60-point scenario threshold, editable scores, Ready Now / Stretch / Not Yet posting buckets, study links, and a ranked-vs-random illustrative unlock chart. Sample scores and roles are labeled as examples; saved quiz mode is limited to skills with quiz banks.
- [x] Data-analyst and BI sample roles now use quiz-verifiable Excel, SQL, Python, Tableau, and Power BI skills.
- [x] Interactive career roadmap with editable skill scenarios, presets, 23 role profiles, category filters, and 69 illustrative job profiles; scenario changes save in browser storage.
- [x] Resume-to-job match with skill readiness, hidden strengths, and keyword overlap.
- [x] MySQL schema and APIs for manual internship listing creation/listing, profile basics, and extracted evidence. Open listings require a source check date.
- [x] Optional MySQL persistence for built-in quiz attempts, including per-concept scores and question IDs; localStorage remains the fallback when MySQL is not configured.
- [x] React/Vite account workspace with registration/sign-in, profile editing, built-in quiz flow, durable quiz history, and semantic opportunity results.
- [x] React project feature hub at `/app`, including a browser-only demo mode and same-origin access to the existing dashboard, resume/GitHub, verification, mismatch, gap, internship, leverage, roadmap, and survey pages; account data snapshots into the prototype's browser state when opened.
- [x] Per-account registration and profile isolation: salted PBKDF2 password hashes, signed 12-hour bearer tokens, and ownership checks on profile, evidence, and quiz-history routes.
- [x] Google sign-in flow with server-side Google ID-token verification and account lookup/creation from Google's verified email; requires a configured Google OAuth Web client ID and authorized JavaScript origins.
- [x] SentenceTransformers semantic opportunity ranker for curated and harvested job records, combining description similarity with verified required-skill coverage. The selected engine is returned with each result.
- [x] Offline TF-IDF fallback when the SentenceTransformers package/model is unavailable.
- [x] Browser-only CSV import plus a dated, manually curated listing CSV. No unauthorized board scraping.
- [x] Optional refresh from permitted public ATS/job APIs; results are marked for source-site verification. No scraping of Internshala, AICTE, LinkedIn, or Wellfound.
- [x] Evaluation harness for evidence-level accuracy, per-class precision/recall/F1, macro-F1, and confusion matrix.
- [x] Optional TF-IDF/logistic-regression evidence classifier training workflow with held-out metrics; requires at least 100 manually reviewed examples and does not fabricate model scores.
- [x] Anonymized participant-study template and analysis script for claim/quiz mismatches, targeted-vs-generic feedback changes, raw-vs-corrected matches, and ranked-vs-random unlock counts; actual outcomes still require consented participants and collected data.
- [x] Setup guidance and a feature-gap checklist.

## Partial or not yet validated

- [~] The new React opportunity view calls `/api/semantic-match`; the original static dashboard's `/api/analyze` and role/leverage scenario calculations remain heuristic and are not semantic.
- [~] Internship data includes the supplied dated sample and manually entered/imported listings. There is no broad, continuously verified pool from Internshala, AICTE, LinkedIn, and Wellfound.
- [~] Evidence scoring uses transparent rules until a model is trained from at least 100 manually reviewed examples. Training code and held-out evaluation are available; no representative labeled dataset or validated model is included.
- [~] React built-in quiz scores and concept-level attempts persist to the signed-in profile in MySQL; the older prototype retains browser-local state and there is no calibrated item-response model.
- [~] The React account workspace and feature hub are included at `/app`; the original analysis modules are still static HTML/JavaScript embedded in the hub, so the React client is not feature-parity with every original view. Demo quiz results are temporary; durable attempts require MySQL-backed sign-in.
- [~] Multi-user profile/evidence/quiz isolation is implemented when MySQL and `APP_SECRET_KEY` are configured and both SQL migrations are applied. Deployment still needs HTTPS, rate limiting, token revocation/rotation, secure session storage, monitoring, backups, and secret management.
- [ ] Complete internship update/delete/admin review workflows and production deployment hardening.
- [ ] Evaluation results from 100–150 manually labeled mentions, student mismatch data, diagnostic intervention results, matching comparisons, and ranked-vs-random leverage simulations. The app provides evaluation/training workflows, but real human-labeled examples and participants are still required; no results are fabricated.
- [ ] LinkedIn OAuth. LinkedIn export ZIP/Skills.csv import is implemented; direct account connection requires a LinkedIn-approved OAuth application and credentials.

## Requirement map

| Project requirement | Status | What the prototype currently does |
|---|---|---|
| Resume/GitHub/LinkedIn skill extraction and project evidence | Implemented with limits | Reads supported skills from uploaded resumes/projects, recent public GitHub READMEs, and a user-authorized LinkedIn data export. LinkedIn-listed skills remain claims, not proof. |
| Evidence-depth scoring | Implemented as baseline | Transparent rules assign weak/medium/strong labels; classifier validation remains pending. |
| Adaptive sub-concept quiz | Implemented for current leverage skills | Quiz banks cover all 25 leverage skills, with four starter questions for 16 newly covered skills and eight for nine existing skills; adaptation is not calibrated testing. |
| Custom skill quiz support | Practice-only | Students can author and save a four-question quiz per added skill; the author controls the answer key, so scores are not independent verification and do not affect matching. |
| Claimed-vs-verified mismatch and weak-topic feedback | Implemented | Flags overclaims/hidden strengths and links weakest quiz concepts to study resources. |
| Mismatch report dashboard | Implemented | Shows evidence/quiz comparison, overclaimed/hidden/verified filters, prioritized fixes, and expandable concept-level diagnostics from saved profile data. |
| Internship matching and readiness buckets | Partial | Corrected scores produce Ready Now/Stretch/Not Yet for sample and imported postings; ranking is heuristic and listings must be verified at their source. |
| Leverage ranking, unlock simulation, role clusters | Implemented for included data | Computes results from the supported skill bank and illustrative/sample posting and role data. |
| Evaluation claims | Workflow implemented; evidence pending | Scripts and templates support labeling, held-out classification, and metrics; real labels, participants, comparison results, and measured outcomes are still required. |
| Proposed React + embedding/classifier stack | Partial | React client and SentenceTransformers semantic matching are now present, with TF-IDF fallback; the original app still uses its static JS dashboard, and evidence classification remains rule-based until a model is trained on reviewed examples. |

## Product positioning

Keep comparisons factual. Jobscan describes resume-to-job matching, missing skills/keywords, and ATS optimization ([Jobscan](https://www.jobscan.co/)). Teal documents a Job Matcher that compares a resume with jobs from its tracker, job board, or pasted descriptions and highlights included/missing keywords ([Teal Job Matcher](https://help.tealhq.com/en/articles/12060992-using-the-job-matcher)). Rezi describes ATS checks, resume scoring, keyword targeting, and missing skills/terms ([Rezi Resume Checker](https://www.rezi.ai/tools/resume-checker), [Rezi Keyword Targeting](https://www.rezi.ai/rezi-docs/ai-keyword-targeting-explained)).

SkillProof's intended distinction is the integrated student workflow: combine project evidence, concept-level quiz results, corrected skill levels, actionable gaps, and opportunity leverage. Treat this as the product design hypothesis; do not claim that no competitor has any similar capability without a dedicated feature review.


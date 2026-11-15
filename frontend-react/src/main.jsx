import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import './features.css';

const API = '/api';
const LEGACY_STORE = 'skillproof-state-v1';
const FEATURE_PAGES = [
  ['dashboard','Dashboard','Readiness overview, verified scores, and next steps.','✅'],
  ['profile','Student profile','Academic, project, experience, and career preferences.','✅'],
  ['resume','Resume & GitHub','Upload a resume/project file or analyze public GitHub README evidence.','✅'],
  ['jobmatch','Resume / Job Match','Compare resume evidence and quiz scores with one job description.','✅'],
  ['verify','Skill Verification','Take built-in quizzes tagged by skill and sub-concept.','✅'],
  ['mismatch','Mismatch Report','Review overclaims, hidden strengths, and weak concepts.','✅'],
  ['gap','Skill Gap Analysis','Choose a target role and view the skill gaps and study plan.','✅'],
  ['matcher','Internship Matcher','Review sample/imported/authorized-feed listings and match explanations.','🟡'],
  ['leverage','Skill Leverage','Rank next skills by illustrative opportunity unlocks.','🟡'],
  ['roadmap','Career Roadmap','Explore role clusters and simulated skill paths.','🟡'],
  ['surveydata','Survey Data File','Preview an exported survey CSV locally in this browser.','✅'],
];
async function request(path, options = {}, token = '') {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}

function App() {
  const [token, setToken] = useState(localStorage.getItem('skillproof-token') || '');
  const [profile, setProfile] = useState(null);
  const [demoMode, setDemoMode] = useState(false);
  const [authMode, setAuthMode] = useState('login');
  const [tab, setTab] = useState('overview');
  const [skills, setSkills] = useState([]);
  const [verified, setVerified] = useState({});
  const [evidence, setEvidence] = useState({});
  const [subScores, setSubScores] = useState({});
  const [currentQuiz, setCurrentQuiz] = useState(null);
  const [answers, setAnswers] = useState({});
  const [quizResult, setQuizResult] = useState(null);
  const [matches, setMatches] = useState([]);
  const [engine, setEngine] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [legacyPage, setLegacyPage] = useState('dashboard');
  const [legacyVersion, setLegacyVersion] = useState(0);
  const [googleClientId, setGoogleClientId] = useState('');
  const [form, setForm] = useState({ email: '', password: '', display_name: '' });

  useEffect(() => { request('/skills').then(data => setSkills(data.skills || [])); }, []);
  useEffect(() => { request('/auth/config').then(data => setGoogleClientId(data.google_client_id || '')).catch(() => setGoogleClientId('')); }, []);
  useEffect(() => {
    if (token || profile || demoMode || !googleClientId) return undefined;
    const script = document.querySelector('script[data-google-identity]');
    const mountGoogleButton = () => {
      const google = window.google;
      const container = document.getElementById('google-sign-in');
      if (!container || !google?.accounts?.id) return;
      container.replaceChildren();
      google.accounts.id.initialize({ client_id: googleClientId, callback: async response => {
        if (!response?.credential) { setError('Google sign-in did not return an identity token.'); return; }
        setBusy(true); setError('');
        try {
          const data = await request('/auth/google', { method: 'POST', body: JSON.stringify({ credential: response.credential }) });
          localStorage.setItem('skillproof-token', data.access_token); setToken(data.access_token); setProfile(data.profile);
        } catch (e) { setError(e.message); } finally { setBusy(false); }
      }});
      google.accounts.id.renderButton(container, { theme: 'outline', size: 'large', text: authMode === 'login' ? 'signin_with' : 'signup_with', shape: 'rectangular', width: 340 });
    };
    script?.addEventListener('load', mountGoogleButton);
    mountGoogleButton();
    return () => script?.removeEventListener('load', mountGoogleButton);
  }, [googleClientId, token, profile, demoMode, authMode]);
  useEffect(() => {
    if (!token) return;
    request('/auth/me', {}, token).then(async data => {
      setProfile(data.profile);
      const [profileData, history] = await Promise.all([
        request(`/profiles/${data.profile.id}`, {}, token),
        request(`/profiles/${data.profile.id}/quiz-attempts`, {}, token),
      ]);
      const evidenceScores = {};
      for (const item of profileData.evidence || []) evidenceScores[item.skill] = Math.max(evidenceScores[item.skill] || 0, item.evidence_score || 0);
      setEvidence(evidenceScores);
      const latest = {};
      const concepts = {};
      for (const attempt of [...(history.attempts || [])].reverse()) {
        latest[attempt.skill] = attempt.score;
        concepts[attempt.skill] = typeof attempt.sub_scores === 'string' ? JSON.parse(attempt.sub_scores) : attempt.sub_scores;
      }
      setVerified(latest);
      setSubScores(concepts);
    }).catch(() => logout());
  }, [token]);

  function logout() { localStorage.removeItem('skillproof-token'); setToken(''); setProfile(null); }
  function openLegacy(page) {
    const legacyProfile = { fullName: profile?.display_name || 'Student', email: profile?.email || '' };
    const state = { name: legacyProfile.fullName, profile: legacyProfile,
      evidence, quiz: verified, subs: subScores, quizSeen: {}, res: {}, customSkills: [], customQuizBanks: {}, customQuizResults: {},
      importedInternships: [], roadmapSkills: null, gapProfile: null, leverageScenario: null, leverageMode: 'quiz' };
    localStorage.setItem(LEGACY_STORE, JSON.stringify(state));
    setLegacyPage(page); setLegacyVersion(value => value + 1); setTab('legacy');
  }
  async function authenticate(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const path = authMode === 'register' ? '/auth/register' : '/auth/login';
      const data = await request(path, { method: 'POST', body: JSON.stringify(form) });
      localStorage.setItem('skillproof-token', data.access_token); setToken(data.access_token); setProfile(data.profile);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function beginQuiz(skill) {
    setBusy(true); setError(''); setQuizResult(null);
    try {
      const history = demoMode ? { attempts: [] } : await request(`/profiles/${profile.id}/quiz-attempts?skill=${encodeURIComponent(skill)}&limit=100`, {}, token);
      const attempts = history.attempts || [];
      const latest = attempts[0];
      let priorScores = latest?.sub_scores || {};
      if (typeof priorScores === 'string') priorScores = JSON.parse(priorScores);
      const seen = [...new Set(attempts.flatMap(attempt => {
        const ids = typeof attempt.question_ids === 'string' ? JSON.parse(attempt.question_ids) : attempt.question_ids;
        return ids || [];
      }))];
      const params = new URLSearchParams();
      if (Object.keys(priorScores).length) params.set('sub_scores', JSON.stringify(priorScores));
      if (seen.length) params.set('seen_ids', JSON.stringify(seen));
      const query = params.toString() ? `?${params}` : '';
      const data = await request(`/quiz/${encodeURIComponent(skill)}${query}`);
      setCurrentQuiz(data); setAnswers({});
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function submitQuiz(event) {
    event.preventDefault(); if (!currentQuiz) return;
    setBusy(true); setError('');
    try {
      const result = await request('/score', { method: 'POST', body: JSON.stringify({
        skill: currentQuiz.skill,
        question_ids: currentQuiz.questions.map(q => q.id),
        answers: Object.fromEntries(Object.entries(answers).map(([key,value]) => [key, Number(value)])),
      }) });
      if (!demoMode) await request(`/profiles/${profile.id}/quiz-attempts`, { method: 'POST', body: JSON.stringify({
        skill: result.skill, score: result.score,
        question_ids: currentQuiz.questions.map(q => q.id), sub_scores: result.subs,
      }) }, token);
      setVerified({ ...verified, [result.skill]: result.score }); setQuizResult(result); setCurrentQuiz(null);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function saveProfile(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const data = await request(`/profiles/${profile.id}`, { method: 'PUT', body: JSON.stringify(profile) }, token);
      setProfile(data); setTab('overview');
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function rankJobs() {
    setBusy(true); setError('');
    try {
      const data = await request('/semantic-match', { method: 'POST', body: JSON.stringify({ skills: verified }) }, token);
      setMatches(data.matches || []); setEngine(data.matches?.[0]?.matching_engine || ''); setTab('matches');
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function refreshListings() {
    setBusy(true); setError('');
    try {
      await request('/jobs/harvest-free', { method: 'POST', body: JSON.stringify({ enrich_with_llm: false }) }, token);
      if (!Object.keys(verified).length) { setMatches([]); setEngine(''); setTab('matches'); return; }
      const data = await request('/semantic-match', { method: 'POST', body: JSON.stringify({ skills: verified }) }, token);
      setMatches(data.matches || []); setEngine(data.matches?.[0]?.matching_engine || '');
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  if ((!token || !profile) && !demoMode) return <main className="auth-shell"><section className="auth-card">
    <div className="brand">🎓 SkillProof</div><p className="eyebrow">Evidence-led career readiness</p>
    <h1>{authMode === 'login' ? 'Welcome back' : 'Create your student account'}</h1>
    <form onSubmit={authenticate} className="stack">
      {authMode === 'register' && <label>Name<input required maxLength="160" value={form.display_name} onChange={e => setForm({ ...form, display_name: e.target.value })}/></label>}
      <label>Email<input required type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })}/></label>
      <label>Password<input required type="password" minLength={authMode === 'register' ? 12 : 1} value={form.password} onChange={e => setForm({ ...form, password: e.target.value })}/>{authMode === 'register' && <small>Use at least 12 characters.</small>}</label>
      {error && <p className="error">{error}</p>}<button disabled={busy}>{busy ? 'Please wait…' : authMode === 'login' ? 'Sign in' : 'Create account'}</button>
    </form>
    <button className="text-button" onClick={() => { setAuthMode(authMode === 'login' ? 'register' : 'login'); setError(''); }}>{authMode === 'login' ? 'New to SkillProof? Create an account' : 'Already registered? Sign in'}</button>
    <div className="auth-divider"><span>or continue with</span></div>
    {googleClientId ? <div id="google-sign-in" className="google-sign-in"/> : <button type="button" className="google-fallback" onClick={() => setError('Google sign-in is not configured yet. Add GOOGLE_CLIENT_ID to .env and register this site in Google Cloud Console.')}>Continue with Google</button>}
    <button className="secondary" onClick={() => { setDemoMode(true); setProfile({ id: null, display_name: 'Demo Student', email: 'demo@skillproof.local', branch: 'Sample profile' }); setTab('featurehub'); }}>Explore demo workspace</button>
    <small className="muted">Demo quizzes are scored for this session only. Saving profiles and quiz history requires configured MySQL and an account.</small>
    <a className="legacy-link" href="/">Open the original SkillProof prototype</a>
  </section></main>;

  return <div className="layout"><aside><div className="brand">🎓 SkillProof</div><p className="muted">Student workspace</p><nav>{[['overview','Overview'],['profile','My profile'],['skills','Verified skills'],['matches','Opportunity matches'],['featurehub','All project features']].map(([id,label]) => <button key={id} className={tab===id?'selected':''} onClick={() => setTab(id)}>{label}</button>)}</nav><button className="signout" onClick={logout}>Sign out</button></aside>
    <main className="content"><header><div><p className="eyebrow">Career readiness workspace</p><h1>{tab === 'overview' ? `Welcome, ${profile.display_name}` : tab === 'profile' ? 'Your profile' : tab === 'skills' ? 'Verified skills' : tab === 'matches' ? 'Opportunity matches' : tab === 'legacy' ? 'SkillProof feature workspace' : 'All project features'}</h1></div><span className="pill">Signed in as {profile.email}</span></header>
      {error && <p className="error">{error}</p>}
      {tab==='featurehub' && <>{demoMode&&<p className="notice">Demo workspace: scores and profile data are temporary. Create an account with MySQL configured to save quiz history.</p>}<p className="muted">Open every project module from one place. The established analysis pages run in their original same-origin workspace and use this browser’s saved SkillProof state.</p><div className="feature-grid">{FEATURE_PAGES.map(([id,title,description,status])=><article className="panel feature-card" key={id}><div className="row"><h3>{title}</h3><span>{status}</span></div><p>{description}</p><button onClick={()=>openLegacy(id)}>Open feature</button></article>)}</div><article className="panel"><h3>Research and prototype limits</h3><p>Sample and imported listings need checking at their source. No evaluation results are claimed until real labeled examples and consented participant data are collected. See the project checklist for current implementation status.</p><a href="/project-checklist" target="_blank" rel="noreferrer">Open requirement checklist ↗</a></article></>}
      {tab==='legacy' && <section className="panel legacy-panel"><div className="row legacy-tools"><div><h2>{FEATURE_PAGES.find(item=>item[0]===legacyPage)?.[1]||'SkillProof module'}</h2><p className="muted">This module uses your current browser session and the profile/quiz snapshot synced when opened.</p></div><button className="secondary" onClick={()=>setTab('featurehub')}>All features</button></div><iframe key={legacyVersion} className="legacy-frame" title="SkillProof feature module" src={`${import.meta.env.BASE_URL}frontend/`} onLoad={event=>{try{event.currentTarget.contentWindow.go(legacyPage)}catch{}}}/></section>}
      {tab==='overview' && <>{demoMode&&<p className="notice">Demo workspace: scores are temporary, and opportunity ranking is available after signing in with a configured account.</p>}<section className="hero"><div><p className="eyebrow">SkillProof snapshot</p><h2>Build a trustworthy profile, one skill at a time.</h2><p>{demoMode?'Demo quiz scores last for this session.':'Quiz scores are saved to your account database.'}</p><button onClick={() => setTab('skills')}>Update verified skills</button></div><div className="score">{Object.keys(verified).length}<small>skills scored</small></div></section><div className="grid"><article className="panel"><h3>Profile</h3><p>{profile.email}</p><button className="secondary" onClick={() => setTab('profile')}>Edit profile</button></article><article className="panel"><h3>Next opportunity</h3><p>Match your verified profile against the included internship roles.</p><button disabled={busy || demoMode || !Object.keys(verified).length} onClick={rankJobs}>{busy?'Ranking…':demoMode?'Sign in to rank':'Rank opportunities'}</button></article></div></>}
      {tab==='profile' && <form className="panel stack" onSubmit={saveProfile}><h2>Profile details</h2>{demoMode&&<p className="notice">Demo profile changes are not saved.</p>}<label>Name<input required value={profile.display_name||''} disabled={demoMode} onChange={e=>setProfile({...profile,display_name:e.target.value})}/></label><label>Email<input disabled value={profile.email||''}/></label><button disabled={busy||demoMode}>{demoMode?'Account required to save':'Save profile'}</button></form>}
      {tab==='skills' && <section className="panel"><h2>Quiz-verified skill scores</h2><p className="muted">Complete the quiz to save a score to your private account and use it in job matching.</p>
        {quizResult && <div className="quiz-result"><strong>{quizResult.skill}: {quizResult.score}%</strong><p>Lowest concept: {quizResult.weakest || 'None'}</p>{quizResult.resource&&<a href={quizResult.resource.url} target="_blank" rel="noreferrer">Study {quizResult.resource.title} ↗</a>}</div>}
        {currentQuiz ? <form onSubmit={submitQuiz}><h3>{currentQuiz.skill} quiz</h3>{currentQuiz.questions.map((q,index)=><fieldset className="question" key={q.id}><legend>{index+1}. {q.q} <small>· {q.sub}</small></legend>{q.options.map((option,choice)=><label key={choice}><input required type="radio" name={q.id} value={choice} checked={String(answers[q.id])===String(choice)} onChange={e=>setAnswers({...answers,[q.id]:e.target.value})}/> {option}</label>)}</fieldset>)}<button disabled={busy||Object.keys(answers).length!==currentQuiz.questions.length}>{busy?'Scoring and saving…':'Submit quiz'}</button> <button className="secondary" type="button" onClick={()=>setCurrentQuiz(null)}>Cancel</button></form> : <div>{skills.map(skill=><div className="skill-row" key={skill}><div><strong>{skill}</strong><div className="scorebar"><i style={{width:`${verified[skill]||0}%`}}/></div></div><span>{verified[skill]!==undefined?`${verified[skill]}%`:'Not verified'}</span><button disabled={busy} onClick={()=>beginQuiz(skill)}>Take quiz</button></div>)}</div>}
        <button disabled={busy||demoMode||!Object.keys(verified).length} onClick={rankJobs}>{busy?'Matching…':demoMode?'Sign in to match':'Find matching opportunities'}</button></section>}
      {tab==='matches' && <section className="panel"><div className="row"><div><h2>Ranked opportunity matches</h2><p className="muted">Matching engine: {engine||'run a match to calculate'}</p></div><div className="row"><button className="secondary" disabled={busy||demoMode} onClick={refreshListings}>{busy?'Loading…':demoMode?'Account required':'Refresh permitted job feeds'}</button><button disabled={busy||demoMode||!Object.keys(verified).length} onClick={rankJobs}>{busy?'Ranking…':demoMode?'Account required':'Refresh matches'}</button></div></div>{matches.length===0?<p>Add quiz scores and run a match to see results.</p>:<div className="match-list">{matches.map((job,i)=><article className="match" key={job.id||i}><div className="row"><div><h3>{job.title||'Internship'}</h3><p>{job.company||job.employer||'Company'}</p></div><strong>{job.readiness_score}%</strong></div><p><span className={`tag ${job.readiness_bucket}`}>{job.readiness_bucket.replace('_',' ')}</span> Similarity {job.semantic_similarity}% · skill coverage {job.skill_coverage}%</p><p>Matched: {job.matched_skills.join(', ')||'None'}{job.missing_skills.length?` · To prove: ${job.missing_skills.join(', ')}`:''}</p>{job.apply_url&&<a href={job.apply_url} target="_blank" rel="noreferrer">View posting ↗</a>}</article>)}</div>}</section>}
    </main>
  </div>;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App/></React.StrictMode>);

'use strict';

let MISMATCH_FILTER = 'all';
let MISMATCH_EXPANDED = '';

function mismatchSetFilter(filter) { MISMATCH_FILTER = filter; render(); }
function mismatchToggle(skill) { MISMATCH_EXPANDED = MISMATCH_EXPANDED === skill ? '' : skill; render(); }
function mismatchStatus(skill, bySkill) {
  const item = bySkill[skill], evidence = Number(S.evidence[skill]) || 0, quiz = S.quiz[skill];
  if (item?.type === 'overclaimed') return 'overclaimed';
  if (item?.type === 'hidden') return 'hidden';
  if (item?.type === 'unverified') return 'needs_quiz';
  if (quiz !== undefined && quiz !== null) return Number(quiz) >= 60 ? 'verified' : 'needs_work';
  return evidence ? 'needs_quiz' : 'needs_work';
}

function renderMismatchReport() {
  const analysis = A0(), bySkill = Object.fromEntries((analysis.mismatches || []).map(item => [item.skill, item]));
  const names = [...new Set([...Object.keys(S.evidence || {}), ...Object.keys(S.quiz || {})])];
  const rows = names.map(skill => ({
    skill, evidence: Number(S.evidence[skill]) || 0, hasEvidence: Object.prototype.hasOwnProperty.call(S.evidence || {}, skill), quiz: S.quiz[skill] ?? null,
    status: mismatchStatus(skill, bySkill), subs: S.subs[skill] || {},
    context: (S.parsed || []).find(item => item.skill === skill)?.context || [], resource: S.res[skill] || null,
  }));
  const counts = { all: rows.length, overclaimed: 0, hidden: 0, verified: 0, needs_quiz: 0, needs_work: 0 };
  rows.forEach(row => counts[row.status]++);
  const visible = MISMATCH_FILTER === 'all' ? rows : rows.filter(row => row.status === MISMATCH_FILTER);
  const compared = rows.filter(row => row.quiz !== null && row.hasEvidence);
  const closeness = compared.length ? Math.round(compared.reduce((sum, row) => sum + 100 - Math.abs(row.evidence - row.quiz), 0) / compared.length) : null;
  const priority = { overclaimed: 0, hidden: 1, needs_quiz: 2, needs_work: 3, verified: 4 };
  const ranked = [...rows].sort((a, b) => priority[a.status] - priority[b.status] ||
    (a.status === 'overclaimed' ? (b.evidence - b.quiz) - (a.evidence - a.quiz) :
      a.status === 'hidden' ? (b.quiz - b.evidence) - (a.quiz - a.evidence) :
        a.status === 'needs_quiz' ? b.evidence - a.evidence : (a.quiz || 0) - (b.quiz || 0)));
  const actions = ranked.filter(row => row.status !== 'verified').slice(0, 3).map(row => {
    const weak = Object.entries(row.subs).sort((a, b) => a[1] - b[1])[0]?.[0] || row.resource?.weak;
    if (row.status === 'overclaimed') return { icon: '!', title: `Recheck ${row.skill}${weak ? ` · ${weak}` : ''}`,
      text: `Resume evidence is ${row.evidence}; quiz score is ${row.quiz}. Review the claim and practice the weaker concept.`,
      button: `Retake ${row.skill} quiz`, run: `openSkillQuiz('${esc(row.skill)}')`, warn: true };
    if (row.status === 'hidden') return { icon: '+', title: `Add ${row.skill} evidence if accurate`,
      text: `Your quiz score is ${row.quiz}, but no matching resume project evidence was found. Add a real project example.`,
      button: 'Review profile', run: "go('profile')" };
    if (row.status === 'needs_quiz') return { icon: '?', title: `Verify ${row.skill}`,
      text: `Resume/project evidence was found (${row.evidence}/100), but there is no quiz result yet.`,
      button: `Take ${row.skill} quiz`, run: `openSkillQuiz('${esc(row.skill)}')` };
    return { icon: '!', title: `Practice ${row.skill}${weak ? ` · ${weak}` : ''}`,
      text: `Latest quiz score: ${row.quiz}/100. Review the concepts and retake the quiz.`,
      button: `Retake ${row.skill} quiz`, run: `openSkillQuiz('${esc(row.skill)}')`, warn: true };
  });
  const filters = [['all', 'All skills'], ['overclaimed', 'Overclaimed'], ['hidden', 'Hidden strengths'],
    ['verified', 'Verified'], ['needs_quiz', 'Needs quiz'], ['needs_work', 'Needs work']];
  const statusText = { overclaimed: 'Overclaimed', hidden: 'Hidden strength', verified: 'Verified', needs_quiz: 'Needs quiz', needs_work: 'Needs work' };
  const tableRows = visible.map(row => {
    const open = MISMATCH_EXPANDED === row.skill;
    const topics = Object.entries(row.subs).sort((a, b) => a[1] - b[1]).map(([topic, score]) =>
      `<div class="mr-topic"><span>${esc(topic)}</span><i><em style="width:${score}%"></em></i><b>${score}%</b></div>`).join('');
    const excerpts = row.context.map(text => `<blockquote>${esc(text)}</blockquote>`).join('');
    return `<div class="mr-row-wrap"><button class="mr-row" type="button" aria-expanded="${open}" onclick="mismatchToggle('${esc(row.skill)}')">
      <b>${esc(row.skill)}</b><span class="mr-meter"><i><em style="width:${row.evidence}%"></em></i>${row.evidence || '—'}</span>
      <span class="mr-meter quiz"><i><em style="width:${row.quiz === null ? 0 : row.quiz}%"></em></i>${row.quiz === null ? '—' : row.quiz}</span>
      <span class="mr-badge ${row.status}">${statusText[row.status]}</span><span>${open ? '⌄' : '›'}</span></button>
      ${open ? `<div class="mr-detail"><p>${row.quiz === null ? 'Take a quiz to compare your profile claim with your knowledge.' : `Evidence ${row.evidence}/100 · quiz ${row.quiz}/100 · difference ${Math.abs(row.evidence - row.quiz)} points.`}</p>
        ${topics ? `<h4>Quiz sub-topics</h4>${topics}` : row.quiz !== null ? '<p>No sub-topic scores are saved yet. Retake a quiz to see concept-level results.</p>' : ''}
        ${row.resource?.url ? `<p>Focus on <b>${esc(row.resource.weak || 'the weakest topic')}</b>: <a href="${esc(row.resource.url)}" target="_blank" rel="noopener noreferrer">${esc(row.resource.title || 'Study resource')} ↗</a></p>` : ''}
        ${excerpts ? `<h4>Evidence excerpts</h4>${excerpts}` : row.evidence ? '<p>Evidence excerpts are unavailable for this saved score.</p>' : ''}</div>` : ''}</div>`;
  }).join('');
  const actionHtml = actions.length ? actions.map(action => `<article class="mr-action"><span class="mr-action-icon ${action.warn ? 'warn' : ''}">${action.icon}</span><div><b>${esc(action.title)}</b><p>${esc(action.text)}</p><button class="btn o" type="button" onclick="${action.run}">${esc(action.button)}</button></div></article>`).join('') :
    '<div class="mr-empty">No mismatch actions yet. Upload project evidence and complete quizzes to get personalized recommendations.</div>';
  const meta = [S.resumeFile ? `Resume: ${esc(S.resumeFile)}` : 'No resume uploaded',
    S.githubFile ? 'GitHub linked' : 'GitHub not linked', S.linkedinFile ? 'LinkedIn export imported' : 'LinkedIn not imported', `${Object.keys(S.quiz || {}).length} skills quiz-scored`];
  return `<div class="mr-page"><header class="mr-head"><div><span class="mr-eyebrow">SKILLPROOF · TRUST REPORT</span><h2>Mismatch Report</h2><p>Compare skills found in your resume, projects, or profile with what quizzes check.</p></div><div class="mr-meta">${meta.map(item => `<span>${item}</span>`).join('')}</div></header>
    <div class="mr-layout"><aside class="mr-side"><section class="mr-score"><div class="mr-ring" style="--score:${closeness ?? 0}%"><div>${closeness === null ? '—' : `${closeness}%`}</div></div><b>${closeness === null ? 'No comparison yet' : closeness >= 80 ? 'Close alignment' : closeness >= 60 ? 'Some gaps' : 'Needs review'}</b>
      <p>${closeness === null ? 'Take a quiz to compare claimed and quiz scores.' : 'Average closeness between evidence and quiz scores for skills with both.'}</p></section>
      <nav class="mr-filters" aria-label="Filter skills">${filters.map(([key, label]) => `<button class="${MISMATCH_FILTER === key ? 'active' : ''}" aria-pressed="${MISMATCH_FILTER === key}" onclick="mismatchSetFilter('${key}')"><i class="${key}"></i>${label}<b>${counts[key]}</b></button>`).join('')}</nav></aside>
      <main class="mr-content"><section class="mr-panel"><div class="mr-title"><div><h3>Fix first</h3><p>Prioritized from your saved evidence and quiz results.</p></div></div><div class="mr-actions">${actionHtml}</div></section>
      <section class="mr-panel"><div class="mr-title"><div><h3>Skills comparison</h3><p>Evidence is a project signal; quizzes are learning checks, not certifications. Select a row for details.</p></div></div>
        <div class="mr-tabs">${filters.map(([key, label]) => `<button class="${MISMATCH_FILTER === key ? 'active' : ''}" onclick="mismatchSetFilter('${key}')">${label} (${counts[key]})</button>`).join('')}</div>
        <div class="mr-columns"><span>Skill</span><span>Evidence score</span><span>Quiz result</span><span>Status</span><span></span></div>
        <div>${tableRows || '<p class="mr-empty">No skills to compare yet. Upload a resume/LinkedIn export or take a quiz.</p>'}</div>
        <small class="mr-disclaimer">A mismatch is flagged when evidence and quiz results differ by 20 points or more. LinkedIn-listed skills are self-reported claims. Quiz results are learning checks, not formal skill certifications.</small></section></main></div></div>`;
}

const mismatchReportStyles = document.createElement('style');
mismatchReportStyles.textContent = `
.mr-page{max-width:1220px;margin:0 auto;color:#e7eef7}.mr-head{display:flex;justify-content:space-between;gap:20px;padding:8px 0 20px}.mr-eyebrow{font-size:11px;letter-spacing:.15em;color:#70b5ed;font-weight:800}.mr-head h2{font-size:30px;margin:6px 0}.mr-head p,.mr-title p{margin:0;color:#8ea7c0;font-size:13px;line-height:1.5}.mr-meta{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}.mr-meta span{padding:7px 10px;background:#192638;border:1px solid #2b3c51;border-radius:20px;color:#9db2c8;font-size:11px}.mr-layout{display:grid;grid-template-columns:260px minmax(0,1fr);gap:18px;align-items:start}.mr-side{position:sticky;top:12px}.mr-score,.mr-filters,.mr-panel{background:#142131;border:1px solid #26374d;border-radius:13px}.mr-score{padding:20px;text-align:center}.mr-ring{width:132px;height:132px;border-radius:50%;margin:0 auto 12px;background:conic-gradient(#f4bd43 var(--score),#29384a 0);display:grid;place-items:center}.mr-ring>div{width:104px;height:104px;border-radius:50%;background:#142131;display:grid;place-items:center;font-size:28px;font-weight:800}.mr-score>b{font-size:15px}.mr-score>p{color:#8fa7c0;font-size:12px;line-height:1.5;margin:8px 0 0}.mr-filters{padding:8px;margin-top:10px}.mr-filters button{width:100%;display:flex;align-items:center;gap:9px;padding:10px 9px;background:transparent;border:0;border-radius:7px;color:#d8e4f1;text-align:left;cursor:pointer}.mr-filters button.active{background:#1b2d43}.mr-filters button>b{margin-left:auto;color:#9bb1c7}.mr-filters i{width:9px;height:9px;border-radius:50%;background:#68a8ed}.mr-filters i.overclaimed{background:#fb777a}.mr-filters i.hidden{background:#46c6d6}.mr-filters i.verified{background:#50cf9a}.mr-filters i.needs_quiz{background:#a487ef}.mr-filters i.needs_work{background:#f5b942}.mr-content{min-width:0}.mr-panel{padding:18px;margin-bottom:14px}.mr-title{margin-bottom:12px}.mr-panel h3{font-size:17px;margin:0 0 4px}.mr-actions{display:grid;gap:8px}.mr-action{display:flex;gap:12px;padding:13px;background:#172638;border:1px solid #2a3c51;border-radius:9px}.mr-action-icon{flex:0 0 26px;width:26px;height:26px;display:grid;place-items:center;border-radius:50%;background:#153b4c;color:#4cc6d4;font-weight:800}.mr-action-icon.warn{background:#422c2b;color:#ff8a75}.mr-action b{font-size:14px}.mr-action p{color:#96adc4;font-size:12px;line-height:1.5;margin:5px 0}.mr-action .btn{padding:6px 10px;font-size:11px}.mr-tabs{display:flex;gap:17px;overflow-x:auto;border-bottom:1px solid #2a3b50;margin-bottom:8px}.mr-tabs button{white-space:nowrap;color:#92a9c1;background:none;border:0;border-bottom:2px solid transparent;padding:10px 3px;cursor:pointer;font-size:12px}.mr-tabs button.active{color:#78baff;border-bottom-color:#78baff}.mr-columns,.mr-row{display:grid;grid-template-columns:minmax(100px,1.1fr) minmax(95px,1fr) minmax(95px,1fr) minmax(100px,.9fr) 14px;gap:12px;align-items:center}.mr-columns{padding:9px 8px;color:#8fa7c0;font-size:11px}.mr-row{width:100%;padding:12px 8px;background:none;border:0;border-top:1px solid #26384d;color:#e7eef7;text-align:left;cursor:pointer}.mr-row:hover{background:#18283a}.mr-meter{display:flex;align-items:center;gap:8px;color:#b2c3d5;font-size:12px}.mr-meter>i{height:8px;flex:1;background:#29394d;border-radius:8px;overflow:hidden}.mr-meter em{display:block;height:100%;background:#899daf;border-radius:8px}.mr-meter.quiz em{background:#5da9f7}.mr-badge{padding:5px 8px;border-radius:14px;text-align:center;font-size:10px;background:#27394a;color:#c0d0e0}.mr-badge.overclaimed{background:#4a2c30;color:#ff9790}.mr-badge.hidden{background:#163e49;color:#65d6e3}.mr-badge.verified{background:#173d32;color:#72dda9}.mr-badge.needs_quiz{background:#342d4b;color:#c6afff}.mr-badge.needs_work{background:#463a22;color:#ffd166}.mr-detail{padding:12px 14px 15px;margin:0 0 7px 8px;background:#101b29;border-left:2px solid #4d91d0;color:#a6b9cc;font-size:12px}.mr-detail h4{color:#e6eef7;margin:10px 0 6px}.mr-detail p{line-height:1.5}.mr-detail a{color:#79baff}.mr-detail blockquote{margin:6px 0;padding:7px 10px;border-left:2px solid #758ca5;background:#182637;color:#aebed0}.mr-topic{display:grid;grid-template-columns:140px 1fr 35px;gap:10px;align-items:center;margin:8px 0}.mr-topic>i{height:7px;background:#2b3a4d;border-radius:8px;overflow:hidden}.mr-topic em{display:block;height:100%;background:#57c69b}.mr-topic b{text-align:right}.mr-disclaimer{display:block;color:#8199b2;font-size:10px;margin-top:12px;line-height:1.5}.mr-empty{padding:18px;color:#91a8c0;font-size:13px}.mr-page .btn{background:transparent;color:#b9d6f2;border:1px solid #3a526c}.mr-page .btn:hover{background:#213750}
@media(max-width:800px){.mr-layout{grid-template-columns:1fr}.mr-side{position:static}.mr-filters{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}.mr-head{display:block}.mr-meta{justify-content:flex-start;margin-top:12px}}
@media(max-width:560px){.mr-panel{padding:12px}.mr-columns,.mr-row{grid-template-columns:minmax(80px,1fr) minmax(70px,.8fr) minmax(70px,.8fr) 14px}.mr-columns span:nth-child(4),.mr-row .mr-badge{display:none}.mr-action{padding:10px}.mr-tabs{gap:12px}.mr-topic{grid-template-columns:95px 1fr 30px}}
`;
document.head.appendChild(mismatchReportStyles);

// Replace the basic mismatch list from the legacy app with this data-driven report.
VIEWS.mismatch = renderMismatchReport;

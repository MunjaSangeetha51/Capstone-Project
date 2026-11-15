'use strict';

const LEVERAGE_SKILLS = [
  'Java','Machine Learning','Data Analysis','SQL','Node.js','SEO','Android','Flutter',
  'Canva','Social Media','Graphic Design','Digital Marketing','Figma','UI/UX Design',
  'Photoshop','Video Editing','HTML/CSS','Python','JavaScript','React','Excel',
  'Content Writing','Git','English','MongoDB'
];
const LEVERAGE_SAMPLE = {
  Java:61,'Machine Learning':60,'Data Analysis':45,SQL:45,'Node.js':40,SEO:45,
  Android:45,Flutter:45,Canva:55,'Social Media':55,'Graphic Design':40,
  'Digital Marketing':30,Figma:50,'UI/UX Design':45,Photoshop:25,'Video Editing':20,
  'HTML/CSS':75,Python:72,JavaScript:66,React:62,Excel:74,'Content Writing':70,Git:80,English:85,MongoDB:20
};
const LEVERAGE_POSTINGS = [
  {title:'Web Development',req:{'HTML/CSS':60,JavaScript:60}},
  {title:'Python Development',req:{Python:60}},
  {title:'Content Writing',req:{'Content Writing':60}},
  {title:'Front End Development',req:{'HTML/CSS':60,JavaScript:60,React:60}},
  {title:'Data Entry & MIS',req:{Excel:60}},
  {title:'Machine Learning',req:{'Machine Learning':60}},
  {title:'Java Development',req:{Java:60}},
  {title:'SEO',req:{SEO:60}},
  {title:'Data Science',req:{'Data Analysis':60,'Machine Learning':60}},
  {title:'Node.js Development',req:{'Node.js':60}},
  {title:'Android App Development',req:{Android:60}},
  {title:'Flutter App Development',req:{Flutter:60}},
  {title:'Graphic Design',req:{'Graphic Design':60,Canva:60}},
  {title:'Social Media Marketing',req:{'Social Media':60,Canva:60}},
  {title:'Digital Marketing',req:{'Digital Marketing':60,SEO:60,'Social Media':60}},
  {title:'UI/UX Design',req:{Figma:60,'UI/UX Design':60}},
  {title:'Data Analytics',req:{'Data Analysis':60,SQL:60}},
  {title:'MERN Stack Development',req:{'Node.js':60,MongoDB:60,JavaScript:60,React:60}},
  {title:'Video Editing',req:{'Video Editing':60}}
];
const LEVERAGE_RESOURCES = {
  'Machine Learning':'https://developers.google.com/machine-learning/crash-course',
  'Data Analysis':'https://www.khanacademy.org/math/statistics-probability',
  'Node.js':'https://nodejs.org/en/learn',SEO:'https://developers.google.com/search/docs/fundamentals/seo-starter-guide',
  Android:'https://developer.android.com/courses',Flutter:'https://docs.flutter.dev/get-started/learn-more',
  Canva:'https://www.canva.com/designschool/', 'Social Media':'https://www.facebook.com/business/learn',
  'Graphic Design':'https://www.adobe.com/creativecloud/design/discover/graphic-design.html',
  'Digital Marketing':'https://skillshop.withgoogle.com/',Figma:'https://help.figma.com/hc/en-us/categories/360002051613-Get-started',
  'UI/UX Design':'https://www.nngroup.com/articles/ux-basics-study-guide/',
  Photoshop:'https://helpx.adobe.com/photoshop/tutorials.html',
  'Video Editing':'https://www.blackmagicdesign.com/products/davinciresolve/training',
  Java:'https://dev.java/learn/',SQL:'https://sqlbolt.com/',Excel:'https://support.microsoft.com/excel',
  'HTML/CSS':'https://web.dev/learn/',Python:'https://docs.python.org/3/tutorial/',
  JavaScript:'https://javascript.info/',React:'https://react.dev/learn',
  'Content Writing':'https://developers.google.com/search/docs/fundamentals/creating-helpful-content',
  Git:'https://git-scm.com/docs/gittutorial',English:'https://learnenglish.britishcouncil.org/',
  MongoDB:'https://learn.mongodb.com/'
};
const LEVERAGE_QUIZ_NAMES = Object.fromEntries([
  'Java','Machine Learning','Data Analysis','SQL','Node.js','SEO','Android','Flutter','Canva',
  'Social Media','Graphic Design','Digital Marketing','Figma','UI/UX Design','Photoshop',
  'Video Editing','HTML/CSS','Python','JavaScript','React','Excel','Content Writing','Git','English','MongoDB'
].map(skill=>[skill,skill]));
let LEVERAGE_SELECTED = '';

function leverageQuizKey(skill){
  return LEVERAGE_QUIZ_NAMES[skill]||null;
}
function leverageMode(){
  return S.leverageMode==='quiz'&&Object.keys(S.quiz||{}).length?'quiz':'sample';
}
function leverageSampleScores(){
  const saved=S.leverageScenario||{};
  return Object.fromEntries(LEVERAGE_SKILLS.map(skill=>{
    const key=leverageQuizKey(skill);
    return [skill,Math.max(0,Math.min(100,Number(saved[skill]??(key?S.quiz[key]:LEVERAGE_SAMPLE[skill]))||0))];
  }));
}
function leverageScores(){
  const sample=leverageSampleScores();
  if(leverageMode()==='sample')return sample;
  return Object.fromEntries(LEVERAGE_SKILLS.map(skill=>{
    const key=leverageQuizKey(skill);return [skill,key?Number(S.quiz[key])||0:0];
  }));
}
function leveragePostingState(posting,scores){
  const missing=Object.entries(posting.req).filter(([skill,need])=>(scores[skill]||0)<need)
    .map(([skill,need])=>({skill,missing:need-(scores[skill]||0)}));
  if(!missing.length)return 'Ready Now';
  if(missing.length===1&&missing[0].missing<=25)return 'Stretch';
  return 'Not Yet';
}
function leverageCounts(scores){
  const counts={'Ready Now':0,Stretch:0,'Not Yet':0};
  LEVERAGE_POSTINGS.forEach(post=>counts[leveragePostingState(post,scores)]++);
  return counts;
}
function leverageSequence(scores){
  const current={...scores},remaining=LEVERAGE_SKILLS.filter(skill=>current[skill]<60),
    steps=[{label:'Today',ready:leverageCounts(current)['Ready Now']}],order=[];
  while(remaining.length){
    const before=leverageCounts(current)['Ready Now'];
    const candidates=remaining.map(skill=>{
      const trial={...current,[skill]:60};
      return {skill,unlocks:leverageCounts(trial)['Ready Now']-before,score:current[skill]};
    }).sort((a,b)=>b.unlocks-a.unlocks||a.score-b.score||a.skill.localeCompare(b.skill));
    const next=candidates[0];
    current[next.skill]=60;remaining.splice(remaining.indexOf(next.skill),1);
    order.push({...next,ready:leverageCounts(current)['Ready Now']});
    steps.push({label:`+ ${next.skill}`,ready:leverageCounts(current)['Ready Now']});
  }
  return {order,steps};
}
function leverageRandomAverage(scores,stepCount){
  const remaining=LEVERAGE_SKILLS.filter(skill=>scores[skill]<60),runs=10;
  if(!remaining.length)return [leverageCounts(scores)['Ready Now']];
  const totals=Array(stepCount+1).fill(0);
  for(let run=0;run<runs;run++){
    const rotated=remaining.map((_,i)=>remaining[(i*7+run*3)%remaining.length]);
    const order=[...new Set(rotated),...remaining.filter(skill=>!rotated.includes(skill))],state={...scores};
    totals[0]+=leverageCounts(state)['Ready Now'];
    order.forEach((skill,index)=>{state[skill]=60;totals[index+1]+=leverageCounts(state)['Ready Now'];});
  }
  return totals.map(value=>value/runs);
}
function setLeverageMode(mode){
  S.leverageMode=mode==='quiz'&&Object.keys(S.quiz||{}).length?'quiz':'sample';persist();render();
}
function resetLeverageScenario(){S.leverageScenario={};S.leverageMode='sample';persist();render();}
function previewLeverageScore(input){const out=document.getElementById(input.dataset.output);if(out)out.textContent=input.value;}
function setLeverageScore(skill,value){
  const scroll=document.querySelector('main')?.scrollTop||0;
  S.leverageMode='sample';S.leverageScenario={...leverageSampleScores(),[skill]:Math.max(0,Math.min(100,Number(value)||0))};persist();render();
  requestAnimationFrame(()=>{const main=document.querySelector('main');if(main)main.scrollTop=scroll;});
}
function jumpToLeverageSkill(skill){
  LEVERAGE_SELECTED=skill;const el=document.getElementById(`leverage-skill-${roadmapSlug(skill)}`);
  if(el){el.scrollIntoView({behavior:'smooth',block:'center'});el.focus({preventScroll:true});}
}
function leverageChart(ranked,random){
  const width=760,height=210,pad=34,max=Math.max(1,...ranked.map(step=>step.ready),...random),
    x=i=>pad+i*(width-2*pad)/Math.max(1,ranked.length-1),y=n=>height-pad-n*(height-2*pad)/max;
  const points=ranked.map((step,i)=>`${x(i)},${y(step.ready)}`).join(' '),
    randomPoints=random.map((value,i)=>`${x(i)},${y(value)}`).join(' ');
  const ticks=[0,Math.ceil(max/2),max];
  return `<svg class="leverage-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Ready Now sample posting counts by number of skills proven">
    ${ticks.map(value=>`<g><line x1="${pad}" x2="${width-pad}" y1="${y(value)}" y2="${y(value)}"/><text x="4" y="${y(value)+4}">${value}</text></g>`).join('')}
    <polyline class="leverage-random" points="${randomPoints}"/><polyline class="leverage-ranked" points="${points}"/>
    <circle cx="${x(0)}" cy="${y(ranked[0].ready)}" r="5"/><text x="${pad}" y="${height-5}">0</text><text x="${width-pad}" y="${height-5}" text-anchor="end">${ranked.length-1} skills proven</text>
  </svg>`;
}
function renderSkillLeverage(){
  const scores=leverageScores(),mode=leverageMode(),counts=leverageCounts(scores),
    {order,steps}=leverageSequence(scores),random=leverageRandomAverage(scores,steps.length-1),
    supported=LEVERAGE_SKILLS.filter(skill=>leverageQuizKey(skill)).length,
    sliders=LEVERAGE_SKILLS.map(skill=>{
      const actualKey=leverageQuizKey(skill),actual=actualKey&&Number.isFinite(Number(S.quiz[actualKey]))?Number(S.quiz[actualKey]):null,
        shown=mode==='quiz'?scores[skill]:leverageSampleScores()[skill],selected=LEVERAGE_SELECTED===skill,
        valueId=`leverage-output-${roadmapSlug(skill)}`;
      return `<label class="leverage-skill ${selected?'selected':''}" id="leverage-skill-${roadmapSlug(skill)}" tabindex="-1"><span><b>${skill}</b><small>${actual===null?'Quiz not taken':`Quiz ${actual}%`}</small></span><input type="range" min="0" max="100" step="1" value="${shown}" ${mode==='quiz'?'disabled':''} aria-label="${skill} scenario score" data-output="${valueId}" oninput="previewLeverageScore(this)" onchange="setLeverageScore('${skill}',this.value)"><output id="${valueId}">${shown}</output></label>`;
    }).join('');
  const bucketCards=['Ready Now','Stretch','Not Yet'].map(status=>`<section class="leverage-bucket ${roadmapSlug(status)}"><h3>${status}<span>${counts[status]}</span></h3><div>${LEVERAGE_POSTINGS.filter(post=>leveragePostingState(post,scores)===status).map(post=>{
    const gaps=Object.entries(post.req).filter(([skill,need])=>scores[skill]<need).map(([skill,need])=>skill);
    return `<article class="leverage-posting"><b>${post.title}</b>${gaps.length?`<small>Needs ${gaps.map(skill=>`${skill} (${Math.max(0,60-(scores[skill]||0))} to prove)`).join(', ')}</small>`:''}</article>`;
  }).join('')||'<small>None in this scenario.</small>'}</div></section>`).join('');
  const rankedRows=order.map((item,index)=>`<button type="button" class="leverage-rank-row ${LEVERAGE_SELECTED===item.skill?'selected':''}" onclick="jumpToLeverageSkill('${item.skill}')"><span>${index+1}</span><b>${item.skill}<small>${item.score}% ${mode==='quiz'?'verified':'scenario'}${item.score>=60?' · proven':''}</small></b><strong>+${item.unlocks} ${item.unlocks===1?'posting':'postings'}</strong></button>`).join('');
  const quizButton=mode==='quiz'?'<button class="btn o" type="button" onclick="setLeverageMode(\'sample\')">Use sample scenario</button>':'<button class="btn o" type="button" onclick="setLeverageMode(\'quiz\')" '+(Object.keys(S.quiz||{}).length?'':'disabled title="Complete a quiz first"')+'>Use saved quiz scores</button>';
  return `<div class="leverage-page"><header class="leverage-hero"><span class="roadmap-eyebrow">SKILLPROOF · CAREER READINESS</span><h2>🏆 Skill Leverage</h2><p>Prioritize skills by the Ready Now sample postings they can unlock. A score of 60 or more counts as proven.</p></header>
    <div class="leverage-note"><b>${mode==='quiz'?'Quiz mode':'Illustrative sample scenario'}</b><span>${mode==='quiz'?`Using your saved quiz scores. ${supported} of ${LEVERAGE_SKILLS.length} listed skills have quiz banks; unsupported or untested skills count as 0 until verified.`:'Sample scores and posting profiles are illustrative, not quiz results or live vacancies. Adjust the sliders to explore the model.'} Posting results are planning estimates, not application recommendations.</span></div>
    <section class="leverage-grid"><article class="leverage-panel"><div class="leverage-panel-head"><div><h3>Set your skill scores</h3><p>${mode==='quiz'?'Saved quiz scores are shown and locked.':'Drag a skill to model a scenario; 60 or more counts as proven in this scenario.'}</p></div><div>${quizButton}<button class="btn o" type="button" onclick="resetLeverageScenario()">Reset to sample</button></div></div><div class="leverage-slider-grid">${sliders}</div></article>
    <article class="leverage-panel"><div class="leverage-panel-head"><div><h3>Prove these next</h3><p>Ranked by the additional Ready Now sample postings each skill unlocks on its own.</p></div></div><div class="leverage-ranking">${rankedRows||'<p>All listed skills meet the current threshold.</p>'}</div></article></section>
    <section class="leverage-panel"><h3>Ready Now count as you prove skills in order</h3><div class="leverage-legend"><span><i></i>Leverage order</span><span><i></i>Random order (illustrative average)</span></div>${leverageChart(steps,random)}<p class="leverage-footnote">The random line is a deterministic scenario comparison across rotated skill orders, not a measured study.</p></section>
    <section class="leverage-panel"><div class="leverage-panel-head"><div><h3>Your internship posting profiles</h3><p>Sample role profiles created for the prototype. They are not verified openings.</p></div><b class="leverage-counts">${counts['Ready Now']} Ready · ${counts.Stretch} Stretch · ${counts['Not Yet']} Not yet</b></div><div class="leverage-buckets">${bucketCards}</div></section>
    ${LEVERAGE_SELECTED?`<section class="leverage-panel"><h3>Plan for ${LEVERAGE_SELECTED}</h3><p>Current ${scores[LEVERAGE_SELECTED]} / 100 · ${scores[LEVERAGE_SELECTED]>=60?'meets the modeled proven threshold':'needs '+(60-scores[LEVERAGE_SELECTED])+' more points to reach 60'}.</p><p><a href="${LEVERAGE_RESOURCES[LEVERAGE_SELECTED]||'https://www.google.com/search?q='+encodeURIComponent(LEVERAGE_SELECTED+' official learning resources')}" target="_blank" rel="noopener noreferrer">Open a study resource ↗</a></p>${leverageQuizKey(LEVERAGE_SELECTED)?`<button class="btn" type="button" onclick="openSkillQuiz('${leverageQuizKey(LEVERAGE_SELECTED)}')">Take ${leverageQuizKey(LEVERAGE_SELECTED)} quiz</button>`:'<small>A quiz bank for this skill has not been added yet; the displayed score is only a scenario estimate.</small>'}</section>`:''}
  </div>`;
}
const leverageStyles=document.createElement('style');
leverageStyles.textContent=`
.leverage-page{max-width:1200px;margin:0 auto;color:#e8eff7}.leverage-hero{padding:20px 24px;background:#101a29;border-radius:16px}.leverage-hero h2{font-size:32px;margin:7px 0}.leverage-hero p,.leverage-panel-head p{color:#9aafc9;line-height:1.5}.leverage-note{display:flex;gap:12px;padding:13px 16px;margin:12px 0;background:#1a2940;border-left:3px solid #39c5b4;border-radius:8px;color:#bed0e4;font-size:13px}.leverage-note b{white-space:nowrap;color:#fff}.leverage-grid{display:grid;grid-template-columns:1.2fr .8fr;gap:14px}.leverage-panel{margin:14px 0;padding:20px;background:#152237;border:1px solid #293b56;border-radius:14px}.leverage-panel h3{font-size:19px;margin:0 0 8px}.leverage-panel-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:13px}.leverage-panel-head p{margin:0;font-size:13px}.leverage-panel-head>div:last-child{display:flex;gap:8px;flex-wrap:wrap}.leverage-slider-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:3px 20px}.leverage-skill{display:grid;grid-template-columns:100px minmax(80px,1fr) 32px;gap:9px;align-items:center;min-height:38px;border-bottom:1px solid #263953;padding:5px;border-radius:5px}.leverage-skill.selected{outline:2px solid #3bc6b4}.leverage-skill span b,.leverage-skill span small{display:block}.leverage-skill span small{font-size:10px;color:#8da5c0}.leverage-skill input{width:100%;accent-color:#3bc6b4}.leverage-skill input:disabled{opacity:.65}.leverage-skill output{text-align:right;color:#56d7c2}.leverage-ranking{max-height:420px;overflow:auto}.leverage-rank-row{width:100%;display:grid;grid-template-columns:26px 1fr auto;align-items:center;gap:10px;padding:10px 7px;color:#ecf4fc;background:none;border:0;border-bottom:1px solid #2a3b55;text-align:left;cursor:pointer}.leverage-rank-row:hover,.leverage-rank-row.selected{background:#193f43}.leverage-rank-row>span{color:#9bb0c9}.leverage-rank-row b small{display:block;color:#8da5c0;font-size:11px;font-weight:400;margin-top:3px}.leverage-rank-row strong{color:#44d5bd;white-space:nowrap}.leverage-legend{display:flex;gap:18px;color:#a9bdd4;font-size:12px}.leverage-legend span{display:flex;align-items:center;gap:6px}.leverage-legend i{width:18px;height:3px;background:#35c9b3}.leverage-legend span+span i{background:#8696ae;border-top:1px dashed #fff}.leverage-chart{width:100%;height:auto;margin-top:10px}.leverage-chart line{stroke:#344762;stroke-width:1}.leverage-chart text{fill:#aabbd1;font-size:11px}.leverage-chart polyline{fill:none;stroke-width:3}.leverage-chart .leverage-ranked{stroke:#35c9b3}.leverage-chart .leverage-random{stroke:#8495ae;stroke-width:2;stroke-dasharray:6 5}.leverage-chart circle{fill:#35c9b3}.leverage-footnote{font-size:11px;color:#94a9c1}.leverage-counts{color:#7de2cb;white-space:nowrap}.leverage-buckets{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.leverage-bucket{padding:12px;border:1px solid #315048;border-radius:10px;background:#142b34}.leverage-bucket h3{display:flex;justify-content:space-between;align-items:center;font-size:15px}.leverage-bucket h3 span{color:#fff;background:#1f9e89;border-radius:20px;padding:2px 8px}.leverage-bucket.stretch{background:#332b20;border-color:#74603a}.leverage-bucket.stretch h3 span{background:#ac741b}.leverage-bucket.not-yet{background:#1b2638;border-color:#354660}.leverage-bucket.not-yet h3 span{background:#3a506e}.leverage-posting{padding:8px 0;border-top:1px solid #ffffff18}.leverage-posting b,.leverage-posting small{display:block}.leverage-posting small{margin-top:3px;color:#a9bdd4;font-size:11px}.leverage-page a{color:#60d8c1}.leverage-page .btn{margin:2px;font-size:12px;padding:8px 11px}
@media(max-width:850px){.leverage-grid{grid-template-columns:1fr}.leverage-buckets{grid-template-columns:1fr}.leverage-note{display:block}.leverage-note b{display:block;margin-bottom:4px}}
@media(max-width:560px){.leverage-slider-grid{grid-template-columns:1fr}.leverage-skill{grid-template-columns:95px minmax(65px,1fr) 28px}.leverage-panel{padding:14px}.leverage-panel-head{align-items:flex-start;flex-direction:column}}
`;
document.head.appendChild(leverageStyles);

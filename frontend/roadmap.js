'use strict';

const ROADMAP_SKILLS = [
  'Python','Java','OOP','Spring Boot','DSA','HTML','CSS','JavaScript','React','APIs','SQL',
  'Excel','Tableau','Power BI','Statistics','ML','AI','Analytics','Manual Testing','Selenium',
  'AWS','Azure','Networking','Security','Figma','Design Thinking','Canva','Communication',
  'Digital Marketing','Content Writing','Recruiting'
];
const ROADMAP_CATEGORIES = ['All','Software','Data and AI','Cloud and security','Design','Business and ops','Marketing and people'];
const ROADMAP_PRESETS = {
  'AI/ML student': {Python:75,Java:40,OOP:45,'Spring Boot':0,DSA:50,HTML:0,CSS:0,JavaScript:0,React:0,APIs:0,SQL:50,Excel:0,Tableau:0,'Power BI':0,Statistics:55,ML:60,AI:55,Analytics:0,'Manual Testing':0,Selenium:0,AWS:0,Azure:0,Networking:0,Security:0,Figma:0,'Design Thinking':0,Canva:0,Communication:50,'Digital Marketing':0,'Content Writing':0,Recruiting:0},
  'Web student': {Python:20,Java:0,OOP:20,'Spring Boot':0,DSA:35,HTML:75,CSS:70,JavaScript:65,React:55,APIs:45,SQL:30,Excel:0,Tableau:0,'Power BI':0,Statistics:20,ML:0,AI:0,Analytics:10,'Manual Testing':20,Selenium:0,AWS:10,Azure:0,Networking:10,Security:10,Figma:20,'Design Thinking':20,Canva:25,Communication:50,'Digital Marketing':0,'Content Writing':0,Recruiting:0},
  'Data student': {Python:65,Java:0,OOP:20,'Spring Boot':0,DSA:25,HTML:0,CSS:0,JavaScript:0,React:0,APIs:10,SQL:65,Excel:70,Tableau:45,'Power BI':35,Statistics:65,ML:50,AI:40,Analytics:60,'Manual Testing':0,Selenium:0,AWS:0,Azure:0,Networking:0,Security:0,Figma:0,'Design Thinking':0,Canva:0,Communication:50,'Digital Marketing':0,'Content Writing':0,Recruiting:0},
  'Beginner': {Communication:50}
};
const ROADMAP_ROLES = [
  {name:'AI/ML engineer',category:'Data and AI',req:{Python:70,ML:65,AI:60}},
  {name:'Data scientist',category:'Data and AI',req:{Python:70,Statistics:65,ML:65}},
  {name:'Software developer',category:'Software',req:{DSA:65,Java:60}},
  {name:'Python developer',category:'Software',req:{Python:65,SQL:55,OOP:55,APIs:50}},
  {name:'Backend developer',category:'Software',req:{Python:65,Java:55,SQL:55,APIs:60}},
  {name:'Java developer',category:'Software',req:{Java:65,OOP:60,'Spring Boot':50}},
  {name:'Operations associate',category:'Business and ops',req:{Excel:55,Communication:50}},
  {name:'Business analyst',category:'Business and ops',req:{Excel:60,SQL:55,Communication:60,Analytics:55}},
  {name:'Business development associate',category:'Business and ops',req:{Communication:65,Excel:50}},
  {name:'HR recruiter',category:'Marketing and people',req:{Recruiting:60,Communication:60}},
  {name:'Data analyst',category:'Data and AI',req:{Excel:65,SQL:65,Tableau:50,'Power BI':45}},
  {name:'Market research analyst',category:'Business and ops',req:{Analytics:60,Excel:55}},
  {name:'Technical support associate',category:'Cloud and security',req:{Communication:55,Networking:45,Security:35}},
  {name:'Research analyst',category:'Business and ops',req:{Excel:55,Analytics:60,Communication:55}},
  {name:'Product management intern',category:'Business and ops',req:{Analytics:55,Communication:60,Figma:35}},
  {name:'Full stack developer',category:'Software',req:{HTML:60,CSS:55,JavaScript:60,React:55}},
  {name:'Frontend developer',category:'Software',req:{HTML:65,CSS:60,JavaScript:65,React:60}},
  {name:'Software testing engineer',category:'Software',req:{'Manual Testing':65,Selenium:55}},
  {name:'Cloud engineer',category:'Cloud and security',req:{AWS:60,Azure:50}},
  {name:'Cybersecurity analyst',category:'Cloud and security',req:{Networking:65,Security:60}},
  {name:'UI/UX designer',category:'Design',req:{Figma:65,'Design Thinking':55,Canva:45}},
  {name:'Digital marketing executive',category:'Marketing and people',req:{'Digital Marketing':65,'Content Writing':50,Analytics:45}},
  {name:'Content writer',category:'Marketing and people',req:{'Content Writing':70,'Digital Marketing':40}}
];
const ROADMAP_COMPANIES = ['Brightpath','Kestrel Systems','Northwind Labs'];
const ROADMAP_JOB_PATTERNS = {
  'AI/ML engineer': [{Python:65,ML:65,AI:50},{Python:65,ML:75,AI:50},{Python:80,ML:85,AI:70}],
  'Data scientist': [{Python:65,Statistics:65,ML:60},{Python:65,Statistics:75,ML:60},{Python:80,Statistics:85,ML:80}],
  'Python developer': [{Python:65,SQL:55,OOP:55},{Python:55,SQL:65,OOP:65,APIs:60},{Python:75,SQL:75,OOP:75,APIs:70}],
  'Java developer': [{Java:65,OOP:60},{Java:75,OOP:70,'Spring Boot':50},{Java:85,OOP:80,'Spring Boot':60}],
  'Backend developer': [{Python:65,Java:55},{Python:75,Java:65,SQL:60,APIs:65},{Python:85,Java:75,SQL:70,APIs:75}],
  'Software developer': [{DSA:65,Java:60},{DSA:65,Java:55},{DSA:60,Java:55}],
  'Business development associate': [{Communication:65},{Communication:75,Excel:85},{Communication:85,Excel:60}],
  'Operations associate': [{Excel:55,Communication:65},{Excel:65,Communication:65},{Excel:75,Communication:65}],
  'Data analyst': [{Excel:65,SQL:45},{Excel:75,SQL:45},{Excel:85,SQL:60,Tableau:60,'Power BI':55}],
  'Market research analyst': [{Analytics:60},{Analytics:70,Excel:55},{Analytics:80,Excel:65}],
  'Research analyst': [{Analytics:60},{Analytics:70,Communication:55},{Analytics:80,Excel:65,Communication:60}]
};
let ROADMAP_UI = {category:'All',roleView:'Top 8 picks',selectedRole:'Python developer',jobFilter:'All'};

function roadmapLevels(){
  if(!S.roadmapSkills){S.roadmapSkills={...ROADMAP_PRESETS['AI/ML student']};}
  return S.roadmapSkills;
}
function roadmapLevel(skill){return Math.max(0,Math.min(100,Number(roadmapLevels()[skill])||0));}
function roadmapSlug(value){return String(value).toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');}
function roadmapJobs(){
  return ROADMAP_ROLES.flatMap((role,roleIndex)=>[0,10,20].map((extra,variant)=>{
    const pattern=ROADMAP_JOB_PATTERNS[role.name]?.[variant];
    const req=pattern||Object.fromEntries(Object.entries(role.req).map(([skill,need])=>[skill,Math.min(100,need+extra)]));
    return {id:`${roleIndex}-${variant}`,role:role.name,category:role.category,
      company:ROADMAP_COMPANIES[(roleIndex+variant)%ROADMAP_COMPANIES.length],
      title:`${role.name}${role.name.endsWith('intern')?'':' intern'}`,req};
  }));
}
function roadmapJobStatus(job,levels){
  const gaps=Object.entries(job.req).map(([skill,need])=>({skill,need,gap:Math.max(0,need-(levels[skill]||0))})).filter(item=>item.gap>0);
  if(!gaps.length)return {status:'Ready Now',gaps:[]};
  if(gaps.every(item=>item.gap<=20))return {status:'Stretch',gaps};
  return {status:'Not Yet',gaps};
}
function roadmapFit(req,levels){
  const items=Object.entries(req);
  return Math.round(100*items.reduce((sum,[skill,need])=>sum+Math.min((levels[skill]||0)/need,1),0)/items.length);
}
function roadmapAnalysis(){
  const levels=roadmapLevels(), jobs=roadmapJobs();
  const states=jobs.map(job=>({...job,...roadmapJobStatus(job,levels)}));
  const roleRows=ROADMAP_ROLES.map(role=>({...role,fit:roadmapFit(role.req,levels),ready:states.filter(job=>job.role===role.name&&job.status==='Ready Now').length})).sort((a,b)=>b.fit-a.fit||a.name.localeCompare(b.name));
  const ready=new Set(states.filter(job=>job.status==='Ready Now').map(job=>job.id));
  const left=ROADMAP_SKILLS.filter(skill=>roadmapLevel(skill)<75);
  const sim=[{skill:'Today',ready:ready.size}], ranked=[];
  while(left.length){
    let best=null,bestIds=[];
    const order=['ML','Statistics','Communication','Excel','Analytics',...ROADMAP_SKILLS];
    for(const skill of order.filter(item=>left.includes(item))){
      const trial={...levels,[skill]:Math.max(75,roadmapLevel(skill))};
      const ids=states.filter(job=>!ready.has(job.id)&&roadmapJobStatus(job,trial).status==='Ready Now').map(job=>job.id);
      if(ids.length>(bestIds.length)||(!best&&ids.length===bestIds.length)){best=skill;bestIds=ids;}
    }
    if(best===null)break;
    left.splice(left.indexOf(best),1);
    if(bestIds.length){
      ranked.push({skill:best,unlocks:bestIds.length,current:roadmapLevel(best),names:states.filter(job=>bestIds.includes(job.id)).slice(0,4).map(job=>`${job.company} · ${job.title}`)});
      bestIds.forEach(id=>ready.add(id));
      sim.push({skill:best,ready:ready.size});
    }
  }
  return {levels,jobs:states,roles:roleRows,leverage:ranked,simulation:sim};
}
function setRoadmapPreset(name){
  const preset=ROADMAP_PRESETS[name];if(!preset)return;
  S.roadmapSkills=Object.fromEntries(ROADMAP_SKILLS.map(skill=>[skill,preset[skill]||0]));
  persist();render();
}
function resetRoadmap(){setRoadmapPreset('Beginner');}
function setRoadmapLevel(skill,value){
  S.roadmapSkills={...roadmapLevels(),[skill]:Math.max(0,Math.min(100,Number(value)||0))};
  persist();render();
}
function previewRoadmapLevel(input){
  const output=document.getElementById(`roadmap-level-${roadmapSlug(input.dataset.skill)}`);
  if(output)output.textContent=`${input.value}%`;
}
function setRoadmapCategory(category){ROADMAP_UI.category=category;render();}
function setRoadmapRoleView(view){ROADMAP_UI.roleView=view;render();}
function selectRoadmapRole(role){ROADMAP_UI.selectedRole=role;render();}
function setRoadmapJobFilter(filter){ROADMAP_UI.jobFilter=filter;render();}
function roadmapButton(label,active,handler){return `<button class="btn ${active?'':'o'} roadmap-filter" type="button" onclick="${handler}">${label}</button>`;}
function renderCareerRoadmap(){
  const {levels,jobs,roles,leverage,simulation}=roadmapAnalysis();
  const counts={'Ready Now':jobs.filter(job=>job.status==='Ready Now').length,'Stretch':jobs.filter(job=>job.status==='Stretch').length,'Not Yet':jobs.filter(job=>job.status==='Not Yet').length};
  const presetButtons=Object.keys(ROADMAP_PRESETS).map(name=>roadmapButton(name,false,`setRoadmapPreset('${name}')`)).join('')+roadmapButton('Reset',false,'resetRoadmap()');
  const sliders=ROADMAP_SKILLS.map(skill=>`<label class="roadmap-skill"><span><b>${skill}</b><output id="roadmap-level-${roadmapSlug(skill)}">${roadmapLevel(skill)}%</output></span><input data-skill="${skill}" type="range" min="0" max="100" step="5" value="${roadmapLevel(skill)}" aria-label="${skill} estimated verified level" oninput="previewRoadmapLevel(this)" onchange="setRoadmapLevel('${skill}',this.value)"></label>`).join('');
  const maxReady=Math.max(1,...simulation.map(step=>step.ready));
  const leverageView=leverage.length?`<div class="roadmap-leverage">${leverage.slice(0,5).map((item,index)=>`<div class="roadmap-leverage-row"><span class="roadmap-rank">${index+1}</span><div class="roadmap-leverage-copy"><b>Prove ${item.skill}</b><small>${item.current}% now · target about 75%</small></div><strong>+${item.unlocks}</strong></div>`).join('')}</div><p class="mut">Unlocks are estimated by raising one skill at a time to 75%, then rechecking all 69 sample postings.</p><div class="roadmap-simulation">${simulation.map((step,index)=>`<div class="roadmap-sim-row"><span>${index?`+ ${step.skill}`:'Today'}</span><div class="quiz-progress"><span style="width:${step.ready/maxReady*100}%"></span></div><b>${step.ready}</b></div>`).join('')}</div>`:'<div class="empty">Every currently modeled posting is already ready at these levels.</div>';
  const roleRows=roles.filter(role=>ROADMAP_UI.category==='All'||role.category===ROADMAP_UI.category);
  const topNames=new Set(roles.slice(0,8).map(role=>role.name));
  const visibleRoles=ROADMAP_UI.roleView==='Top 8 picks'?roleRows.filter(role=>topNames.has(role.name)):roleRows;
  const roleCards=visibleRoles.map((role,index)=>`<button type="button" class="roadmap-role ${ROADMAP_UI.selectedRole===role.name?'selected':''}" onclick="selectRoadmapRole('${role.name}')"><div class="roadmap-role-top"><b>${role.name}</b><strong>${role.fit}%</strong></div><div class="roadmap-role-meta">${topNames.has(role.name)?`Top pick ${roles.findIndex(row=>row.name===role.name)+1} · `:''}${role.category} · ${role.ready} of 3 jobs ready</div><div class="quiz-progress"><span style="width:${role.fit}%"></span></div></button>`).join('');
  const selected=roleRows.find(role=>role.name===ROADMAP_UI.selectedRole)||roleRows[0];
  const roleDetail=selected?`<div class="roadmap-detail"><div class="roadmap-detail-title"><div><span class="mut">Selected career path</span><h3>${selected.name}</h3></div><span class="roadmap-fit">${selected.fit}% fit</span></div><p class="mut">Typical skill levels for this role. The largest gap is a suggested place to focus first.</p>${Object.entries(selected.req).map(([skill,need])=>`<div class="roadmap-requirement"><span>${skill}</span><div class="quiz-progress"><span style="width:${Math.min(roadmapLevel(skill),100)}%"></span></div><small>${roadmapLevel(skill)}/${need}</small></div>`).join('')}${(()=>{const gaps=Object.entries(selected.req).map(([skill,need])=>({skill,gap:Math.max(0,need-roadmapLevel(skill))})).filter(item=>item.gap>0).sort((a,b)=>b.gap-a.gap);return gaps.length?`<p class="recommendation">Start with ${gaps[0].skill}: you are ${gaps[0].gap} points below the typical requirement.</p>`:'<p class="recommendation">Your current scenario meets the modeled requirements for this role.</p>'})()}</div>`:'<div class="empty">No roles in this category.</div>';
  const filteredJobs=jobs.filter(job=>(ROADMAP_UI.category==='All'||job.category===ROADMAP_UI.category)&&(ROADMAP_UI.jobFilter==='All'||job.status===ROADMAP_UI.jobFilter));
  const jobCards=filteredJobs.map(job=>`<article class="roadmap-job"><div class="roadmap-job-heading"><div><h4>${job.title}</h4><p class="mut">${job.company} · ${job.category} · sample role profile</p></div><span class="badge ${job.status==='Ready Now'?'strong':job.status==='Stretch'?'medium':'weak'}">${job.status}</span></div>${job.gaps.length?`<p class="mut">Still to prove: ${job.gaps.map(gap=>`${gap.skill} (+${gap.gap})`).join(', ')}</p>`:'<p class="mut">Modeled requirements met at these levels.</p>'}</article>`).join('');
  return `<div class="card roadmap-page"><div class="roadmap-hero"><div><span class="roadmap-eyebrow">CAREER PLANNER</span><h2>Your career roadmap</h2><p>Explore 23 roles, 69 sample job profiles, and skills that could unlock more Ready Now matches.</p></div><div class="roadmap-counts">${Object.entries(counts).map(([label,count])=>`<div><b>${count}</b><span>${label}</span></div>`).join('')}</div></div>
    <div class="roadmap-note"><b>Scenario planner</b><span>Start from a preset or adjust the sliders. In the full product, these levels would come from verified quiz results. Sample postings are illustrative and are not live vacancies.</span></div>
    <section class="roadmap-section"><div class="roadmap-section-heading"><div><h3>Your skill levels</h3><p class="mut">Set a starting point, then adjust individual skills from 0 to 100.</p></div></div><div class="skills roadmap-presets">${presetButtons}</div><div class="roadmap-slider-grid">${sliders}</div></section>
    <section class="roadmap-section"><div class="roadmap-section-heading"><div><h3>What to prove next</h3><p class="mut">Ranked by new sample postings that become Ready Now when skills are raised one at a time.</p></div></div>${leverageView}</section>
    <section class="roadmap-section"><div class="roadmap-section-heading"><div><h3>Explore all 23 roles</h3><p class="mut">Choose a category or role to see current fit and missing requirements.</p></div></div><div class="skills roadmap-filters">${ROADMAP_CATEGORIES.map(category=>roadmapButton(category,ROADMAP_UI.category===category,`setRoadmapCategory('${category}')`)).join('')}${roadmapButton('Top 8 picks',ROADMAP_UI.roleView==='Top 8 picks',"setRoadmapRoleView('Top 8 picks')")}${roadmapButton('All roles',ROADMAP_UI.roleView==='All roles',"setRoadmapRoleView('All roles')")}</div><div class="roadmap-role-grid">${roleCards}</div>${roleDetail}</section>
    <section class="roadmap-section"><div class="roadmap-section-heading"><div><h3>All 69 sample jobs</h3><p class="mut">Readiness is based on modeled skill thresholds, not employer screening or vacancy status.</p></div><b>${filteredJobs.length} shown</b></div><div class="skills roadmap-filters">${['All','Ready Now','Stretch','Not Yet'].map(filter=>roadmapButton(filter,ROADMAP_UI.jobFilter===filter,`setRoadmapJobFilter('${filter}')`)).join('')}</div><div class="roadmap-job-list">${jobCards||'<div class="empty">No sample jobs match these filters.</div>'}</div></section></div>`;
}

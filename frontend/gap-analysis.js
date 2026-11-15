'use strict';

const GAP_DEMO_LEVELS = {
  'Data analyst': {Excel:[55,50],SQL:[70,50],Python:[85,70],Tableau:[40,35],'Power BI':[20,20]},
  'AI/ML engineer': {Python:[75,65],ML:[65,55],AI:[60,50],Statistics:[55,50],SQL:[45,40]},
  'Python developer': {Python:[80,70],SQL:[55,45],OOP:[50,40],APIs:[35,30]},
  'Software developer': {DSA:[55,45],Java:[50,40],OOP:[55,45],SQL:[40,35]},
  'Frontend developer': {HTML:[65,55],CSS:[55,45],JavaScript:[45,35],React:[30,25]},
  'UI/UX designer': {Figma:[55,45],'Design Thinking':[50,40],Canva:[60,55],Communication:[55,50]}
};
const GAP_RESOURCES = {
  Excel:['Practice pivot tables, lookups and charts on a messy dataset.','https://support.microsoft.com/en-us/excel'],
  SQL:['Practice joins, GROUP BY and window functions on a public dataset.','https://sqlbolt.com/'],
  Python:['Build a small data-cleaning script and add tests and error handling.','https://docs.python.org/3/tutorial/'],
  Tableau:['Rebuild one public dashboard, then publish your own with filters.','https://www.tableau.com/learn/training'],
  'Power BI':['Import a dataset, model relationships and build a report with DAX measures.','https://learn.microsoft.com/en-us/training/powerplatform/power-bi/'],
  ML:['Train and evaluate a baseline model; compare it with a validation split.','https://scikit-learn.org/stable/tutorial/index.html'],
  AI:['Build a small application that calls and evaluates an AI model.','https://developers.google.com/machine-learning/crash-course'],
  Statistics:['Practice distributions, confidence intervals and hypothesis tests.','https://www.khanacademy.org/math/statistics-probability'],
  OOP:['Model a small domain with classes, composition and clear interfaces.','https://docs.python.org/3/tutorial/classes.html'],
  APIs:['Build a small REST client and handle errors, pagination and JSON.','https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Server-side/First_steps/Introduction'],
  Java:['Implement a small command-line app using collections and exceptions.','https://dev.java/learn/'],
  DSA:['Solve array, hash map, tree and graph problems; explain complexity.','https://www.geeksforgeeks.org/data-structures/'],
  HTML:['Build a semantic, accessible page with forms and landmarks.','https://developer.mozilla.org/en-US/docs/Learn/HTML'],
  CSS:['Recreate a responsive layout using flexbox, grid and media queries.','https://developer.mozilla.org/en-US/docs/Learn/CSS'],
  JavaScript:['Build an interactive page using modules, events and async fetch.','https://developer.mozilla.org/en-US/docs/Learn/JavaScript'],
  React:['Build a small component-based app with forms and API state.','https://react.dev/learn'],
  Figma:['Create and test a clickable prototype for one user journey.','https://help.figma.com/hc/en-us/categories/360002051613-Get-started'],
  'Design Thinking':['Interview users, map a problem and test a low-fidelity prototype.','https://dschool.stanford.edu/resources/getting-started-with-design-thinking'],
  Canva:['Create a small consistent set of social or presentation assets.','https://www.canva.com/designschool/'],
  Communication:['Practice a concise project walkthrough and get peer feedback.','https://www.toastmasters.org/resources/public-speaking-tips'],
  Analytics:['Define a metric, analyze a dataset and explain a decision it supports.','https://www.khanacademy.org/math/statistics-probability'],
  'Manual Testing':['Write test cases, report reproducible bugs and check edge cases.','https://www.atlassian.com/software/testing/guides'],
  Selenium:['Automate a stable browser flow with assertions and waits.','https://www.selenium.dev/documentation/'],
  AWS:['Deploy a small app and document its storage, compute and access choices.','https://aws.amazon.com/training/'],
  Azure:['Deploy a small app and document its service and access choices.','https://learn.microsoft.com/en-us/training/azure/'],
  Networking:['Practice reading DNS, HTTP and TCP traces for common failures.','https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview'],
  Security:['Review a small app for common web risks and document mitigations.','https://owasp.org/www-project-top-ten/'],
  'Digital Marketing':['Plan a small campaign and review conversion metrics.','https://skillshop.withgoogle.com/'],
  'Content Writing':['Write and revise a focused article using an editorial brief.','https://developers.google.com/search/docs/fundamentals/creating-helpful-content'],
  Recruiting:['Practice structured screening questions and candidate notes.','https://www.shrm.org/topics-tools/tools/toolkits/recruiting-internally-externally']
};
let GAP_SELECTED_ROLE = 'Data analyst';

function gapNormalizeName(name){return String(name||'').toLowerCase().replace(/[^a-z0-9]/g,'');}
function gapDefaultFor(skill,role){
  const found=Object.keys(S.evidence||{}).find(name=>gapNormalizeName(name)===gapNormalizeName(skill));
  const quizKey=Object.keys(S.quiz||{}).find(name=>gapNormalizeName(name)===gapNormalizeName(skill));
  const hasProfileData=Object.keys(S.evidence||{}).length>0||Object.keys(S.quiz||{}).length>0;
  if(hasProfileData)return {claimed:found?Number(S.evidence[found])||0:0,verified:quizKey?Number(S.quiz[quizKey])||0:0,demo:!quizKey,quizVerified:!!quizKey};
  const preset=GAP_DEMO_LEVELS[role]||GAP_DEMO_LEVELS['Data analyst'];
  const demo=preset[skill];
  if(demo)return {claimed:demo[0],verified:demo[1],demo:true,quizVerified:false};
  return {claimed:0,verified:0,demo:true,quizVerified:false};
}
function gapRole(){return ROADMAP_ROLES.find(role=>role.name===GAP_SELECTED_ROLE)||ROADMAP_ROLES.find(role=>role.name==='Data analyst');}
function gapValues(role){
  const saved=S.gapProfile?.[role.name]||{};
  return Object.entries(role.req).map(([skill,need])=>{
    const initial=gapDefaultFor(skill,role.name), value=saved[skill]||initial, scenario=value.scenario===true;
    const claimed=Math.min(100,Math.max(0,Number(value.claimed)||0)), verified=Math.min(100,Math.max(0,Number(value.verified)||0));
    return {skill,need,claimed,verified,demo:value.demo===true||initial.demo===true||scenario,quizVerified:initial.quizVerified&&!scenario,gap:Math.max(0,need-verified)};
  });
}
function gapSetRole(roleName){GAP_SELECTED_ROLE=roleName;render();}
function gapSetLevel(skill,kind,value){
  const role=gapRole(), current=gapValues(role).find(row=>row.skill===skill);
  const entry={claimed:current.claimed,verified:current.verified,demo:true,scenario:true,[kind]:Math.max(0,Math.min(100,Number(value)||0))};
  S.gapProfile={...(S.gapProfile||{}),[role.name]:{...(S.gapProfile?.[role.name]||{}),[skill]:entry}};
  persist();render();
}
function resetGapScenario(){const role=gapRole();if(S.gapProfile)delete S.gapProfile[role.name];persist();render();}
function gapPreview(input){const el=document.getElementById(input.dataset.output);if(el)el.textContent=`${input.value}`;}
function gapSafe(text){return typeof esc==='function'?esc(text):String(text).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));}
function renderSkillGapAnalysis(){
  const role=gapRole(), values=gapValues(role), met=values.filter(item=>item.verified>=item.need).length;
  const readiness=Math.round(values.reduce((total,item)=>total+Math.min(item.verified/item.need,1),0)/Math.max(values.length,1)*100);
  const gapRows=values.slice().sort((a,b)=>b.gap-a.gap);
  const largest=gapRows[0];
  const weeks=gapRows.reduce((total,item)=>total+Math.ceil(item.gap/10),0);
  const sample=values.some(item=>item.demo);
  const roles=ROADMAP_ROLES.map(candidate=>({candidate,fit:Math.round(Object.entries(candidate.req).reduce((sum,[skill,need])=>{
    const item=values.find(row=>gapNormalizeName(row.skill)===gapNormalizeName(skill));
    const fallback=gapDefaultFor(skill,candidate.name);
    return sum+Math.min((item?.verified??fallback.verified)/need,1);
  },0)/Object.keys(candidate.req).length*100)})).filter(row=>row.candidate.name!==role.name).sort((a,b)=>b.fit-a.fit).slice(0,4);
  const options=ROADMAP_ROLES.map(item=>`<option value="${gapSafe(item.name)}" ${item.name===role.name?'selected':''}>${gapSafe(item.name.replace(/\b\w/g,char=>char.toUpperCase()))}</option>`).join('');
  const controls=values.map(item=>`<div class="gap-level-item"><b>${gapSafe(item.skill)} <small>needs ${item.need}</small></b>
    <label>Claimed <input type="range" min="0" max="100" step="5" value="${item.claimed}" data-output="gap-claim-${roadmapSlug(item.skill)}" oninput="gapPreview(this)" onchange="gapSetLevel('${gapSafe(item.skill)}','claimed',this.value)"><output id="gap-claim-${roadmapSlug(item.skill)}">${item.claimed}</output></label>
    <label>${item.quizVerified?'Quiz result':'Scenario estimate'} <input type="range" min="0" max="100" step="5" value="${item.verified}" data-output="gap-verified-${roadmapSlug(item.skill)}" oninput="gapPreview(this)" onchange="gapSetLevel('${gapSafe(item.skill)}','verified',this.value)"><output id="gap-verified-${roadmapSlug(item.skill)}">${item.verified}</output></label></div>`).join('');
  const charts=gapRows.map(item=>`<div class="gap-chart-row"><b>${gapSafe(item.skill)}</b><div class="gap-track"><span class="gap-bar ${item.gap?'short':''}" style="width:${item.verified}%"></span><i class="gap-need" style="left:${item.need}%"></i><i class="gap-claim" style="left:${item.claimed}%"></i></div><div class="gap-status ${item.gap?'short':''}">${item.gap?`${item.gap} points short`:'Requirement met'}<small>${item.quizVerified?'Quiz result':'Scenario'} ${item.verified} · needs ${item.need}</small></div></div>`).join('');
  const plan=gapRows.filter(item=>item.gap>0).map((item,index)=>{const resource=GAP_RESOURCES[item.skill]||['Complete a small project that demonstrates this skill in context.','https://www.coursera.org/'];return `<article class="gap-plan-item"><div><b>${index+1}. ${gapSafe(item.skill)}</b><strong>${item.verified} to ${item.need} · about ${Math.ceil(item.gap/10)} wk</strong></div><p>${gapSafe(resource[0])} <a href="${resource[1]}" target="_blank" rel="noopener noreferrer">Study resource ↗</a></p></article>`;}).join('');
  const otherRoles=roles.map(({candidate,fit})=>`<div class="gap-other-role"><span>${gapSafe(candidate.name)}</span><b>${fit}%</b></div>`).join('');
  return `<div class="gap-analysis-page"><header class="gap-hero"><div><span class="gap-eyebrow">SKILLPROOF · CAREER READINESS</span><h2>Skill gap analysis</h2><p>Choose a target role, enter what your resume claims and what your quiz verified, and see the skills standing between you and that role.</p></div></header>
    <section class="gap-role-picker"><label for="gap-role-select">Target role</label><select id="gap-role-select" onchange="gapSetRole(this.value)">${options}</select><span class="gap-top-pick">Role profile</span></section>
    <section class="gap-summary"><article><b>${readiness}%</b><span>${sample?'Scenario readiness':'Quiz-based readiness'}</span></article><article><b>${met}/${values.length}</b><span>Skills at required level</span></article><article><b>${gapSafe(largest?.gap?largest.skill:'Ready')}</b><span>Biggest gap</span></article><article><b>${weeks}</b><span>Estimated weeks to close</span></article></section>
    <section class="gap-block"><h3>Your levels</h3><p>Claimed is what your resume suggests. Verified is your quiz result. Adjust the scenario sliders to explore how gaps change.${sample?' Sample starting values are illustrative until you complete a quiz.':''}</p><div class="gap-control-grid">${controls}</div><small class="gap-disclaimer">Scenario sliders are editable estimates and do not change quiz scores or certify proficiency.</small></section>
    <section class="gap-block"><h3>Gap breakdown</h3><div class="gap-chart">${charts}<div class="gap-legend"><span><i class="legend-verified"></i>Bar: quiz result or scenario</span><span><i class="legend-need"></i>Line: role requirement</span><span><i class="legend-claim"></i>Triangle: resume claim</span></div>${values.some(item=>item.quizVerified&&Math.abs(item.claimed-item.verified)>=15)?`<p class="gap-mismatch">Mismatch to review: ${values.filter(item=>item.quizVerified&&Math.abs(item.claimed-item.verified)>=15).map(item=>`${item.claimed>item.verified?'Overclaimed':'Underclaimed'} ${gapSafe(item.skill)} (claimed ${item.claimed}, quiz result ${item.verified})`).join('; ')}. A quiz comparison is a signal to review, not a final judgment.</p>`:''}</div><button class="btn o" type="button" onclick="resetGapScenario()">Reset to profile values</button></section>
    <section class="gap-block"><h3>Your action plan</h3><p>Largest gap first. Time assumes about 10 points of improvement per week of focused practice.</p><div class="gap-plan">${plan||'<p class="gap-all-met">You meet the modeled skill thresholds for this role. Check employer requirements and keep building evidence in projects.</p>'}</div></section>
    <section class="gap-block"><h3>Other roles this also helps</h3><p>Based on current scenario values against the modeled role requirements.</p><div class="gap-other-list">${otherRoles}</div><small class="gap-disclaimer">Role requirements, readiness, and week estimates are planning examples, not employer decisions or guaranteed learning timelines.</small></section>
  </div>`;
}

const gapStyles=document.createElement('style');
gapStyles.textContent=`
.gap-analysis-page{max-width:1150px;margin:0 auto;padding:4px 0 32px;color:#e8f0eb}.gap-hero{padding:22px 24px 14px;background:#0f1d18;border-radius:18px 18px 0 0}.gap-eyebrow{font-size:11px;letter-spacing:.16em;color:#65d6b4;font-weight:800}.gap-hero h2{font-size:34px;margin:7px 0;color:#e7f3ea}.gap-hero p,.gap-block>p{color:#9fb8ad;max-width:760px;line-height:1.55}.gap-role-picker{display:flex;align-items:center;gap:14px;padding:10px 24px 18px;background:#0f1d18}.gap-role-picker label{font-weight:700}.gap-role-picker select{min-width:min(320px,60vw);padding:11px 14px;background:#172a22;color:#e8f0eb;border:1px solid #29443a;border-radius:8px}.gap-top-pick{font-size:12px;border:1px solid #39bd96;color:#63d8b5;padding:5px 10px;border-radius:20px}.gap-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;padding:0 0 20px;background:#0f1d18}.gap-summary article{padding:15px;background:#142820;border:1px solid #203b30;border-radius:12px}.gap-summary b,.gap-summary span{display:block}.gap-summary b{font-size:28px;color:#57d5ae}.gap-summary span{font-size:12px;color:#9fb8ad}.gap-block{margin:16px 0;padding:20px;background:#11231c;border:1px solid #203b30;border-radius:15px}.gap-block h3{font-family:Georgia,serif;font-size:22px;margin:0 0 5px;color:#e5f0e7}.gap-block>p{margin:0 0 14px}.gap-control-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 20px}.gap-level-item{display:grid;grid-template-columns:1fr auto;gap:6px 10px;padding:11px 0;border-bottom:1px solid #233a30}.gap-level-item>b{grid-column:1/-1}.gap-level-item small{font-weight:400;color:#9fb8ad}.gap-level-item label{display:grid;grid-template-columns:62px minmax(70px,1fr) 28px;align-items:center;gap:7px;color:#9fb8ad;font-size:12px}.gap-level-item input{width:100%;accent-color:#50cba4}.gap-level-item output{color:#c6dfd3;text-align:right}.gap-disclaimer{display:block;color:#88a398;font-size:11px;margin-top:12px}.gap-chart{padding:8px 15px;background:#142820;border:1px solid #203b30;border-radius:12px}.gap-chart-row{display:grid;grid-template-columns:140px minmax(100px,1fr) 130px;align-items:center;gap:14px;padding:14px 0;border-bottom:1px solid #243b31}.gap-track{height:16px;position:relative;border-radius:5px;background:#263d33;overflow:visible}.gap-bar{position:absolute;inset:0 auto 0 0;background:#52cba4;border-radius:5px}.gap-bar.short{background:#f29a63}.gap-need{position:absolute;top:-4px;height:24px;width:2px;background:#e4eee8}.gap-claim{position:absolute;top:18px;width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-bottom:7px solid #6495ff;transform:translateX(-50%)}.gap-status{text-align:right;color:#58d5ae;font-weight:700;font-size:12px}.gap-status.short{color:#ff9a61}.gap-status small{display:block;color:#94aca1;font-weight:400;font-size:10px;margin-top:3px}.gap-legend{display:flex;gap:18px;flex-wrap:wrap;margin:15px 0 6px;color:#9fb8ad;font-size:11px}.gap-legend span{display:flex;align-items:center;gap:6px}.legend-verified{height:8px;width:15px;background:#52cba4;border-radius:4px}.legend-need{height:15px;width:2px;background:#e4eee8}.legend-claim{width:0;height:0;border-left:5px solid transparent;border-right:5px solid transparent;border-bottom:7px solid #6495ff}.gap-mismatch{color:#91adff!important;font-size:12px;margin-top:10px!important}.gap-plan{padding:12px 16px;background:#142820;border:1px solid #203b30;border-radius:12px}.gap-plan-item{padding:12px 0;border-bottom:1px solid #263d33}.gap-plan-item:last-child{border-bottom:0}.gap-plan-item>div{display:flex;justify-content:space-between;gap:12px}.gap-plan-item strong{font-size:12px;color:#ffac73}.gap-plan-item p{color:#9fb8ad;margin:6px 0 0;font-size:13px}.gap-plan-item a{display:inline-block;margin-left:8px;color:#72d5b9}.gap-all-met{color:#68d8b7}.gap-other-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.gap-other-role{display:flex;justify-content:space-between;padding:10px 12px;border:1px solid #29443a;border-radius:9px;background:#142820}.gap-other-role b{color:#62d4b2}
@media(max-width:760px){.gap-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.gap-control-grid{grid-template-columns:1fr}.gap-chart-row{grid-template-columns:90px minmax(70px,1fr);gap:10px}.gap-status{grid-column:2;text-align:left}.gap-role-picker{flex-wrap:wrap;padding-left:14px;padding-right:14px}.gap-hero,.gap-block{padding:16px}.gap-other-list{grid-template-columns:1fr}}
`;
document.head.appendChild(gapStyles);

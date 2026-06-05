/* EACHS — application logic ---------------------------------------------- */
/* Live backend contract preserved:
     GET  /logs            -> array of evaluation log objects
     GET  /stats           -> { global, by_task_type }
     GET  /stats/kappa     -> { quadratic_weighted_kappa, interpretation, n_evaluated } | { message }
     POST /review/{logId}  -> { final_score, decision, prof_comment }
   If the backend is unreachable, a demo dataset is used so the UI stays legible. */

let allLogs = [], curStats = {}, curKappa = {};
let currentFilter = 'all';
let modLogId = null, modMax = 100;
let rejectLogId = null;
let selectedDevoirKey = null;
let lastLogCount = 0, lastLogTimestamp = '';
let demoMode = false;

const TYPE_LABEL = {qcm:'QCM', short_answer:'Réponse courte', essay:'Rédaction', formal:'Exercice formel'};
const TYPE_TAG   = {qcm:'tag-qcm', short_answer:'tag-short', essay:'tag-essay', formal:'tag-formal'};
const TYPE_COLOR = {qcm:'--emerald', short_answer:'--teal', essay:'--amber', formal:'--violet'};

const nf = n => (n==null||isNaN(n)) ? '—' : Number(n).toLocaleString('fr-FR');
function studentLabel(l){ return (l.student_name && l.student_name.trim()) ? l.student_name : 'Étudiant ' + l.student_id; }
function getOpenCards(){ const s=new Set(); document.querySelectorAll('.etudiant-card.open').forEach(c=>s.add(c.id.replace('card-',''))); return s; }
function initials(name){ const p=name.replace(/^(Pr\.|Dr\.|M\.|Mme)\s*/,'').trim().split(/\s+/); return ((p[0]||'')[0]||'')+((p[1]||'')[0]||'').toUpperCase(); }
function cvar(n){ return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }

/* ───────── Theme ───────── */
const SUN='<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="8" cy="8" r="3.2"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.4 1.4M11.6 11.6L13 13M13 3l-1.4 1.4M4.4 11.6L3 13"/></svg>';
const MOON='<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M13.5 9.5A5.5 5.5 0 016.5 2.5 5.5 5.5 0 1013.5 9.5z"/></svg>';
function applyTheme(t){
  document.documentElement.setAttribute('data-theme', t);
  document.getElementById('theme-btn').innerHTML = t==='dark' ? SUN : MOON;
  try{ localStorage.setItem('eachs-theme', t); }catch(e){}
}
function toggleTheme(){
  const cur = document.documentElement.getAttribute('data-theme');
  applyTheme(cur==='dark'?'light':'dark');
  rerenderCharts();
}
(function(){ let t='light'; try{ t=localStorage.getItem('eachs-theme')||'light'; }catch(e){} applyTheme(t); })();

/* ───────── Navigation ───────── */
function showPage(p, el){
  ['dashboard','devoirs','analytics','logs'].forEach(id=>{
    document.getElementById('page-'+id).style.display = id===p?'':'none';
  });
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
  if(el) el.classList.add('active');
}

/* ───────── Data loading ───────── */
async function fetchLive(){
  const [lr,sr,kr] = await Promise.all([fetch('/logs'),fetch('/stats'),fetch('/stats/kappa')]);
  if(!lr.ok||!sr.ok||!kr.ok) throw new Error('endpoint error');
  return { logs: await lr.json(), stats: await sr.json(), kappa: await kr.json() };
}

async function loadAll(){
  let data;
  try{ data = await fetchLive(); demoMode=false; }
  catch(e){ data = getDemo(); demoMode=true; }

  const newLogs = Array.isArray(data.logs) ? data.logs : [];
  const newCount = newLogs.length;
  const newTs = newCount>0 ? newLogs[newLogs.length-1].timestamp : '';
  if(lastLogCount>0 && newCount>lastLogCount){
    const newLog=newLogs[newLogs.length-1];
    showToast('Nouvelle évaluation disponible', newLog?newLog.log_id:null);
  } else if(lastLogTimestamp && newTs!==lastLogTimestamp && newCount===lastLogCount){
    const updLog=newLogs.find(l=>l.timestamp===newTs);
    showToast('Évaluation mise à jour', updLog?updLog.log_id:null);
  }
  lastLogCount=newCount; lastLogTimestamp=newTs;

  allLogs = newLogs;
  curStats = data.stats || {};
  curKappa = data.kappa || {};

  document.getElementById('demo-pill').style.display = demoMode ? '' : 'none';
  document.getElementById('avatar').textContent = 'AI';

  renderDashboard(curStats, curKappa);
  renderDevoirsList(allLogs);
  renderAnalytics(curStats, curKappa);
  renderLogs(allLogs);

  const pending = allLogs.filter(l=>l.requires_human_review && !l.human_decision).length;
  document.getElementById('pending-count').textContent = pending;
  document.getElementById('footer-time').textContent = new Date().toLocaleTimeString('fr-FR');
  if(selectedDevoirKey) renderEtudiants(selectedDevoirKey);
}

function rerenderCharts(){ if(allLogs.length||curStats.global){ renderDashboard(curStats,curKappa); renderAnalytics(curStats,curKappa); } }

/* ───────── Derived metrics ───────── */
function recentWeek(logs){
  const wk = Date.now()-7*864e5;
  return logs.filter(l=>{ const t=new Date(l.timestamp).getTime(); return !isNaN(t)&&t>=wk; }).length;
}
function deriveTrend(logs){
  const rev = logs.filter(l=>l.human_final_score!=null && l.max_score>0)
    .sort((a,b)=> new Date(a.reviewed_at||a.timestamp) - new Date(b.reviewed_at||b.timestamp));
  if(rev.length<3) return null;
  const win = Math.max(3, Math.round(rev.length/6));
  const conc=[], val=[];
  for(let i=0;i<rev.length;i++){
    const s = rev.slice(Math.max(0,i-win+1), i+1);
    conc.push(s.reduce((a,l)=>a+(1-Math.abs(l.proposed_score-l.human_final_score)/l.max_score),0)/s.length);
    val.push(s.filter(l=>l.human_decision==='validated').length/s.length);
  }
  return { conc: sample(conc,14), val: sample(val,14) };
}
function sample(arr,n){ if(arr.length<=n) return arr; const out=[]; for(let i=0;i<n;i++) out.push(arr[Math.round(i*(arr.length-1)/(n-1))]); return out; }
function scoreBuckets(logs){
  const b = Array.from({length:10},(_,i)=>({l:(i*10)+'', v:0}));
  logs.forEach(l=>{ if(l.max_score>0){ const s=(l.human_final_score!=null?l.human_final_score:l.proposed_score); let idx=Math.min(9,Math.floor(s/l.max_score*10)); if(idx>=0) b[idx].v++; }});
  return b;
}

/* ───────── Vue d'ensemble ───────── */
function renderDashboard(s, k){
  document.getElementById('dash-greeting').textContent = 'Tableau de bord EACHS';
  document.getElementById('dash-sub').textContent = 'Supervision des évaluations assistées par IA · ' +
    new Date().toLocaleDateString('fr-FR',{weekday:'long',day:'numeric',month:'long',year:'numeric'});

  const g = s.global;
  const total = g? g.total_evaluations : 0;
  const validated = g? g.validated : 0;
  const pctValidated = total? Math.round(validated/total*100) : 0;
  const recent = recentWeek(allLogs);
  const kpis = [
    {cls:'violet', label:'Total évaluations', value: g?nf(g.total_evaluations):'—', foot: recent?('+'+recent+' cette semaine'):'toutes tâches', icon:IC.grid},
    {cls:'coral', label:'En attente', value: g?nf(g.pending_review):'—', foot:'à réviser maintenant', icon:IC.doc},
    {cls:'emerald', label:'Validées', value: g?nf(validated):'—', foot: total?(pctValidated+'% sans modification'):'sans modification', icon:IC.check},
    {cls:'amber', label:'Taux modification', value: g&&g.modification_rate_pct!=null?(g.modification_rate_pct+'%'):'—', foot:'humain ≠ IA', icon:IC.edit},
  ];
  document.getElementById('kpi-row').innerHTML = kpis.map(t=>`
    <div class="kpi ${t.cls}">
      <div class="kpi-top"><div class="kpi-label">${t.label}</div><div class="kpi-chip">${t.icon}</div></div>
      <div class="kpi-value">${t.value}</div>
      <div class="kpi-foot">${t.foot}</div>
    </div>`).join('');

  // trend
  const tr = deriveTrend(allLogs);
  const tc = document.getElementById('trend-chart');
  if(tr){ tc.innerHTML = lineChart([
      {vals:tr.conc, color:cvar('--violet'), fill:true},
      {vals:tr.val, color:cvar('--emerald')}
    ], 640, 200, {ymin:0.3, ymax:1}); }
  else { tc.innerHTML = `<div class="empty-state" style="padding:60px 0">Pas encore assez de copies révisées pour tracer la tendance.</div>`; }

  // kappa donut
  const dn = document.getElementById('kappa-donut');
  if(k && k.message){ dn.innerHTML = donut(0, cvar('--faint'), 168, 15, {label:'N/A', labelColor:cvar('--faint')});
    document.getElementById('kappa-interp').textContent = k.message;
    document.getElementById('kappa-grade').textContent='—';
    document.getElementById('kappa-n').textContent='';
  } else if(k && k.quadratic_weighted_kappa!=null){
    const v=k.quadratic_weighted_kappa;
    const col = v>=0.8?cvar('--emerald') : v>=0.6?cvar('--amber') : cvar('--coral');
    dn.innerHTML = donut(v*100, col, 168, 15, {label:v.toFixed(3), labelColor:col});
    document.getElementById('kappa-grade').textContent = grade(v);
    document.getElementById('kappa-interp').textContent = k.interpretation || '';
    document.getElementById('kappa-n').textContent = (k.n_evaluated!=null? nf(k.n_evaluated)+' paires évaluées':'');
  } else { dn.innerHTML = donut(0, cvar('--faint'), 168, 15, {label:'—'}); }

  // task grid
  const bt = s.by_task_type||{};
  document.getElementById('task-grid-dash').innerHTML = Object.keys(TYPE_LABEL).map(t=>{
    const d=bt[t]||{}, col=cvar(TYPE_COLOR[t]);
    const pct = d.avg_ai_score_pct!=null ? d.avg_ai_score_pct : 0;
    return `<div class="task-cell">
      <div class="tc-label">${TYPE_LABEL[t]}</div>
      <div class="tc-score" style="color:${col}">${d.avg_ai_score_pct!=null?d.avg_ai_score_pct+'%':'—'}</div>
      <div class="barline"><div style="width:${pct}%;background:${col}"></div></div>
      <div class="tc-count">${nf(d.total_evaluations||0)} évaluation${(d.total_evaluations||0)>1?'s':''}</div>
    </div>`;
  }).join('');
}
function grade(v){ return v>=0.8?'quasi parfait' : v>=0.6?'substantiel' : v>=0.4?'modéré' : 'faible'; }

/* ───────── Devoirs ───────── */
function groupByDevoir(logs){
  const g={};
  logs.forEach(l=>{
    const course=l.course_name||'Cours inconnu', devoir=l.assignment_name||l.assignment_id;
    const key=`${course}|||${devoir}|||${l.assignment_id}`;
    if(!g[key]) g[key]={course,devoir,assignment_id:l.assignment_id,logs:[]};
    g[key].logs.push(l);
  });
  return g;
}
function renderDevoirsList(logs){
  const groups=groupByDevoir(logs), byCourse={};
  Object.entries(groups).forEach(([key,g])=>{ (byCourse[g.course]=byCourse[g.course]||[]).push({key,...g}); });
  let html='';
  Object.entries(byCourse).forEach(([course,devoirs])=>{
    html+=`<div class="course-group"><div class="course-label">${course}</div>`;
    devoirs.forEach(d=>{
      const pending=d.logs.filter(l=>l.requires_human_review&&!l.human_decision).length;
      const manual=d.logs.filter(l=>l.human_decision==='rejected').length;
      const total=d.logs.length, active=selectedDevoirKey===d.key;
      let badge = pending>0 ? `<span class="badge-count badge-pending">${pending} en attente</span>`
        : manual>0 ? `<span class="badge-count badge-manual">${manual} manuel</span>`
        : `<span class="badge-count badge-done">${total} corrigé${total>1?'s':''}</span>`;
      html+=`<div class="devoir-item ${active?'active':''}" onclick="selectDevoir('${esc(d.key)}')">
        <div style="min-width:0;flex:1"><div class="devoir-name">${d.devoir}</div><div class="devoir-meta">${total} soumission${total>1?'s':''}</div></div>${badge}
      </div>`;
    });
    html+='</div>';
  });
  document.getElementById('devoirs-list-content').innerHTML = html || '<div class="empty-state">Aucun devoir</div>';
}
function selectDevoir(key){ selectedDevoirKey=key; renderDevoirsList(allLogs); renderEtudiants(key); }

function renderEtudiants(key){
  const g=groupByDevoir(allLogs)[key]; const panel=document.getElementById('etudiants-panel'); if(!g) return;
  const wasOpen=getOpenCards();
  const pending=g.logs.filter(l=>l.requires_human_review&&!l.human_decision).length;
  const manual=g.logs.filter(l=>l.human_decision==='rejected').length;
  let html=`<div class="etudiants-panel-header">
    <div class="etudiants-panel-title">${g.devoir}</div>
    <div class="etudiants-panel-sub">${g.course} · ${g.logs.length} soumission${g.logs.length>1?'s':''} · ${pending} en attente${manual>0?' · '+manual+' à corriger manuellement':''}</div>
  </div><div class="etudiants-list">`;

  if(!g.logs.length){ html+='<div class="empty-state">Aucune soumission</div>'; }
  else{
    [...g.logs].reverse().forEach(l=>{
      const pct=l.max_score>0?Math.round(l.proposed_score/l.max_score*100):0;
      const bc=pct>=70?cvar('--emerald'):pct>=40?cvar('--amber'):cvar('--coral');
      const dispScore=l.human_final_score!=null?l.human_final_score:l.proposed_score;
      const dispPct=l.max_score>0?Math.round(dispScore/l.max_score*100):0;
      const dispCol=dispPct>=70?cvar('--emerald'):dispPct>=40?cvar('--amber'):cvar('--coral');

      let sBadge='tag-auto',sLabel='Automatique',cardClass='',strip=cvar('--border-2');
      if(l.human_decision==='validated'){sBadge='tag-validated';sLabel='Validé';strip=cvar('--emerald');}
      else if(l.human_decision==='modified'){sBadge='tag-modified';sLabel='Modifié';strip=cvar('--amber');}
      else if(l.human_decision==='rejected'){sBadge='tag-rejected';sLabel='Correction manuelle';cardClass='manual-correction';strip=cvar('--amber');}
      else if(l.requires_human_review){sBadge='tag-pending';sLabel='En attente';cardClass='needs-action';strip=cvar('--coral');}

      const needsAct=l.requires_human_review&&!l.human_decision;
      const dt=new Date(l.timestamp).toLocaleDateString('fr-FR',{day:'2-digit',month:'long',hour:'2-digit',minute:'2-digit'});
      const preview=(l.student_answer_preview||l.student_answer||'').substring(0,400);
      const feedback=(l.feedback||'').substring(0,500);
      const name=studentLabel(l), context=`${name} — ${g.devoir}`;

      let decision='';
      if(l.human_decision==='validated') decision=`<div class="decision-box validated">✓ Validé par l'enseignant${l.human_comment?' — '+l.human_comment:''}<br><small>Score final : ${l.human_final_score}/${l.max_score} · ${fmtDate(l.reviewed_at)}</small></div>`;
      else if(l.human_decision==='modified') decision=`<div class="decision-box modified">✎ Score modifié : ${l.proposed_score} → ${l.human_final_score}/${l.max_score}${l.human_comment?'<br>'+l.human_comment:''}<br><small>${fmtDate(l.reviewed_at)}</small></div>`;
      else if(l.human_decision==='rejected') decision=`<div class="decision-box rejected">⚠ Correction manuelle requise${l.human_comment?'<br>'+l.human_comment:''}<br><small>Note provisoire 0 dans Moodle · ${fmtDate(l.reviewed_at)}</small></div>`;

      html+=`<div class="etudiant-card ${cardClass} ${needsAct?'open':''}" id="card-${l.log_id}">
        <div class="etudiant-strip" style="background:${strip}"></div>
        <div class="etudiant-card-head" onclick="toggleCard('${esc(l.log_id)}')">
          <div class="etudiant-ident">
            <div class="etu-ava">${initials(name)}</div>
            <div style="min-width:0">
              <div class="etudiant-name">${name}</div>
              <div class="etudiant-meta"><span class="tag ${TYPE_TAG[l.task_type]||''} nodot">${TYPE_LABEL[l.task_type]||l.task_type}</span>${dt}</div>
            </div>
          </div>
          <div class="etudiant-score">
            <div><div class="score-big" style="color:${dispCol}">${dispScore}<small>/${l.max_score}</small></div>
            <div style="margin-top:5px;text-align:right"><span class="tag ${sBadge}">${sLabel}</span></div></div>
            <svg class="chev" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3.5 6L8 10.5 12.5 6"/></svg>
          </div>
        </div>
        <div class="etudiant-card-body">
          <div class="score-bar-wrap"><div class="lbl">Score IA</div><div class="bar-bg"><div class="bar-fill" style="width:${pct}%;background:${bc}"></div></div><span class="mono" style="color:var(--faint);font-size:11.5px">${l.proposed_score}/${l.max_score}</span></div>
          <div class="section-label">Question posée</div>
          <div class="content-box">${l.question||'—'}</div>
          <div class="section-label">Réponse de l'étudiant</div>
          <div class="content-box">${preview||'<em style="color:var(--faint)">Soumission fichier — voir Moodle</em>'}</div>
          <div class="section-label">Feedback proposé par l'IA</div>
          <div class="feedback-box">${feedback||'—'}</div>
          <div class="section-label">Backend IA</div>
          <div style="font-size:12px;color:var(--faint);font-family:'JetBrains Mono',monospace;padding:4px 0">${l.backend||'—'} · version prompt ${l.prompt_version||'—'}</div>
          ${decision}
          ${needsAct?`<div class="action-row">
            <button class="act-btn act-btn-ok" onclick="quickValidate('${esc(l.log_id)}',${l.proposed_score},${l.max_score})">✓ Valider ${l.proposed_score}/${l.max_score}</button>
            <button class="act-btn act-btn-mod" onclick="openMod('${esc(l.log_id)}',${l.proposed_score},${l.max_score},'${esc(context)}')">✎ Modifier</button>
            <button class="act-btn act-btn-no" onclick="openReject('${esc(l.log_id)}','${esc(context)}')">✕ Rejeter</button>
          </div>`:''}
        </div>
      </div>`;
    });
  }
  html+='</div>';
  panel.innerHTML=html;
  // Restaurer les cartes ouvertes avant le refresh
  wasOpen.forEach(id=>{ const c=document.getElementById('card-'+id); if(c) c.classList.add('open'); });
}
function toggleCard(id){ const c=document.getElementById('card-'+id); if(c) c.classList.toggle('open'); }

/* ───────── Analytiques ───────── */
function renderAnalytics(s, k){
  if(!s || !s.by_task_type){ document.getElementById('analytics-content').innerHTML='<div class="loading-state">Aucune donnée disponible.</div>'; return; }
  const bt=s.by_task_type, types=Object.keys(TYPE_LABEL);
  const g=s.global||{};

  // kappa block
  let kappaBlock;
  if(k && k.message){ kappaBlock=`<div class="empty-state" style="padding:20px 0">${k.message}</div>`; }
  else if(k && k.quadratic_weighted_kappa!=null){
    const v=k.quadratic_weighted_kappa, col=v>=0.8?cvar('--emerald'):v>=0.6?cvar('--amber'):cvar('--coral');
    kappaBlock=`<div style="display:flex;align-items:center;gap:22px;flex-wrap:wrap">
      ${donut(v*100,col,130,13,{label:v.toFixed(2),labelColor:col})}
      <div style="flex:1;min-width:200px">
        <div class="mono" style="font-size:44px;font-weight:700;letter-spacing:-2px;color:${col};line-height:1">${v.toFixed(4)}</div>
        <div style="font-size:14px;font-weight:700;margin-top:8px">${k.interpretation||grade(v)}</div>
        <div class="card-meta" style="margin-top:8px">${nf(k.n_evaluated)} paires évaluées · échelle : &lt;0,4 faible · 0,4–0,6 modéré · 0,6–0,8 substantiel · &gt;0,8 quasi parfait</div>
      </div></div>`;
  } else kappaBlock='<div class="empty-state">—</div>';

  // decision distribution
  const decData=[
    {l:'Validé', v:g.validated||0, color:cvar('--emerald')},
    {l:'Modifié', v:countDec('modified'), color:cvar('--amber')},
    {l:'Rejeté', v:countDec('rejected'), color:cvar('--coral')},
    {l:'En attente', v:allLogs.filter(x=>x.requires_human_review&&!x.human_decision).length, color:cvar('--violet')},
  ];
  // IA vs Humain
  const groups=types.map(t=>({l:TYPE_LABEL[t].split(' ')[0], vals:[ bt[t]&&bt[t].avg_ai_score_pct!=null?bt[t].avg_ai_score_pct:0, bt[t]&&bt[t].avg_human_score_pct!=null?bt[t].avg_human_score_pct:0 ]}));

  const rows=types.map(t=>{const d=bt[t]||{};return `<tr>
    <td><span class="tag ${TYPE_TAG[t]} nodot">${TYPE_LABEL[t]}</span></td>
    <td class="perf-num">${nf(d.total_evaluations||0)}</td>
    <td class="perf-num">${nf(d.requires_human_review||0)}</td>
    <td class="perf-num">${d.avg_ai_score_pct!=null?d.avg_ai_score_pct+'%':'—'}</td>
    <td class="perf-num">${d.avg_human_score_pct!=null?d.avg_human_score_pct+'%':'—'}</td>
    <td class="perf-num" style="color:var(--amber)">${d.modification_rate_pct!=null?d.modification_rate_pct+'%':'—'}</td>
    <td class="perf-num" style="color:var(--emerald)">${nf(d.validated||0)}</td>
    <td class="perf-num" style="color:var(--amber)">${nf(d.modified||0)}</td>
    <td class="perf-num" style="color:var(--coral)">${nf(d.rejected||0)}</td>
  </tr>`}).join('');

  document.getElementById('analytics-content').innerHTML=`
    <div class="card card-pad" style="margin-bottom:16px">
      <div class="card-head"><span class="card-title">Kappa de Cohen pondéré quadratique</span><span class="card-meta">accord IA / humain</span></div>
      <div style="margin-top:14px">${kappaBlock}</div>
    </div>
    <div class="grid g-3" style="margin-bottom:16px">
      <div class="card card-pad"><div class="card-head"><span class="card-title">Distribution des décisions</span></div><div style="margin-top:8px">${vbars(decData,300,180)}</div></div>
      <div class="card card-pad"><div class="card-head"><span class="card-title">Distribution des scores</span><span class="card-meta">en %</span></div><div style="margin-top:8px">${histogram(scoreBuckets(allLogs),300,180,cvar('--violet'))}</div></div>
      <div class="card card-pad"><div class="card-head"><span class="card-title">Score moyen IA vs humain</span></div><div style="margin-top:8px">${groupedBars(groups,300,180,{max:100})}</div>
        <div class="legend"><span><i style="background:var(--violet)"></i>IA</span><span><i style="background:var(--emerald)"></i>Humain</span></div></div>
    </div>
    <div class="table-card">
      <div class="table-toolbar"><span class="card-title">Performance par type de tâche</span></div>
      <div class="table-scroll"><table>
        <thead><tr><th>Type</th><th>Total</th><th>Révision requise</th><th>Score moy. IA</th><th>Score moy. humain</th><th>Taux modif.</th><th>Validées</th><th>Modifiées</th><th>Rejetées</th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
    </div>`;
}
function countDec(d){ return allLogs.filter(l=>l.human_decision===d).length; }

/* ───────── Journal d'audit ───────── */
function renderLogs(logs){
  const filtered=logs.filter(l=>{
    if(currentFilter==='all') return true;
    if(currentFilter==='pending') return l.requires_human_review && !l.human_decision;
    if(currentFilter==='auto') return !l.requires_human_review;
    return l.human_decision===currentFilter;
  });
  const tb=document.getElementById('logs-tbody');
  if(!filtered.length){ tb.innerHTML=`<tr><td colspan="10" class="empty-state">Aucun enregistrement</td></tr>`; return; }
  const lbl={qcm:'QCM',short_answer:'Court',essay:'Rédaction',formal:'Formel'};
  tb.innerHTML=[...filtered].reverse().map(l=>{
    let sBadge='tag-auto',sLabel='Auto (IA)';
    if(l.human_decision==='validated'){sBadge='tag-validated';sLabel='Validé';}
    else if(l.human_decision==='modified'){sBadge='tag-modified';sLabel='Modifié';}
    else if(l.human_decision==='rejected'){sBadge='tag-rejected';sLabel='Rejeté';}
    else if(l.requires_human_review){sBadge='tag-pending';sLabel='En attente';}
    const dt=new Date(l.timestamp).toLocaleDateString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
    const final=l.human_final_score!=null?`<span class="mono">${l.human_final_score}/${l.max_score}</span>`:`<span class="cell-muted">—</span>`;
    const decidedBy=l.human_decision?'Enseignant':(l.requires_human_review?'—':'IA auto');
    const backend=(l.backend||'').toLowerCase();
    const bl=backend.includes('gemini')?'Gemini':backend.includes('mistral')?'Mistral':(l.backend||'—');
    return `<tr>
      <td><span class="truncate">${l.course_name||'—'}</span></td>
      <td><span class="truncate">${l.assignment_name||l.assignment_id}</span></td>
      <td style="font-weight:600">${studentLabel(l)}</td>
      <td><span class="tag ${TYPE_TAG[l.task_type]||''} nodot">${lbl[l.task_type]||l.task_type}</span></td>
      <td class="mono">${l.proposed_score}/${l.max_score}</td>
      <td><span class="tag ${sBadge}">${sLabel}</span></td>
      <td>${final}</td>
      <td class="cell-muted">${decidedBy}</td>
      <td class="cell-muted">${bl}</td>
      <td class="mono cell-muted">${dt}</td>
    </tr>`;
  }).join('');
}
function setFilter(f, btn){ currentFilter=f; document.querySelectorAll('.filter-pill').forEach(b=>b.classList.remove('active')); btn.classList.add('active'); renderLogs(allLogs); }

/* ───────── Review actions (HITL) ───────── */
async function postReview(logId, body){
  if(demoMode){ applyDemoReview(logId, body); return; }
  const r=await fetch('/review/'+logId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!r.ok) throw new Error('HTTP '+r.status);
}
async function quickValidate(logId, score){
  try{ await postReview(logId,{final_score:score,decision:'validated',prof_comment:''}); showToast('✓ Score validé et envoyé à Moodle'); await loadAll(); }
  catch(e){ showToast('Erreur : '+e.message); }
}
function openMod(logId, score, max, context){
  modLogId=logId; modMax=max;
  document.getElementById('mod-context').textContent=context;
  document.getElementById('mod-score').value=score;
  document.getElementById('mod-score').max=max;
  document.getElementById('mod-max-label').textContent=max;
  document.getElementById('mod-comment').value='';
  document.getElementById('overlay-mod').classList.add('open');
}
async function submitMod(){
  const score=parseFloat(document.getElementById('mod-score').value);
  const comment=document.getElementById('mod-comment').value.trim();
  if(isNaN(score)||score<0||score>modMax){ showToast('Score invalide (0–'+modMax+')'); return; }
  try{ await postReview(modLogId,{final_score:score,decision:'modified',prof_comment:comment}); closeModals(); showToast('✎ Score modifié et envoyé à Moodle'); await loadAll(); }
  catch(e){ showToast('Erreur : '+e.message); }
}
function openReject(logId, context){
  rejectLogId=logId;
  document.getElementById('reject-context').textContent=context;
  document.getElementById('reject-comment').value='';
  document.getElementById('overlay-reject').classList.add('open');
}
async function submitReject(){
  const comment=document.getElementById('reject-comment').value.trim();
  try{ await postReview(rejectLogId,{final_score:0,decision:'rejected',prof_comment:comment}); closeModals(); showToast('⚠ Évaluation rejetée — note provisoire 0 dans Moodle'); await loadAll(); }
  catch(e){ showToast('Erreur : '+e.message); }
}
function closeModals(){ document.getElementById('overlay-mod').classList.remove('open'); document.getElementById('overlay-reject').classList.remove('open'); modLogId=null; rejectLogId=null; }
document.addEventListener('keydown',e=>{ if(e.key==='Escape') closeModals(); });
document.querySelectorAll('.overlay').forEach(o=>o.addEventListener('click',e=>{ if(e.target===o) closeModals(); }));

/* ───────── Export CSV ───────── */
function exportCsv(){
  const cols=['log_id','course_name','assignment_name','student_name','task_type','proposed_score','max_score','requires_human_review','human_decision','human_final_score','backend','timestamp'];
  const head=cols.join(',');
  const rows=allLogs.map(l=>cols.map(c=>{ let v=l[c]; if(v==null)v=''; v=String(v).replace(/"/g,'""'); return /[",\n;]/.test(v)?`"${v}"`:v; }).join(','));
  const blob=new Blob([head+'\n'+rows.join('\n')],{type:'text/csv;charset=utf-8'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='eachs-journal-audit.csv'; a.click(); URL.revokeObjectURL(a.href);
  showToast('Journal exporté en CSV');
}

/* ───────── Toast & helpers ───────── */
function showToast(msg, logId){
  const t=document.getElementById('toast');
  t.textContent = logId ? msg + ' — Cliquer pour voir' : msg;
  t.classList.add('show');
  t.style.cursor = logId ? 'pointer' : 'default';
  t.onclick = logId ? ()=>{
    t.classList.remove('show');
    const log=allLogs.find(l=>l.log_id===logId);
    if(!log) return;
    const key=`${log.course_name}|||${log.assignment_name}|||${log.assignment_id}`;
    document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
    document.querySelectorAll('.nav-item')[1].classList.add('active');
    showPage('devoirs', document.querySelectorAll('.nav-item')[1]);
    selectDevoir(key);
    setTimeout(()=>{
      const card=document.getElementById('card-'+logId);
      if(card){ card.classList.add('open'); card.scrollIntoView({behavior:'smooth',block:'center'}); }
    }, 150);
  } : null;
  clearTimeout(t._t);
  t._t=setTimeout(()=>t.classList.remove('show'),4000);
}
function esc(s){ return String(s).replace(/\\/g,'\\\\').replace(/'/g,"\\'"); }
function fmtDate(s){ if(!s) return ''; const d=new Date(s); return isNaN(d)?'':d.toLocaleDateString('fr-FR'); }

const IC={
  grid:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="1.5" y="1.5" width="5.5" height="5.5" rx="1.6"/><rect x="9" y="1.5" width="5.5" height="5.5" rx="1.6"/><rect x="1.5" y="9" width="5.5" height="5.5" rx="1.6"/><rect x="9" y="9" width="5.5" height="5.5" rx="1.6"/></svg>',
  doc:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 1.5h6l3 3v10H4z"/><path d="M9.5 1.5V5h3.5M6 8.5h4M6 11h3"/></svg>',
  check:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M8 1.5L2.5 4v4c0 3.5 2.5 5.5 5.5 6.5 3-1 5.5-3 5.5-6.5V4z"/><path d="M5.8 8l1.6 1.6L10.4 6.5"/></svg>',
  edit:'<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M11 2.5l2.5 2.5L6 12.5 3 13l.5-3z"/></svg>',
};

/* ───────── Boot ───────── */
loadAll();
setInterval(loadAll, 10000);
/* EACHS — demo dataset (used only when the live backend is unreachable) --- */
(function(){
  let cache = null;

  // deterministic RNG
  let _s = 20260605;
  function rnd(){ _s = (_s*1664525 + 1013904223) % 4294967296; return _s/4294967296; }
  function pick(a){ return a[Math.floor(rnd()*a.length)]; }
  function ri(a,b){ return a + Math.floor(rnd()*(b-a+1)); }

  const STUDENTS = ['Léa Moreau','Hugo Bernard','Camille Dubois','Lucas Martin','Manon Petit','Théo Rousseau','Chloé Lefebvre','Nathan Garcia','Emma Laurent','Louis Faure','Sarah Mercier','Adam Bonnet','Inès Girard','Gabriel Roy','Jade Fontaine','Maxime Vincent','Alice Robin','Noah Caron','Zoé Lemoine','Raphaël Aubert'];

  const ASSIGNMENTS = [
    {course:'L2 Informatique', name:'TP3 : Récursivité', type:'short_answer', max:20,
      q:"Expliquez le principe de la récursivité et donnez la condition d'arrêt de la fonction factorielle.",
      a:"La récursivité consiste pour une fonction à s'appeler elle-même. Pour factorielle, la condition d'arrêt est n = 0 qui renvoie 1, sinon on renvoie n * fact(n-1).",
      fb:"Bonne définition et condition d'arrêt correcte. Aurait pu préciser le risque de débordement de pile pour de grandes valeurs."},
    {course:'L2 Informatique', name:'Examen partiel : Algorithmes', type:'essay', max:100,
      q:"Comparez la complexité du tri rapide et du tri fusion dans le pire des cas. Justifiez.",
      a:"Le tri fusion garantit O(n log n) dans tous les cas grâce au découpage équilibré. Le tri rapide est en O(n²) dans le pire cas (pivot mal choisi) mais O(n log n) en moyenne, avec une meilleure constante en pratique.",
      fb:"Analyse solide des deux algorithmes. La justification du pire cas du tri rapide est correcte. Manque une discussion sur la stabilité et l'occupation mémoire."},
    {course:'L1 Mathématiques', name:'QCM chapitre 4 : dérivées', type:'qcm', max:10,
      q:"Quelle est la dérivée de f(x) = x³ − 2x ?",
      a:"f'(x) = 3x² − 2",
      fb:"Réponse exacte."},
    {course:'L1 Mathématiques', name:'DM5 : intégrales', type:'formal', max:20,
      q:"Calculez l'intégrale de 0 à 1 de (2x + 1) dx.",
      a:"∫(2x+1)dx = x² + x ; évaluée entre 0 et 1 = (1+1) − 0 = 2.",
      fb:"Primitive correcte et évaluation juste. Vérification manuelle conseillée pour la notation des bornes."},
    {course:'M1 Data Science', name:'Projet : régression linéaire', type:'essay', max:100,
      q:"Décrivez votre démarche de validation du modèle et les métriques choisies.",
      a:"J'ai séparé les données en train/test (80/20), utilisé la validation croisée à 5 plis, et évalué avec le RMSE et le R². Le R² obtenu est de 0,87 sur l'ensemble de test, ce qui indique un bon ajustement sans surapprentissage manifeste.",
      fb:"Démarche méthodologique rigoureuse. Le choix des métriques est pertinent. Il aurait été utile d'ajouter une analyse des résidus."},
    {course:'M1 Data Science', name:'Dissertation : éthique de l\'IA', type:'essay', max:100,
      q:"Dans quelle mesure le contrôle humain reste-t-il indispensable dans l'évaluation automatisée ?",
      a:"Le contrôle humain garantit la responsabilité, corrige les biais du modèle et préserve l'équité. Les systèmes automatisés peuvent proposer une évaluation, mais la décision finale doit rester entre les mains de l'enseignant, conformément aux exigences de transparence et de supervision.",
      fb:"Argumentation nuancée et bien structurée, en lien direct avec le cadre réglementaire. Quelques exemples concrets renforceraient encore le propos."},
  ];

  function isoAgo(daysAgo, hour){ const d=new Date(); d.setDate(d.getDate()-daysAgo); d.setHours(hour, ri(0,59), 0, 0); return d.toISOString(); }

  function build(){
    const logs=[]; let id=1000;
    ASSIGNMENTS.forEach((as, ai)=>{
      const n = as.type==='qcm' ? 16 : ri(7,11);
      for(let i=0;i<n;i++){
        const max=as.max;
        const ratio = 0.5 + rnd()*0.48;                       // 50–98%
        const proposed = as.type==='qcm' ? (rnd()<0.78?max:ri(0,max-1)) : Math.round(ratio*max*2)/2;
        const requires = as.type!=='qcm';                      // QCM auto-graded
        const student = STUDENTS[(ai*7+i)%STUDENTS.length];
        const daysAgo = ri(0,29);
        const ts = isoAgo(daysAgo, ri(8,19));

        let decision=null, finalScore=null, comment=null, reviewedAt=null;
        if(requires){
          const r=rnd();
          if(r<0.18){ decision=null; }                         // still pending
          else if(r<0.74){ decision='validated'; finalScore=proposed; reviewedAt=isoAgo(Math.max(0,daysAgo-1), ri(8,19)); }
          else if(r<0.93){ decision='modified'; const delta=(rnd()<0.5?-1:1)*Math.round(max*(0.02+rnd()*0.08)*2)/2; finalScore=Math.max(0,Math.min(max,proposed+delta)); comment=pick(['Argumentation à nuancer.','Quelques imprécisions corrigées.','Barème ajusté pour cette question.','Bonus pour la clarté de la rédaction.']); reviewedAt=isoAgo(Math.max(0,daysAgo-1), ri(8,19)); }
          else { decision='rejected'; finalScore=0; comment='Vérification manuelle requise.'; reviewedAt=isoAgo(Math.max(0,daysAgo-1), ri(8,19)); }
        }
        logs.push({
          log_id:'EV-'+(id++),
          course_name:as.course, assignment_name:as.name, assignment_id:'A'+ai,
          student_id:1+((ai*7+i)%STUDENTS.length), student_name:student,
          task_type:as.type, question:as.q, student_answer_preview:as.a, feedback:as.fb,
          proposed_score:proposed, max_score:max,
          requires_human_review:requires,
          human_decision:decision, human_final_score:finalScore, human_comment:comment, reviewed_at:reviewedAt,
          backend: rnd()<0.6?'gemini-1.5-pro':'mistral-large', timestamp:ts,
        });
      }
    });
    logs.sort((a,b)=> new Date(a.timestamp)-new Date(b.timestamp));
    return logs;
  }

  function computeStats(logs){
    const byType={}; const types=['qcm','short_answer','essay','formal'];
    types.forEach(t=>byType[t]={total_evaluations:0,requires_human_review:0,_ai:[],_hu:[],validated:0,modified:0,rejected:0});
    logs.forEach(l=>{
      const b=byType[l.task_type]; if(!b) return;
      b.total_evaluations++;
      if(l.requires_human_review) b.requires_human_review++;
      if(l.max_score>0) b._ai.push(l.proposed_score/l.max_score*100);
      if(l.human_final_score!=null && l.max_score>0) b._hu.push(l.human_final_score/l.max_score*100);
      if(l.human_decision==='validated') b.validated++;
      else if(l.human_decision==='modified') b.modified++;
      else if(l.human_decision==='rejected') b.rejected++;
    });
    const avg=a=>a.length?Math.round(a.reduce((x,y)=>x+y,0)/a.length):null;
    types.forEach(t=>{ const b=byType[t]; b.avg_ai_score_pct=avg(b._ai); b.avg_human_score_pct=avg(b._hu);
      const rev=b.validated+b.modified; b.modification_rate_pct = rev? Math.round(b.modified/rev*100):null; delete b._ai; delete b._hu; });
    const validated=logs.filter(l=>l.human_decision==='validated').length;
    const modified=logs.filter(l=>l.human_decision==='modified').length;
    const pending=logs.filter(l=>l.requires_human_review&&!l.human_decision).length;
    const rev=validated+modified;
    return { global:{ total_evaluations:logs.length, pending_review:pending, validated, modification_rate_pct: rev?Math.round(modified/rev*100):null }, by_task_type:byType };
  }

  function computeKappa(logs){
    const N=11, pairs=logs.filter(l=>l.human_final_score!=null && l.human_decision!=='rejected' && l.max_score>0);
    if(pairs.length<10) return { message:"Pas encore assez de paires évaluées pour calculer le kappa." };
    const bucket=(s,m)=>Math.max(0,Math.min(N-1,Math.round(s/m*(N-1))));
    const O=Array.from({length:N},()=>new Array(N).fill(0)); const ai=new Array(N).fill(0), hu=new Array(N).fill(0);
    pairs.forEach(l=>{ const a=bucket(l.proposed_score,l.max_score), h=bucket(l.human_final_score,l.max_score); O[a][h]++; ai[a]++; hu[h]++; });
    const n=pairs.length; let num=0, den=0;
    for(let i=0;i<N;i++)for(let j=0;j<N;j++){ const w=Math.pow(i-j,2)/Math.pow(N-1,2); const e=ai[i]*hu[j]/n; num+=w*O[i][j]; den+=w*e; }
    const kappa=den===0?1:1-num/den;
    const interp = kappa>=0.8?"Accord quasi parfait entre l'IA et l'enseignant." : kappa>=0.6?"Accord substantiel entre l'IA et l'enseignant." : kappa>=0.4?"Accord modéré.":"Accord faible.";
    return { quadratic_weighted_kappa:Math.round(kappa*10000)/10000, interpretation:interp, n_evaluated:n };
  }

  window.getDemo = function(){
    if(!cache){ const logs=build(); cache={logs}; }
    return { logs: cache.logs, stats: computeStats(cache.logs), kappa: computeKappa(cache.logs) };
  };
  window.applyDemoReview = function(logId, body){
    if(!cache) return;
    const l=cache.logs.find(x=>x.log_id===logId); if(!l) return;
    l.human_decision=body.decision; l.human_final_score=body.final_score; l.human_comment=body.prof_comment||null; l.reviewed_at=new Date().toISOString();
  };
})();

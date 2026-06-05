/* EACHS — chart helpers (dependency-free SVG) ----------------------------- */

function cssVar(name){
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/* Donut / gauge ----------------------------------------------------------- */
function donut(pct, color, size, stroke, opts={}){
  const r=(size-stroke)/2, c=2*Math.PI*r, off=c*(1-Math.max(0,Math.min(1,pct/100)));
  const track = opts.track || cssVar('--border');
  const label = opts.label, sub = opts.sub, lc = opts.labelColor || color;
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="display:block">
    <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="${track}" stroke-width="${stroke}"/>
    <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="${color}" stroke-width="${stroke}" stroke-linecap="round"
      stroke-dasharray="${c}" stroke-dashoffset="${off}" transform="rotate(-90 ${size/2} ${size/2})">
      <animate attributeName="stroke-dashoffset" from="${c}" to="${off}" dur="0.9s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1" keyTimes="0;1"/>
    </circle>
    ${label!=null?`<text x="50%" y="${sub?'45%':'52%'}" text-anchor="middle" font-family="JetBrains Mono" font-size="${size*0.2}" font-weight="700" fill="${lc}">${label}</text>`:''}
    ${sub?`<text x="50%" y="63%" text-anchor="middle" font-family="Plus Jakarta Sans" font-size="${size*0.085}" font-weight="600" fill="${cssVar('--faint')}">${sub}</text>`:''}
  </svg>`;
}

/* smooth path through points --------------------------------------------- */
function smoothPath(vals, w, h, pad, ymin, ymax){
  const n=vals.length; if(n<2) return '';
  const lo = ymin!=null?ymin:Math.min(...vals), hi = ymax!=null?ymax:Math.max(...vals);
  const xs=i=>pad+i*((w-2*pad)/(n-1));
  const ys=v=>h-pad-((v-lo)/((hi-lo)||1))*(h-2*pad);
  let d=`M ${xs(0).toFixed(1)} ${ys(vals[0]).toFixed(1)}`;
  for(let i=1;i<n;i++){
    const x0=xs(i-1),y0=ys(vals[i-1]),x1=xs(i),y1=ys(vals[i]),cx=(x0+x1)/2;
    d+=` C ${cx.toFixed(1)} ${y0.toFixed(1)} ${cx.toFixed(1)} ${y1.toFixed(1)} ${x1.toFixed(1)} ${y1.toFixed(1)}`;
  }
  return d;
}

/* Multi-line area chart --------------------------------------------------- */
function lineChart(series, w, h, opts={}){
  const pad=12;
  const ymin=opts.ymin, ymax=opts.ymax;
  const grid=[0,1,2,3].map(i=>{const y=pad+i*(h-2*pad)/3;return `<line x1="${pad}" x2="${w-pad}" y1="${y}" y2="${y}" stroke="${cssVar('--border')}" stroke-width="1"/>`}).join('');
  const body=series.map(s=>{
    const d=smoothPath(s.vals,w,h,pad,ymin,ymax); if(!d) return '';
    const area=`${d} L ${(w-pad)} ${h-pad} L ${pad} ${h-pad} Z`;
    const gid='g'+Math.random().toString(36).slice(2,8);
    return `${s.fill?`<defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${s.color}" stop-opacity="0.22"/><stop offset="100%" stop-color="${s.color}" stop-opacity="0"/></linearGradient></defs><path d="${area}" fill="url(#${gid})"/>`:''}
      <path d="${d}" fill="none" stroke="${s.color}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>`;
  }).join('');
  return `<svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${grid}${body}</svg>`;
}

/* Vertical bars ----------------------------------------------------------- */
function vbars(data, w, h, opts={}){
  const pad=14, foot=22, max=opts.max||Math.max(...data.map(d=>d.v),1);
  const slot=(w-2*pad)/data.length, bw=Math.min(slot*0.52,46);
  return `<svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}">${data.map((d,i)=>{
    const x=pad+i*slot+(slot-bw)/2;
    const bh=Math.max((d.v/max)*(h-foot-22),2), y=h-foot-bh;
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" rx="6" fill="${d.color}">
        <animate attributeName="height" from="0" to="${bh.toFixed(1)}" dur="0.7s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1" keyTimes="0;1"/>
        <animate attributeName="y" from="${(h-foot).toFixed(1)}" to="${y.toFixed(1)}" dur="0.7s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1" keyTimes="0;1"/>
      </rect>
      <text x="${(x+bw/2).toFixed(1)}" y="${(y-7).toFixed(1)}" text-anchor="middle" font-family="JetBrains Mono" font-size="12" font-weight="700" fill="${cssVar('--ink')}">${d.v}</text>
      <text x="${(x+bw/2).toFixed(1)}" y="${h-6}" text-anchor="middle" font-family="Plus Jakarta Sans" font-size="11" font-weight="600" fill="${cssVar('--faint')}">${d.l}</text>`;
  }).join('')}</svg>`;
}

/* Grouped bars (two series, e.g. IA vs Humain) ---------------------------- */
function groupedBars(groups, w, h, opts={}){
  const pad=16, foot=24;
  const max=opts.max||Math.max(...groups.flatMap(g=>g.vals),1);
  const slot=(w-2*pad)/groups.length, n=2, gap=4, bw=Math.min((slot*0.6-gap)/n,26);
  const cols=opts.colors||[cssVar('--violet'),cssVar('--emerald')];
  return `<svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}">${groups.map((g,i)=>{
    const base=pad+i*slot+(slot-(bw*n+gap))/2;
    const bars=g.vals.map((v,j)=>{
      const x=base+j*(bw+gap), bh=Math.max((v/max)*(h-foot-18),2), y=h-foot-bh;
      return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" rx="5" fill="${cols[j]}">
        <animate attributeName="height" from="0" to="${bh.toFixed(1)}" dur="0.7s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1" keyTimes="0;1"/>
        <animate attributeName="y" from="${(h-foot).toFixed(1)}" to="${y.toFixed(1)}" dur="0.7s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1" keyTimes="0;1"/></rect>`;
    }).join('');
    return `${bars}<text x="${(base+(bw*n+gap)/2).toFixed(1)}" y="${h-7}" text-anchor="middle" font-family="Plus Jakarta Sans" font-size="11" font-weight="600" fill="${cssVar('--faint')}">${g.l}</text>`;
  }).join('')}</svg>`;
}

/* Histogram (distribution) ------------------------------------------------ */
function histogram(buckets, w, h, color){
  const pad=14, foot=24, max=Math.max(...buckets.map(b=>b.v),1);
  const slot=(w-2*pad)/buckets.length, bw=slot*0.8;
  return `<svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}">${buckets.map((b,i)=>{
    const x=pad+i*slot+(slot-bw)/2;
    const bh=Math.max((b.v/max)*(h-foot-14),b.v>0?3:0), y=h-foot-bh;
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" rx="4" fill="${color}" opacity="${0.45+0.55*(i/(buckets.length-1))}">
        <animate attributeName="height" from="0" to="${bh.toFixed(1)}" dur="0.7s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1" keyTimes="0;1"/>
        <animate attributeName="y" from="${(h-foot).toFixed(1)}" to="${y.toFixed(1)}" dur="0.7s" fill="freeze" calcMode="spline" keySplines="0.2 0.8 0.2 1" keyTimes="0;1"/></rect>
      ${i%2===0?`<text x="${(x+bw/2).toFixed(1)}" y="${h-7}" text-anchor="middle" font-family="JetBrains Mono" font-size="10" font-weight="600" fill="${cssVar('--faint')}">${b.l}</text>`:''}`;
  }).join('')}</svg>`;
}

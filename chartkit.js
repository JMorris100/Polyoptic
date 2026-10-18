/* ══════════════════════════════════════════════════════════════════
   Polyoptic chart kit — the drawing rules every chart on the site shares.

   The explorer and the homepage both draw through these functions, so a
   chart reads the same wherever it appears: round-number ticks, a stronger
   line at 100 or 0, the unit written above the plot, government shaded
   behind the data, series named at their line ends, breaks drawn on the
   line. Change a rule here and every chart follows. The matching styles
   are in chart.css.

   Everything returns SVG strings pushed onto a caller's array `g`, and
   takes the scale it needs as arguments, so it carries no state of its own.
   ══════════════════════════════════════════════════════════════════ */
(function(){

/* Categorical slots, violet-led so a chart reads as this site's. Light and
   dark are the same four hues stepped for their own surface. */
const PAL={
  light: ["#6D4AE0","#0E9384","#D97706","#DB2777"],
  dark:  ["#8367E8","#17A394","#C58207","#DE5A96"],
};
const theme=()=>document.documentElement.dataset.theme||"light";
const pal=i=>(PAL[theme()]||PAL.light)[i%4];

const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

/* Break on words at a character budget; anything longer than a line on its
   own (a URL) is hard-broken. */
function wrapText(s,max){
  const out=[]; let cur="";
  String(s).split(/\s+/).filter(Boolean).flatMap(w=>{
    if(w.length<=max) return [w];
    const bits=[]; for(let i=0;i<w.length;i+=max) bits.push(w.slice(i,i+max)); return bits;
  }).forEach(w=>{
    if(!cur) cur=w;
    else if((cur+" "+w).length<=max) cur+=" "+w;
    else { out.push(cur); cur=w; }
  });
  if(cur) out.push(cur);
  return out.length?out:[""];
}

/* A series name for the line end: wrapped to the gutter, three lines at most */
const NAME_CH=24;
function nameLines(name){
  const l=wrapText(name,NAME_CH);
  return l.length>3?[l[0],l[1],l[2].slice(0,NAME_CH-1)+"…"]:l;
}
/* the right gutter a set of end labels needs */
const gutterFor=(names,min)=>Math.min(200,Math.max(min,
  Math.round(Math.max(...names.flatMap(nameLines).map(l=>l.length))*6.1)+22));

/* The y axis: round 1-2-5 steps with the domain snapped out to whole steps,
   so ticks read 80 / 100 / 120 rather than 83.2 / 127 / 170. `incl` forces a
   value into range — 100 on an index, 0 for columns. */
function niceStep(raw){const e=Math.pow(10,Math.floor(Math.log10(raw))),f=raw/e;
  return (f<=1?1:f<=2?2:f<=2.5?2.5:f<=5?5:10)*e;}
function yAxis(vals,plotH,incl){
  const v=vals.filter(x=>x!=null&&isFinite(x));
  if(incl!=null) v.push(incl);
  if(!v.length) return {mn:0,mx:1,ticks:[0,1],st:1};
  let a=Math.min(...v),b=Math.max(...v);
  if(a===b){a-=1;b+=1;}
  const n=Math.max(3,Math.min(6,Math.round(plotH/55)));
  const st=niceStep((b-a)/n);
  const mn=Math.floor(a/st+1e-9)*st, mx=Math.ceil(b/st-1e-9)*st, ticks=[];
  for(let t=mn;t<=mx+st/2;t+=st) ticks.push(+t.toFixed(10));
  return {mn,mx,ticks,st};
}
const tickFmt=(v,st)=>{let d=0; while(d<6&&Math.abs(st*10**d-Math.round(st*10**d))>1e-6) d++;
  return Math.abs(v)>=1000?v.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g,","):v.toFixed(d);};

/* Gridlines, y labels, year labels and the unit as a line of text above the
   plot rather than rotated up the side. `base` is drawn stronger.
   o: {g, ax, Y, x0, x1, sx, l, r, bot, H, label, base} */
function frame(o){
  const {g,ax,Y,l,r}=o;
  const same=(v,b)=>b!=null&&Math.abs(v-b)<ax.st/1e6;
  ax.ticks.forEach(v=>{
    g.push(`<line class="${same(v,o.base)?"baseline":"gridline"}" x1="${l}" y1="${Y(v).toFixed(1)}" x2="${r}" y2="${Y(v).toFixed(1)}"/>`);
    g.push(`<text class="axlabel" x="${l-9}" y="${(Y(v)+3.5).toFixed(1)}" text-anchor="end">${tickFmt(v,ax.st)}</text>`);
  });
  if(o.base!=null&&o.base>ax.mn&&o.base<ax.mx&&!ax.ticks.some(v=>same(v,o.base)))
    g.push(`<line class="baseline" x1="${l}" y1="${Y(o.base).toFixed(1)}" x2="${r}" y2="${Y(o.base).toFixed(1)}"/>`);
  const span=o.x1-o.x0, step=span>24?5:span>12?2:1;
  for(let yr=Math.ceil(o.x0/step)*step;yr<=o.x1;yr+=step)
    g.push(`<text class="axlabel" x="${o.sx(yr).toFixed(1)}" y="${o.H-6}" text-anchor="middle">${yr}</text>`);
  if(o.label) g.push(`<text class="axunit" x="0" y="11">${esc(o.label)}</text>`);
}
/* the extra room above the plot that government shading needs for names */
const BANDS_TOP=16;

/* Government as faint party-coloured bands behind the data, each prime
   minister named along the top. A band too narrow for its name stays
   unlabelled and names itself on hover instead.
   o: {g, x0, x1, sx, top, bot, eras, pms} */
function bands(o){
  const {g,sx,top,bot}=o;
  (o.eras||[]).forEach(e=>{
    const f=Math.max(e.from,o.x0), t=Math.min(e.to,o.x1);
    if(t<=f) return;
    g.push(`<rect class="band" x="${sx(f).toFixed(1)}" y="${top}" width="${(sx(t)-sx(f)).toFixed(1)}" height="${bot-top}" fill="${e.colour}"><title>${esc(e.party)} ${e.from}–${e.to}</title></rect>`);
  });
  const pms=o.pms||[];
  pms.forEach(([y,n],i)=>{
    const end=i+1<pms.length?pms[i+1][0]:Infinity;
    const f=Math.max(y,o.x0), t=Math.min(end,o.x1);
    if(t<=f) return;
    const a=sx(f), b=sx(t);
    if(y>o.x0) g.push(`<line class="banddiv" x1="${a.toFixed(1)}" y1="${top-14}" x2="${a.toFixed(1)}" y2="${bot}"/>`);
    g.push(`<rect x="${a.toFixed(1)}" y="${top-14}" width="${(b-a).toFixed(1)}" height="14" fill="transparent"><title>${esc(n)}, ${y}–${end===Infinity?"":end}</title></rect>`);
    if(b-a>n.length*5.6+10) g.push(`<text class="bandlbl" x="${((a+b)/2).toFixed(1)}" y="${top-4}" text-anchor="middle">${esc(n)}</text>`);
  });
}

/* Breaks sit on the line they belong to. A series that stops at a break gets
   a hollow end point (drawn by endPoint) and the reason beside its label; a
   break part way along gets a marker at that year, with the full note on
   hover. Returns the break the series ends at, if any.
   o: {g, ds (discontinuities), pts, sx, Y, colour, x0, x1} */
function breaks(o){
  const last=[...o.pts].reverse().find(q=>q[1]!=null); if(!last) return null;
  const ds=(o.ds||[]).filter(d=>d.year>=o.x0&&d.year<=o.x1+1);
  const endBreak=ds.find(d=>d.year>=Math.floor(last[0]))||null;
  ds.filter(d=>d!==endBreak).forEach(d=>{
    const q=o.pts.find(q=>q[0]>=d.year&&q[1]!=null); if(!q) return;
    const x=o.sx(q[0]).toFixed(1), y=o.Y(q[1]);
    o.g.push(`<g class="brkmark"><title>Break at ${d.year}: ${esc(d.note)}</title>`+
      `<line class="brkline" x1="${x}" y1="${(y-16).toFixed(1)}" x2="${x}" y2="${(y+16).toFixed(1)}"/>`+
      `<circle cx="${x}" cy="${y.toFixed(1)}" r="4" class="hollow" stroke="${o.colour}" stroke-width="2"/>`+
      `<text class="brk" x="${x}" y="${(y-20).toFixed(1)}" text-anchor="middle">${esc(d.label||"Series break")}</text></g>`);
  });
  return endBreak;
}
/* the point a line ends on: solid, or hollow when it ends at a break */
function endPoint(g,cx,cy,colour,endBreak){
  g.push(endBreak
    ? `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="4.5" class="hollow" stroke="${colour}" stroke-width="2"><title>${esc(endBreak.note)}</title></circle>`
    : `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="3.6" class="enddot" fill="${colour}"/>`);
}

/* Names and last values at the line ends, stacked in the right gutter and
   nudged apart where they would collide, then backed up from the bottom so
   nothing spills under the chart. A leader joins a label to its point when
   they are not level.
   o: {g, labels:[{colour, cx, cy, name, val, endBreak}], lx, floorY} */
function endLabels(o){
  const L=o.labels.map(l=>({...l,names:nameLines(l.name),
    note:l.endBreak?wrapText(l.endBreak.label||"Series ends at a break",NAME_CH):[]}));
  L.sort((a,b)=>a.cy-b.cy);
  let floor=-1e9;
  L.forEach(l=>{ l.h=l.names.length*12+12+l.note.length*11; l.top=Math.max(l.cy-9,floor+6); floor=l.top+l.h; });
  let ceil=o.floorY;
  [...L].reverse().forEach(l=>{ if(l.top+l.h>ceil) l.top=ceil-l.h; ceil=l.top-6; });
  const lx=o.lx;
  L.forEach(l=>{
    let y=l.top+9;
    if(l.cx<lx-14||Math.abs(l.top+9-l.cy)>3)
      o.g.push(`<path class="leader" d="M${(l.cx+6).toFixed(1)} ${l.cy.toFixed(1)} L${lx-6} ${(l.top+5).toFixed(1)}" stroke="${l.colour}"/>`);
    o.g.push(`<g>${l.endBreak?`<title>${esc(l.endBreak.note)}</title>`:""}`);
    l.names.forEach(n=>{ o.g.push(`<text class="endlbl" x="${lx}" y="${y}" fill="${l.colour}">${esc(n)}</text>`); y+=12; });
    o.g.push(`<text class="endval" x="${lx}" y="${y}">${esc(l.val)}</text>`); y+=12;
    l.note.forEach(n=>{ o.g.push(`<text class="brk" x="${lx}" y="${y}">${esc(n)}</text>`); y+=11; });
    o.g.push(`</g>`);
  });
}

/* a line through the non-null points, lifting the pen over gaps */
function linePath(pts,sx,Y,step){
  let d="",pen=false,lastY=null;
  pts.forEach(q=>{ if(q[1]==null){pen=false;lastY=null;return;}
    const x=sx(q[0]).toFixed(1), y=Y(q[1]).toFixed(1);
    if(step&&pen&&lastY!=null) d+="L"+x+" "+lastY+" ";
    d+=(pen?"L":"M")+x+" "+y+" "; pen=true; lastY=y; });
  return d.trim();
}

window.CK={PAL,pal,esc,wrapText,nameLines,gutterFor,niceStep,yAxis,tickFmt,frame,BANDS_TOP,bands,breaks,endPoint,endLabels,linePath};
})();

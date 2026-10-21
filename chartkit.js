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
   o: {g, ax, Y, x0, x1, sx, l, r, bot, H, label, base, noX}
   noX leaves out the years, for a y axis drawn on its own while it animates */
function frame(o){
  const {g,ax,Y,l,r}=o;
  const same=(v,b)=>b!=null&&Math.abs(v-b)<ax.st/1e6;
  ax.ticks.forEach(v=>{
    g.push(`<line class="${same(v,o.base)?"baseline":"gridline"}" x1="${l}" y1="${Y(v).toFixed(1)}" x2="${r}" y2="${Y(v).toFixed(1)}"/>`);
    g.push(`<text class="axlabel" x="${l-9}" y="${(Y(v)+4).toFixed(1)}" text-anchor="end">${tickFmt(v,ax.st)}</text>`);
  });
  if(o.base!=null&&o.base>ax.mn&&o.base<ax.mx&&!ax.ticks.some(v=>same(v,o.base)))
    g.push(`<line class="baseline" x1="${l}" y1="${Y(o.base).toFixed(1)}" x2="${r}" y2="${Y(o.base).toFixed(1)}"/>`);
  if(o.label) g.push(`<text class="axunit" x="0" y="11">${esc(o.label)}</text>`);
  if(o.noX) return;
  const span=o.x1-o.x0;
  let step=span>24?5:span>12?2:1;
  /* on a narrow chart, fewer years rather than years printed over each other */
  const per=(o.r-o.l)/Math.max(1,span);
  while(step*per<38&&step<span) step=step<2?2:step<5?5:step*2;
  for(let yr=Math.ceil(o.x0/step)*step;yr<=o.x1;yr+=step)
    g.push(`<text class="axlabel" x="${o.sx(yr).toFixed(1)}" y="${o.H-6}" text-anchor="middle">${yr}</text>`);
}
/* the extra room above the plot that government shading needs for names */
const BANDS_TOP=16;

/* Government as faint party-coloured bands behind the data, each prime
   minister named along the top. Names are placed longest term first, and a
   name may spill past its own band where the neighbours leave room, so a
   short premiership still gets named unless it would collide. One that
   cannot fit names itself on hover instead.
   o: {g, x0, x1, sx, top, bot, eras, pms} */
function bands(o){
  const {g,sx,top,bot}=o;
  (o.eras||[]).forEach(e=>{
    const f=Math.max(e.from,o.x0), t=Math.min(e.to,o.x1);
    if(t<=f) return;
    g.push(`<rect class="band" x="${sx(f).toFixed(1)}" y="${top}" width="${(sx(t)-sx(f)).toFixed(1)}" height="${bot-top}" fill="${e.colour}"><title>${esc(e.party)} ${e.from}–${e.to}</title></rect>`);
  });
  const pms=o.pms||[], L=sx(o.x0), R=sx(o.x1), want=[];
  pms.forEach(([y,n],i)=>{
    const end=i+1<pms.length?pms[i+1][0]:Infinity;
    const f=Math.max(y,o.x0), t=Math.min(end,o.x1);
    if(t<=f) return;
    const a=sx(f), b=sx(t);
    if(y>o.x0) g.push(`<line class="banddiv" x1="${a.toFixed(1)}" y1="${top-14}" x2="${a.toFixed(1)}" y2="${bot}"/>`);
    g.push(`<rect x="${a.toFixed(1)}" y="${top-14}" width="${(b-a).toFixed(1)}" height="14" fill="transparent"><title>${esc(n)}, ${y}–${end===Infinity?"":end}</title></rect>`);
    want.push({n,a,b});
  });
  /* the current prime minister first, then the longest terms (the later one
     on a tie); each name sits over its band where it can, or slides to the
     nearest free spot that still touches its band */
  const put=[], last=want[want.length-1];
  want.sort((p,q)=>(q===last)-(p===last)||(q.b-q.a)-(p.b-p.a)||q.a-p.a).forEach(p=>{
    const w=p.n.length*5.6, mid=(p.a+p.b)/2;
    const spots=[mid,...put.flatMap(q=>[q.r+5+w/2,q.l-5-w/2])]
      .map(c=>Math.min(Math.max(c,L+w/2),R-w/2))
      .filter(c=>c-w/2<p.b&&c+w/2>p.a&&Math.abs(c-mid)<=w&&!put.some(q=>c-w/2-5<q.r&&c+w/2+5>q.l))
      .sort((x,y)=>Math.abs(x-mid)-Math.abs(y-mid));
    if(!spots.length) return;
    const cx=spots[0];
    put.push({l:cx-w/2-5,r:cx+w/2+5});
    g.push(`<text class="bandlbl" x="${cx.toFixed(1)}" y="${top-4}" text-anchor="middle">${esc(p.n)}</text>`);
  });
}

/* Government as a ribbon under the chart instead of shading behind it: a
   slim party-coloured band with party names, or prime ministers, or general
   elections marked. Shares the chart's x scale, so it lines up year for year.
   o: {mode: party|pm|elections, x0, x1, sx, l, r, W, eras, pms}
   Returns HTML: a small title and the ribbon's own SVG. */
const ELECTIONS=[1997,2001,2005,2010,2015,2017,2019,2024];
function ribbon(o){
  const g=[], {sx,W}=o;
  const wrap=(title,h,aria)=>`<div class="ribbon-t">${title}</div><svg class="ribbon" viewBox="0 0 ${W} ${h}" style="width:100%;height:auto" role="img" aria-label="${aria}">${g.join("")}</svg>`;
  if(o.mode==="elections"){
    g.push(`<line class="gridline" x1="${o.l}" y1="7" x2="${o.r}" y2="7"/>`);
    ELECTIONS.forEach(y=>{ if(y>=o.x0&&y<=o.x1){
      g.push(`<circle cx="${sx(y).toFixed(1)}" cy="7" r="3.4" class="elect"/>`);
      g.push(`<text class="pmlabel" x="${sx(y).toFixed(1)}" y="24" text-anchor="middle">${y}</text>`);
    }});
    return wrap("General elections",29,"General election years");
  }
  /* a slim rounded band; names sit beneath it rather than inside the blocks */
  const BY=3, BH=8;
  (o.eras||[]).forEach(e=>{
    const f=Math.max(e.from,o.x0), t=Math.min(e.to,o.x1); if(t<=f) return;
    const x=sx(f), w=sx(t)-sx(f);
    g.push(`<g class="era"><title>${esc(e.party)} ${e.from}–${e.to}</title><rect x="${x.toFixed(1)}" y="${BY}" width="${Math.max(1,w-1.5).toFixed(1)}" height="${BH}" rx="${BH/2}" fill="${e.colour}"/></g>`);
  });
  if(o.mode==="party"){
    (o.eras||[]).forEach(e=>{
      const f=Math.max(e.from,o.x0), t=Math.min(e.to,o.x1); if(t<=f) return;
      const x=sx(f), w=sx(t)-sx(f);
      if(w>64) g.push(`<text class="eralabel" x="${(x+w/2).toFixed(1)}" y="${BY+BH+14}" text-anchor="middle">${esc(e.party)}</text>`);
    });
    return wrap("Government in power",30,"Governing party by year");
  }
  /* prime ministers, staggered onto a second row where short ones collide */
  const R1=BY+BH+16, R2=R1+11;
  let lastX=-1e9, lastRow=2;
  (o.pms||[]).filter(([y])=>y>=o.x0&&y<=o.x1).forEach(([y,n])=>{
    const x=sx(y), row=(x-lastX<58&&lastRow===1)?2:1;
    lastX=x; lastRow=row;
    const ty=row===1?R1:R2;
    g.push(`<line class="pmtick" x1="${x.toFixed(1)}" y1="${BY+BH}" x2="${x.toFixed(1)}" y2="${ty-8}"/>`);
    g.push(`<text class="pmlabel" x="${x.toFixed(1)}" y="${ty}" text-anchor="${x>o.r-30?"end":"middle"}">${esc(n)}</text>`);
  });
  return wrap("Government in power",R2+5,"Governing party and prime ministers by year");
}

/* Key events, for context: wars, crashes, the pandemic and the political
   shocks that moved the numbers. Years are fractional so a mark lands in the
   right part of the year; an event with no `to` is a single date.
   kind: crisis | war | pandemic | politics */
const EVENTS=[
  {from:1982.25,to:1982.45,short:"Falklands",name:"Falklands War",when:"Apr–Jun 1982",kind:"war"},
  {from:1984.18,to:1985.18,short:"Miners' strike",name:"Miners' strike",when:"Mar 1984 – Mar 1985",kind:"politics"},
  {from:1987.8,short:"Black Monday",name:"Black Monday stock market crash",when:"Oct 1987",kind:"crisis"},
  {from:1990.5,to:1991.75,short:"Recession",name:"Early-1990s recession",when:"1990–1991",kind:"crisis"},
  {from:1992.71,short:"Black Wednesday",name:"Black Wednesday: the pound leaves the ERM",when:"Sep 1992",kind:"crisis"},
  {from:2000.2,short:"Dot-com crash",name:"Dot-com crash",when:"Mar 2000",kind:"crisis"},
  {from:2003.22,short:"Iraq War",name:"Iraq War begins",when:"Mar 2003",kind:"war"},
  {from:2007.7,to:2009.5,short:"Financial crisis",name:"Global financial crisis and recession",when:"Sep 2007 – mid 2009",kind:"crisis"},
  {from:2016.48,short:"Brexit vote",name:"EU referendum",when:"Jun 2016",kind:"politics"},
  {from:2020.22,to:2021.55,short:"Covid-19",name:"Covid-19 pandemic: first lockdown to restrictions lifted",when:"Mar 2020 – Jul 2021",kind:"pandemic"},
  {from:2022.15,short:"Ukraine war",name:"Russia invades Ukraine; energy price shock",when:"Feb 2022",kind:"war"},
  {from:2022.73,short:"Mini-budget",name:"Mini-budget and gilt market turmoil",when:"Sep 2022",kind:"crisis"}
];
const EVENTS_ROW=13;
/* Where each event in view sits, and which of two label rows its name goes
   on; a name with room on neither row is left off and names itself on hover.
   o: {x0, x1, sx, l, r} */
function eventLayout(o){
  const ends=[-1e9,-1e9];
  return EVENTS.filter(e=>(e.to??e.from)>=o.x0&&e.from<=o.x1).map(e=>{
    const a=o.sx(Math.max(e.from,o.x0)), b=e.to!=null?o.sx(Math.min(e.to,o.x1)):a;
    const w=e.short.length*5.6+6;
    const cx=Math.min(o.r-w/2,Math.max(o.l+w/2,(a+b)/2));
    return {e,a,b,cx,lo:cx-w/2,hi:cx+w/2,row:-1};
  }).sort((p,q)=>p.cx-q.cx).map(it=>{
    for(let r=0;r<2;r++) if(it.lo>ends[r]+6){ it.row=r; ends[r]=it.hi; break; }
    return it;
  });
}
const eventRows=items=>items.reduce((m,it)=>Math.max(m,it.row+1),0);
const evTip=e=>`<title>${esc(e.name)}, ${esc(e.when)}</title>`;

/* Key events behind the data: a faint span for something that lasted, a
   dashed line for a single date, names in rows above the plot.
   o: {g, items (from eventLayout), top, bot, lblBot} — lblBot is the
   baseline of the lowest label row */
function events(o){
  const {g,top,bot}=o;
  o.items.forEach(it=>{
    const {e,a,b}=it, ly=o.lblBot-it.row*EVENTS_ROW;
    const mark = e.to!=null
      ? `<rect class="evspan" x="${a.toFixed(1)}" y="${top}" width="${Math.max(1.5,b-a).toFixed(1)}" height="${bot-top}"/>`
      : `<line class="evline" x1="${a.toFixed(1)}" y1="${top}" x2="${a.toFixed(1)}" y2="${bot}"/>`+
        `<rect class="evhit" x="${(a-4).toFixed(1)}" y="${top}" width="8" height="${bot-top}"/>`;
    const lbl = it.row<0 ? "" :
      `<line class="evtick" x1="${it.cx.toFixed(1)}" y1="${ly+3}" x2="${it.cx.toFixed(1)}" y2="${top}"/>`+
      `<text class="evlbl" x="${it.cx.toFixed(1)}" y="${ly}" text-anchor="middle">${esc(e.short)}</text>`;
    g.push(`<g class="ev">${evTip(e)}${mark}${lbl}</g>`);
  });
}

/* Key events as a ribbon under the chart: spans as slim bars, single dates
   as dots, names beneath on up to two rows.
   o: {x0, x1, sx, l, r, W} */
function eventRibbon(o){
  const items=eventLayout(o), g=[], BY=7, R1=26;
  g.push(`<line class="gridline" x1="${o.l}" y1="${BY}" x2="${o.r}" y2="${BY}"/>`);
  items.forEach(it=>{
    const {e,a,b}=it, ty=R1+Math.max(0,it.row)*EVENTS_ROW;
    const mark = e.to!=null
      ? `<rect class="evbar" x="${a.toFixed(1)}" y="${BY-3.5}" width="${Math.max(7,b-a).toFixed(1)}" height="7" rx="3.5"/>`
      : `<circle class="evdot" cx="${a.toFixed(1)}" cy="${BY}" r="3.4"/>`;
    const lbl = it.row<0 ? "" :
      `<line class="pmtick" x1="${it.cx.toFixed(1)}" y1="${BY+4}" x2="${it.cx.toFixed(1)}" y2="${ty-9}"/>`+
      `<text class="evlbl" x="${it.cx.toFixed(1)}" y="${ty}" text-anchor="middle">${esc(e.short)}</text>`;
    g.push(`<g class="ev">${evTip(e)}${mark}${lbl}</g>`);
  });
  const h=R1+Math.max(0,eventRows(items)-1)*EVENTS_ROW+5;
  return `<div class="ribbon-t">Key events</div><svg class="ribbon" viewBox="0 0 ${o.W} ${h}" style="width:100%;height:auto" role="img" aria-label="Key economic and political events">${g.join("")}</svg>`;
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


/* Small line icons for the topics, drawn on a 16-unit grid in
   currentColor so they take the colour of whatever they sit in. */
const TOPIC_ICONS={
  work:'<rect x="2.5" y="5" width="11" height="8.5" rx="1.5"/><path d="M6 5V3.3h4V5M2.5 8.8h11M8 8v1.6"/>',
  economy:'<path d="M2.5 12.5l3.5-4 3 2.5 4.5-6"/><path d="M10.5 5h3v3"/>',
  housing:'<path d="M2.5 7.5L8 3l5.5 4.5"/><path d="M4 6.5v7h8v-7"/><path d="M6.8 13.5v-3.5h2.4v3.5"/>',
  education:'<path d="M1.5 6.5L8 3.5l6.5 3L8 9.5z"/><path d="M4.5 8v3.2c1 .9 2.2 1.3 3.5 1.3s2.5-.4 3.5-1.3V8"/>',
  health:'<path d="M8 13.5S2.5 10.2 2.5 6.4A2.8 2.8 0 0 1 8 5.2a2.8 2.8 0 0 1 5.5 1.2C13.5 10.2 8 13.5 8 13.5z"/>',
  crime:'<path d="M8 2.5v11M5.5 13.5h5M3.5 4.5h9"/><path d="M3.5 4.5L1.8 8.8a1.9 1.9 0 0 0 3.4 0z"/><path d="M12.5 4.5l-1.7 4.3a1.9 1.9 0 0 0 3.4 0z"/>',
  transport:'<rect x="3.5" y="2.5" width="9" height="9" rx="2"/><path d="M3.5 7.5h9M6 14l.8-2.5M10 14l-.8-2.5"/><circle cx="6" cy="9.5" r=".4"/><circle cx="10" cy="9.5" r=".4"/>',
  environment:'<path d="M3 13c0-6 4-10 10.5-10.5C13 9 9 13 3 13z"/><path d="M3 13l6.5-6.5"/>',
  migration:'<circle cx="6" cy="5" r="2"/><path d="M2 13.5c0-2.3 1.8-4 4-4s4 1.7 4 4"/><path d="M10.5 3.3a1.8 1.8 0 0 1 0 3.4M11.8 9.7c1.4.5 2.4 1.9 2.4 3.8"/>',
  culture:'<path d="M2 6L8 2.5 14 6z"/><path d="M3.5 7.5v5M6.5 7.5v5M9.5 7.5v5M12.5 7.5v5M2 13.5h12"/>',
  local:'<path d="M8 14s4.5-4.1 4.5-7.5a4.5 4.5 0 0 0-9 0C3.5 9.9 8 14 8 14z"/><circle cx="8" cy="6.5" r="1.6"/>',
  all:'<rect x="2.5" y="2.5" width="4.5" height="4.5" rx="1"/><rect x="9" y="2.5" width="4.5" height="4.5" rx="1"/><rect x="2.5" y="9" width="4.5" height="4.5" rx="1"/><rect x="9" y="9" width="4.5" height="4.5" rx="1"/>'
};
const topicIcon=(k,cls="ticon")=>TOPIC_ICONS[k]
  ?`<svg class="${cls}" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${TOPIC_ICONS[k]}</svg>`:"";

/* The UK in four pieces, small enough for a 16px badge: ONS ITL1 boundaries
   simplified (ingest/geo.py has the full ones). A geography's badge fills the
   nations it covers and leaves the rest faint. */
const NATIONS={"w":109,"h":170,"p":{"E":"M66 63 73 77 69 77 73 79 74 85 79 87 64 87 60 80 60 72 66 63ZM60 75 65 87 60 93 66 98 67 110 57 114 53 107 59 107 54 104 58 100 55 100 57 95 58 91 54 94 49 86 53 78 60 75ZM80 86 87 93 90 103 79 101 88 103 87 106 85 103 70 108 60 93 64 87 80 86ZM86 103 90 105 93 112 89 116 92 118 84 122 79 132 75 133 76 126 66 107 68 104 75 109 86 103ZM74 130 71 134 69 131 58 136 54 131 55 122 54 115 67 110 76 126 74 130ZM100 114 107 117 109 123 107 130 101 133 104 135 98 137 100 139 96 139 99 140 93 142 89 138 83 140 81 136 83 136 83 121 100 114ZM92 142 89 142 92 142 88 146 84 139 89 138 92 142ZM82 129 83 136 81 136 86 145 95 142 106 143 101 152 81 156 72 153 74 155 72 157 67 151 71 152 72 145 70 133 82 129ZM69 131 72 145 71 152 67 151 70 156 66 159 59 158 61 160 57 156 49 157 47 165 40 161 40 164 35 162 30 167 28 170 22 166 33 159 37 150 41 151 42 147 54 148 62 137 58 139 61 132 69 131Z","W":"M52 107 58 114 54 116 55 122 52 124 59 140 50 144 45 139 40 140 43 138 40 136 33 137 30 138 28 134 41 128 45 122 44 115 36 116 46 108 52 107ZM38 108 40 106 43 108 40 111 38 108Z","S":"M23 58 24 63 21 65 21 62 23 58ZM24 45 29 50 21 51 25 50 22 47 24 45ZM23 26 24 33 30 34 26 38 28 35 23 34 18 31 20 27 23 30 23 26ZM19 16 26 11 22 21 20 19 20 23 16 23 19 22 16 16 19 16ZM30 51 35 47 31 49 35 42 29 48 25 45 30 45 23 44 27 44 28 39 31 39 28 38 32 37 29 36 32 33 29 34 32 31 28 32 28 28 31 29 29 23 36 24 32 19 33 16 38 17 37 9 42 13 56 9 55 15 46 24 43 23 49 24 42 28 47 27 44 31 53 26 68 29 61 48 52 51 58 50 60 54 52 58 47 56 65 60 65 68 55 77 49 76 45 81 40 78 41 82 36 79 35 83 32 77 39 67 36 60 41 60 37 58 38 54 35 60 34 58 32 61 35 53 26 70 30 51ZM53 2 55 0 59 5 57 8 53 2Z","N":"M27 90 22 94 16 93 12 86 6 91 0 84 5 82 3 80 7 79 9 74 22 72 27 80 24 82 29 86 27 90Z"}};
const COVERS={"UK":"EWSN","Great Britain":"EWS","England and Wales":"EW","England & Wales":"EW",
  "England":"E","Wales":"W","Scotland":"S","Northern Ireland":"N"};
const geoIcon=(geo,cls="gicon")=>{
  const on=COVERS[geo]; if(!on) return "";
  return `<svg class="${cls}" viewBox="-2 -2 ${NATIONS.w+4} ${NATIONS.h+4}" aria-hidden="true">${
    Object.entries(NATIONS.p).map(([n,d])=>`<path d="${d}" fill="currentColor" stroke="currentColor" stroke-width="2.5" stroke-linejoin="round" opacity="${on.includes(n)?1:.22}"/>`).join("")}</svg>`;
};

window.CK={PAL,pal,esc,wrapText,nameLines,gutterFor,niceStep,yAxis,tickFmt,frame,BANDS_TOP,bands,ribbon,ELECTIONS,EVENTS,EVENTS_ROW,eventLayout,eventRows,events,eventRibbon,breaks,endPoint,endLabels,linePath,topicIcon,geoIcon};
})();

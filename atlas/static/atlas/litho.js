// Litho map style: sheet furniture and rendering helpers ported from the
// design handoff (docs/Улучшение дизайна карты/handoff/derry-map-render.js).
// World coordinates here are screen-oriented (y grows downward), matching the
// inside of #world where map.js already draws geometry as (x, -y_payload).
(function(){
'use strict';
const NS='http://www.w3.org/2000/svg';
function el(t,a,p){const n=document.createElementNS(NS,t);for(const k in a){const v=a[k];if(v!=null&&v!==false)n.setAttribute(k,v)}if(p)p.appendChild(n);return n}
function pd(p,z){let s='M'+p[0][0]+' '+p[0][1];for(let i=1;i<p.length;i++)s+='L'+p[i][0]+' '+p[i][1];return z?s+'Z':s}
// u(n): stroke width pinned to n screen px at any zoom (map.js sets --u = 1/k px).
// mx(w,n): world width w, but never thinner than n screen px.
const u=n=>`stroke-width:calc(var(--u)*${n})`;
const mx=(w,n)=>`stroke-width:max(${w}px,calc(var(--u)*${n}))`;
const dash=(a,b)=>`stroke-dasharray:calc(var(--u)*${a}) calc(var(--u)*${b})`;
// The designed sheet frame; content outside is clipped, the margin gets a dot raster.
const FR=[-6150,-3450,3450,4380];
const PAL={paper:'#f5f1e3',frameC:'#8b7a5a',ink:'#2f3d36'};
// Patterns keep a fixed screen-pixel cell: cells are authored 10×10 and rescaled on zoom.
const patterns=[];
function pattern(defs,id,px,draw,rot){const p=el('pattern',{id,patternUnits:'userSpaceOnUse',width:10,height:10},defs);draw(p);patterns.push([p,px,rot]);return`url(#${id})`}
function updatePatterns(k){for(const[p,px,rot]of patterns){const s=px/10/k;p.setAttribute('patternTransform',`scale(${s})${rot?` rotate(${rot})`:''}`)}}
const dots=(c,r,pts)=>p=>pts.forEach(([x,y])=>el('circle',{cx:x,cy:y,r,fill:c},p));

// --- Sheet: paper under everything, a clip for the content, frame on top.
function paper(world){el('rect',{x:-12000,y:-10000,width:22000,height:22000,fill:PAL.paper,class:'litho-paper'},world)}
function clip(world,defs){
 const cp=el('clipPath',{id:'clipF'},defs);
 el('rect',{x:FR[0],y:FR[1],width:FR[2]-FR[0],height:FR[3]-FR[1]},cp);
 return el('g',{'clip-path':'url(#clipF)'},world);
}
function frame(world,defs){
 const [x0,y0,x1,y1]=FR,B=90,c=PAL.frameC;
 const margin=pattern(defs,'lithoMargin',8,dots('#d9d2ba',1.1,[[2.5,2.5],[7.5,7.5]]));
 el('path',{d:`M${x0-4000} ${y0-4000}H${x1+4000}V${y1+4000}H${x0-4000}Z M${x0-B} ${y0-B}V${y1+B}H${x1+B}V${y0-B}Z`,fill:margin,'fill-rule':'evenodd'},world);
 el('rect',{x:x0,y:y0,width:x1-x0,height:y1-y0,fill:'none',stroke:c,style:u(.8)},world);
 el('rect',{x:x0-B,y:y0-B,width:x1-x0+2*B,height:y1-y0+2*B,fill:'none',stroke:c,style:u(1.4)},world);
 // Alternating 500 m bands between the two frame lines.
 let d='';const s=B*.42;
 for(let x=x0,i=0;x<x1;x+=500,i++)if(i%2){const w=Math.min(500,x1-x);d+=`M${x} ${y0-B/2-s/2}h${w}v${s}h${-w}Z M${x} ${y1+B/2-s/2}h${w}v${s}h${-w}Z`}
 for(let y=y0,i=0;y<y1;y+=500,i++)if(i%2){const h=Math.min(500,y1-y);d+=`M${x0-B/2-s/2} ${y}v${h}h${s}v${-h}Z M${x1+B/2-s/2} ${y}v${h}h${s}v${-h}Z`}
 el('path',{d,fill:c},world);
 // 1 km grid over the content.
 let gd='';for(let x=x0+1000;x<x1;x+=1000)gd+=`M${x} ${y0}V${y1}`;for(let y=y0+1000;y<y1;y+=1000)gd+=`M${x0} ${y}H${x1}`;
 el('path',{d:gd,fill:'none',stroke:c,opacity:.28,style:u(.6)},world);
 cartouche(world,x1-120,y1-120);
 el('rect',{x:x0-B/2-s/2,y:y0-B/2-s/2,width:x1-x0+B+s,height:y1-y0+B+s,fill:'none',stroke:c,style:u(.6)},world);
}
// Sheet cartouche, bottom right where the map is empty.
// DRAFT WORDING — the texts await the author's sign-off.
function cartouche(G,rx,by){
 const W=2050,H=1060,x=rx-W,y=by-H,c=PAL.frameC,ink=PAL.ink;
 el('rect',{x:x+14,y:y+18,width:W,height:H,fill:'#5e4e38',opacity:.08},G);
 el('rect',{x,y,width:W,height:H,fill:'#f7f3e6',stroke:c,style:u(1.4)},G);
 el('rect',{x:x+28,y:y+28,width:W-56,height:H-56,fill:'none',stroke:c,style:u(.6)},G);
 const t=(tx,ty,txt,a)=>{const n=el('text',{x:tx,y:ty,'text-anchor':'middle','font-family':'Georgia,serif',fill:ink,...a},G);n.textContent=txt};
 const cx=x+W/2;
 t(cx,y+170,'MAINE · PENOBSCOT COUNTY',{'font-size':62,'letter-spacing':14,fill:'#6b5c42'});
 t(cx,y+400,'DERRY',{'font-size':250,'font-weight':700,'letter-spacing':60});
 el('path',{d:`M${cx-600} ${y+470}H${cx-60}M${cx+60} ${y+470}H${cx+600}M${cx} ${y+445}l25 25l-25 25l-25 -25Z`,fill:c,stroke:c,style:u(.8)},G);
 t(cx,y+570,'a reconstructed town plan after Stephen King’s IT',{'font-size':66,'font-style':'italic',fill:'#4a4a3e'});
 t(cx,y+650,'1957–58 · 1984–85',{'font-size':56,'letter-spacing':10,fill:'#6b5c42'});
 // Plain 0–1000 m bar in 250 m blocks; the historical "extension scale" left of
 // zero confused readers and is gone.
 const sx=cx-500,sy=y+770;
 for(let i=0;i<4;i++)el('rect',{x:sx+i*250,y:sy,width:250,height:34,fill:i%2?'#f7f3e6':ink,stroke:ink,style:u(.8)},G);
 [['0',0],['250',250],['500',500],['1000 m',1000]].forEach(([l,d])=>t(sx+d,sy+100,l,{'font-size':50}));
 t(cx,y+H-80,'Relief conceptual · heights approximate, in metres',{'font-size':44,'font-style':'italic',fill:'#6b5c42'});
 const nx=x+W-230,ny=y+780;
 el('path',{d:`M${nx} ${ny-150}L${nx+55} ${ny+60}L${nx} ${ny+25}Z`,fill:ink},G);
 el('path',{d:`M${nx} ${ny-150}L${nx-55} ${ny+60}L${nx} ${ny+25}Z`,fill:'#f7f3e6',stroke:ink,style:u(.8)},G);
 t(nx,ny-175,'N',{'font-size':70,'font-weight':700});
}
// Screen-stuck A–J / 1–8 grid index chips, drawn into the overlay every view change.
function gridRefs(g,view){
 const[x0,y0,x1,y1]=FR,ink='#6b5c42';
 const S=(x,y)=>[(x-view.cx)*view.k+view.w/2,(y-view.cy)*view.k+view.h/2];
 const tl=S(x0,y0),top=Math.max(tl[1]-8,62),left=Math.max(tl[0]-8,14);
 const chip=(x,y,t)=>{el('rect',{x:x-8,y:y-8,width:16,height:16,rx:8,fill:'#f7f3e6',stroke:'#b9ab88','stroke-width':.8,'pointer-events':'none'},g);
  const n=el('text',{x,y:y+3.4,'text-anchor':'middle',style:'font:700 9.5px Georgia,serif',fill:ink,'pointer-events':'none'},g);n.textContent=t};
 if(S(x0,y1)[1]<top+20||tl[1]>view.h)return;
 for(let i=0,x=x0;x<x1;x+=1000,i++){const cx=S(Math.min(x+500,(x+x1)/2),0)[0];if(cx>30&&cx<view.w-70)chip(cx,top,'ABCDEFGHIJ'[i])}
 if(S(x1,0)[0]<left+20||tl[0]>view.w)return;
 for(let j=0,y=y0;y<y1;y+=1000,j++){const cy=S(0,Math.min(y+500,(y+y1)/2))[1];if(cy>top+18&&cy<view.h-80)chip(left,cy,String(j+1))}
}

// --- Adapter: payload.base (cls-tagged, map y) -> litho layer structures (screen y).
function adapt(payload){
 const D={valley:[],water:[],covered:[],roads:[],rail:[],ties:[],paths:[],contours:[],forest:[],veg:[],areas:[],buildings:[],dots:[],misc:[],bridges:[]};
 const flip=pts=>pts.map(([x,y])=>[x,-y]);
 for(const o of payload.base){
  const cls=o.cls||'misc',fid=o.feature_id||'';
  if(cls==='valley'){D.valley.push({p:flip(o.points),w:o.width});continue}
  if(cls==='water-edge'){
   const id=fid.startsWith('water:')?fid.slice(6):'trib';
   D.water.push(o.stroke==='#8b968e'?{id,p:flip(o.points),w:o.width,edge:1}:{id,p:flip(o.points),w:o.width});continue}
  if(cls==='water-core'||cls==='rail-fill')continue; // rebuilt from widths
  if(cls==='covered'){D.covered.push({p:flip(o.points)});continue}
  if(cls==='rail'){D.rail.push(flip(o.points));continue}
  if(cls==='rail-ties'){D.ties.push(flip(o.points));continue}
  if(cls==='path'){D.paths.push(flip(o.points));continue}
  if(cls==='contour'){D.contours.push({p:flip(o.points),i:o.width>=1.4?1:0});continue}
  if(cls.startsWith('road-')){
   const m=cls.match(/^road-(.+)-(casing|fill)$/);
   if(m){if(m[2]==='casing')D.roads.push({p:flip(o.points),c:m[1]})}
   else D.roads.push({p:flip(o.points),c:cls.slice(5)});continue}
  if(cls==='barrens'){D.forest.push({p:flip(o.points),t:'barrens'});continue}
  if(cls==='forest'||cls==='forest-light'){D.forest.push({p:flip(o.points),t:o.fill});continue}
  if(cls==='park'||cls==='lot'){D.areas.push({p:flip(o.points),fill:o.fill,stroke:o.stroke,w:o.width});continue}
  if(cls==='veg'){D.veg.push({p:flip(o.points),t:o.stroke==='#879674'?1:0});continue}
  if(cls==='bridge'){D.bridges.push({p:flip(o.points),w:o.width});continue}
  if(cls==='bridge-fill')continue; // redrawn from the deck width
  if(cls==='building'&&o.type==='rect'){
   const plain=o.fill==='#c7beb0'&&!o.stroke;
   D.buildings.push([o.x,-o.y,o.w,o.h,-(o.angle||0),plain?0:1,o.fill,o.stroke]);continue}
  if(o.type==='circle'){D.dots.push({x:o.x,y:-o.y,r:o.r,fill:o.fill,stroke:o.stroke,w:o.width,lyr:o.layer});continue}
  if(o.points)D.misc.push({p:flip(o.points),close:o.type==='poly',fill:o.fill,s:o.stroke,w:o.width,dash:o.dash,lyr:o.layer});
 }
 D.labels=(payload.labels||[]).map(l=>({t:l.text,x:l.x,y:-l.y}));
 return D;
}

// --- Slots: litho paint order; unported classes keep their classic drawing inside their slot.
const SLOT_ORDER=['under','valley','areas','forest','veg','relief','builtup','symbols','water','roads','covered','misc','buildings','dots','trees','flow'];
const SLOT_OF={valley:'valley','water-edge':'water','water-core':'water',covered:'covered',
 rail:'roads','rail-fill':'roads','rail-ties':'roads',path:'roads',contour:'relief',
 barrens:'forest',forest:'forest','forest-light':'forest',park:'areas',lot:'areas',veg:'veg',
 building:'buildings',misc:'misc'};
function slotOf(o){const c=o.cls||'misc';if(SLOT_OF[c])return SLOT_OF[c];if(c.startsWith('road-'))return'roads';return'misc'}
function makeSlots(host){const s={};for(const n of SLOT_ORDER)s[n]=el('g',{class:'slot-'+n},host);return s}

// --- Water (handoff blocks 1 and 5): extended rivers, bank rings, tapered brooks,
// canal lock and portals, ripple; the covered channel draws after the roads.
function ext(p,st,L){const a=st?p[0]:p[p.length-1],b=st?p[Math.min(3,p.length-1)]:p[Math.max(0,p.length-4)],dx=a[0]-b[0],dy=a[1]-b[1],n=Math.hypot(dx,dy)||1,q=[a[0]+dx/n*L,a[1]+dy/n*L];return st?[q,...p]:[...p,q]}
function sdist(p,a,b){const dx=b[0]-a[0],dy=b[1]-a[1],L=dx*dx+dy*dy||1;let t=((p[0]-a[0])*dx+(p[1]-a[1])*dy)/L;t=Math.max(0,Math.min(1,t));return Math.hypot(a[0]+t*dx-p[0],a[1]+t*dy-p[1])}
function segX(a,b,c,d){const r=[b[0]-a[0],b[1]-a[1]],s=[d[0]-c[0],d[1]-c[1]],den=r[0]*s[1]-r[1]*s[0];if(!den)return null;const t=((c[0]-a[0])*s[1]-(c[1]-a[1])*s[0])/den,q=((c[0]-a[0])*r[1]-(c[1]-a[1])*r[0])/den;return t>=0&&t<=1&&q>=0&&q<=1?[a[0]+t*r[0],a[1]+t*r[1],Math.atan2(r[1],r[0])]:null}
function rayHit(o,d,segs,maxT){let best=maxT,hit=null;for(const[a,b,tag]of segs){const sx=b[0]-a[0],sy=b[1]-a[1],den=d[0]*sy-d[1]*sx;if(Math.abs(den)<1e-9)continue;const t=((a[0]-o[0])*sy-(a[1]-o[1])*sx)/den,q=((a[0]-o[0])*d[1]-(a[1]-o[1])*d[0])/den;if(t>1&&t<best&&q>=0&&q<=1){best=t;hit=tag}}return[best,hit]}
// Where roads cross open water: [x,y,angle,waterWidth,roadClass] for generated bridges.
function crossings(D){const out=[];const W=D.water.filter(w=>!w.edge&&w.w>=5);for(const r of D.roads){if(r.c==='lane'||r.c==='trackdash')continue;for(const w of W){for(let i=1;i<r.p.length;i++)for(let j=1;j<w.p.length;j++){const x=segX(r.p[i-1],r.p[i],w.p[j-1],w.p[j]);if(x&&!out.some(o=>Math.hypot(o[0]-x[0],o[1]-x[1])<40))out.push([x[0],x[1],x[2],w.w,r.c])}}}return out}
// Dangling road/rail ends: join to the next line, run to the sheet edge, or fade out over water.
function extendLines(D){
 const L=[...D.roads.map(r=>({r,p:r.p.slice(),rail:0})),...D.rail.map(p=>({p:p.slice(),rail:1}))];
 const segsOf=(ls,skip)=>{const o=[];for(const l of ls)if(l!==skip)for(let i=1;i<l.p.length;i++)o.push([l.p[i-1],l.p[i],'line']);return o};
 const wseg=[];for(const w of D.water)if(!w.edge)for(let i=1;i<w.p.length;i++)wseg.push([w.p[i-1],w.p[i],'water']);
 const stops=[],fades=[];
 for(const l of L){if(l.r&&(l.r.c==='lane'||l.r.c==='trackdash'))continue;const others=segsOf(L.filter(x=>x.rail===l.rail),l);
  for(const st of[1,0]){const p=l.p,e=st?p[0]:p[p.length-1],b=st?p[Math.min(3,p.length-1)]:p[Math.max(0,p.length-4)];
   let m=1e9;for(const[a,c]of others)m=Math.min(m,sdist(e,a,c));if(m<25)continue;
   const dx=e[0]-b[0],dy=e[1]-b[1],n=Math.hypot(dx,dy)||1,d=[dx/n,dy/n];
   const major=l.r&&['primary','main','highway'].includes(l.r.c),edgeD=Math.min(e[0]-FR[0],FR[2]-e[0],e[1]-FR[1],FR[3]-e[1]),near=edgeD<900;
   let tf=1e9;for(const[k,lim]of[[0,FR[0]],[0,FR[2]],[1,FR[1]],[1,FR[3]]]){if(d[k]){const t=(lim-e[k])/d[k];if(t>0)tf=Math.min(tf,t)}}
   const[tl,hl]=rayHit(e,d,others,Math.min(tf+60,1600)),[tw]=rayHit(e,d,wseg,1e9);
   let t,fade=false;
   if(hl&&tl<tw&&(major||near||tl<320))t=tl+2;
   else if(near&&tf<tw)t=tf+60;
   else if(major||near){t=Math.min(350,tw-40);fade=true}
   else{if(l.rail)stops.push([e,Math.atan2(d[1],d[0])]);continue}
   if(t<=5)continue;const q=[e[0]+d[0]*t,e[1]+d[1]*t];
   if(fade){fades.push({p:[e,q],c:l.rail?'rail':l.r.c});continue}
   if(st)l.p.unshift(q);else l.p.push(q)}}
 return{roads:L.filter(l=>!l.rail).map(l=>({...l.r,p:l.p})),rail:L.filter(l=>l.rail).map(l=>l.p),stops,fades};
}
function prepWater(D){
 const W=D.water.map(w=>{let p=w.p;if(w.id==='penobscot')p=ext(ext(p,1,1500),0,3500);else if(w.id==='river'&&p[0][0]<-5000)p=ext(p,1,1500);return{...w,p}});
 const V=D.valley.map(v=>v.p[0][0]<-5000?{...v,p:ext(v.p,1,1500)}:v);
 const X=extendLines({...D,water:W});
 return{...D,water:W,valley:V,roads:X.roads,rail:X.rail,stops:X.stops,fades:X.fades};
}
function inner(w){return w-Math.min(8,Math.max(1.5,w*.14))}
function chunks(p,n){const L=[0];for(let i=1;i<p.length;i++)L.push(L[i-1]+Math.hypot(p[i][0]-p[i-1][0],p[i][1]-p[i-1][1]));const T=L[L.length-1],out=[];let j=1;for(let c=0;c<n;c++){const a=T*c/n,b=T*(c+1)/n,seg=[];const at=d=>{while(j<p.length-1&&L[j]<d)j++;const i=Math.max(1,j),f=(d-L[i-1])/((L[i]-L[i-1])||1);return[p[i-1][0]+(p[i][0]-p[i-1][0])*f,p[i-1][1]+(p[i][1]-p[i-1][1])*f]};j=1;seg.push(at(a));for(let i=1;i<p.length;i++)if(L[i]>a&&L[i]<b)seg.push(p[i]);j=1;seg.push(at(b));out.push(seg)}return out}
function dirAt(p,st){const a=st?p[0]:p[p.length-1],b=st?p[1]:p[p.length-2];return[a,Math.atan2(a[1]-b[1],a[0]-b[0])]}
const WATER_OPTS={valley:'#dde3c9',valleyRing:'#dde3c9',rings:{n:3,gap:4.5,cap:18,lw:2.6,c:'#a5c3c9'},
 bank:'#5f8c97',bankMin:1.2,water:'#87b0ba',ripple:'#b3cfd4',covered:'#5f8c97',portals:'#5b4e38'};
function drawValley(g,D){const o=WATER_OPTS;
 for(const v of D.valley)el('path',{d:pd(v.p),fill:'none',stroke:o.valley,'stroke-width':v.w,'stroke-linecap':'round','stroke-linejoin':'round'},g);
}
function drawWater(g,D){const o=WATER_OPTS;
 const W=D.water.filter(w=>!w.edge);
 const cap=w=>w.id==='canal'||w.id==='outlet'?'butt':'round';
 const TR=W.filter(w=>w.id==='trib'),MW=W.filter(w=>w.id!=='trib');
 // Fading bank rings: double stroke (colour + paper on top), width capped in screen px.
 for(const w of MW){if(w.w<5)continue;const n=o.rings.n,bg=w.id==='penobscot'||w.id==='canal'?PAL.paper:o.valleyRing;
  for(let i=n;i>=1;i--){const s=x=>`stroke-width:calc(${w.w}px + ${2*i}*min(calc(var(--u)*${o.rings.gap}), ${o.rings.cap}px) - calc(var(--u)*${x}))`;
   el('path',{d:pd(w.p),fill:'none',stroke:o.rings.c,opacity:(1-(i-1)/(n+1)).toFixed(2),style:s(0),'stroke-linecap':cap(w),'stroke-linejoin':'round'},g);
   el('path',{d:pd(w.p),fill:'none',stroke:bg,style:s(o.rings.lw),'stroke-linecap':cap(w),'stroke-linejoin':'round'},g)}}
 for(const w of D.water.filter(w=>w.edge))el('path',{d:pd(w.p),fill:'none',stroke:'#8b968e','stroke-width':w.w,'stroke-linecap':'butt','stroke-linejoin':'round'},g);
 // Brooks taper from a fifth of their width at the source to full width at the mouth.
 if(TR.length){const N=8,parts=TR.map(w=>chunks(w.p,N));
  for(const pass of[0,1])parts.forEach((cs,ti)=>cs.forEach((c,i)=>{const f=(i+1)/N,w=TR[ti].w*(.2+.8*f);
   el('path',{d:pd(c),fill:'none',stroke:pass?o.water:o.bank,style:pass?mx(inner(w).toFixed(2),(.25+.9*f).toFixed(2)):mx(w.toFixed(2),(.55+1.3*f).toFixed(2)),'stroke-linecap':'round','stroke-linejoin':'round'},g)}))}
 for(const w of MW)el('path',{d:pd(w.p),fill:'none',stroke:o.bank,style:mx(w.w,o.bankMin+1),'stroke-linecap':cap(w),'stroke-linejoin':'round'},g);
 for(const w of MW){const iw=inner(w.w);
  el('path',{d:pd(w.p),fill:'none',stroke:o.water,style:mx(iw,o.bankMin),'stroke-linecap':cap(w),'stroke-linejoin':'round'},g);
  // Ripple: a broken hairline down the axis. Never a pattern in stroke — that hung the browser.
  if(w.w>=5)el('path',{d:pd(w.p),fill:'none',stroke:o.ripple,style:`stroke-width:min(${(iw*.35).toFixed(1)}px,calc(var(--u)*1.1));`+dash(9,5),'stroke-linecap':'round'},g)}
 // Canal lock at the intake (double bar), single-bar portals at the other ends.
 const cn=D.water.filter(w=>w.id==='canal'&&!w.edge);
 const bar=(a,ang,len,off)=>{const c=Math.cos(ang),s_=Math.sin(ang),x=a[0]+c*off,y=a[1]+s_*off,nx=-s_*len/2,ny=c*len/2;el('path',{d:`M${x+nx} ${y+ny}L${x-nx} ${y-ny}`,stroke:o.portals,style:mx(6,2.2),'stroke-linecap':'butt'},g)};
 for(const w of cn){for(const[a,ang]of[dirAt(w.p,1),dirAt(w.p,0)]){if(Math.hypot(a[0]+850,a[1]-280)<5){bar(a,ang,46,-14);bar(a,ang,46,-40)}else bar(a,ang,64,-3)}}
}
// --- Roads, rail, bridges (handoff block 2): ochre-filled majors with dark casing,
// paper secondary, dashed tracks; decks generated where a road crosses open water.
const ROADS={highway:{c:['#8b7550',30,5.8],f:['#ecd49e',24,4.2]},main:{c:['#8b7550',22,5],f:['#f0dfb2',17,3.4]},
 primary:{c:['#94825e',19,4.4],f:['#f3e6c3',15,2.9]},secondary:{c:['#aaa491',13,2.4],f:['#fbf8ee',9,1.4]},
 track:{c:['#a39a7d',4,1.2]},trackdash:{c:['#a39a7d',4,1.2,[5,3]]},lane:{c:['#9d8257',3,1.1,[3,3]]}};
const ROAD_OPTS={path:'#9d8257',bridges:{deck:'#f0dfb2',c:'#5b4e38',w:1.2},bridgeC:'#6b5c42',rail:'#5a564b'};
function drawRoads(g,D){const o=ROAD_OPTS,RS=ROADS;
 for(const p of D.paths)el('path',{d:pd(p),fill:'none',stroke:o.path,style:u(1.4)+';'+dash(.1,4),'stroke-linecap':'round'},g);
 const order=['lane','trackdash','track','secondary','primary','main','highway'];
 for(const pass of['c','f'])for(const cl of order)for(const r of D.roads){if(r.c!==cl)continue;const s=RS[cl][pass];if(!s)continue;
  el('path',{d:pd(r.p),fill:'none',stroke:s[0],style:(s[2]?mx(s[1],s[2]):`stroke-width:${s[1]}px`)+(s[3]?';'+dash(...s[3]):''),'stroke-linecap':s[3]?'butt':'round','stroke-linejoin':'round'},g)}
 for(const b of D.bridges){el('path',{d:pd(b.p),fill:'none',stroke:o.bridgeC,'stroke-width':b.w,'stroke-linecap':'butt'},g);el('path',{d:pd(b.p),fill:'none',stroke:'#eadbc2','stroke-width':b.w-6,'stroke-linecap':'butt'},g)}
 for(const[x,y,a,ww,cl]of crossings(D)){const hw=(RS[cl].c?RS[cl].c[1]:10)/2+2,len=ww/2+10,t=el('g',{transform:`translate(${x} ${y}) rotate(${a*180/Math.PI})`},g);
  el('rect',{x:-len,y:-hw,width:2*len,height:2*hw,fill:o.bridges.deck},t);
  for(const sy of[-1,1])el('path',{d:`M${-len-6} ${sy*(hw+5)}L${-len} ${sy*hw}L${len} ${sy*hw}L${len+6} ${sy*(hw+5)}`,fill:'none',stroke:o.bridges.c,style:u(o.bridges.w),'stroke-linejoin':'round'},t)}
 for(const p of D.rail){el('path',{d:pd(p),fill:'none',stroke:o.rail,style:mx(5,3.2),'stroke-linecap':'butt'},g);el('path',{d:pd(p),fill:'none',stroke:PAL.paper,style:mx(2.4,1.6)+';'+dash(6,6)},g)}
 if(D.fades)for(const f of D.fades){const s_=RS[f.c]||RS.secondary,c=f.c==='rail'?o.rail:(s_.c?s_.c[0]:'#999');el('path',{d:pd(f.p),fill:'none',stroke:c,opacity:.7,style:mx(3,1.2)+';'+dash(5,4),'stroke-linecap':'butt'},g)}
 if(D.stops)for(const[e,a]of D.stops){const t=el('g',{transform:`translate(${e[0]} ${e[1]}) rotate(${a*180/Math.PI})`},g);el('path',{d:'M0 -9V9',stroke:o.rail,style:mx(4,2.4)},t)}
}
function drawCovered(g,D){const o=WATER_OPTS;
 for(const c of D.covered){
  el('path',{d:pd(c.p),fill:'none',stroke:o.covered,opacity:.7,style:mx(16,4.6)+';'+dash(6,3.5),'stroke-linecap':'butt'},g);
  el('path',{d:pd(c.p),fill:'none',stroke:o.water,opacity:.45,style:mx(10,2.6),'stroke-linecap':'butt'},g)}
}

// --- Relief (handoff block 3): a warm tonal wash for closed contours over 650 m,
// overlaps accumulate (higher reads warmer), plus dashed form lines from mid zoom.
function drawRelief(g,D){
 const CS=D.contours.filter(c=>c.i===1),isCl=c=>Math.hypot(c.p[0][0]-c.p[c.p.length-1][0],c.p[0][1]-c.p[c.p.length-1][1])<30;
 const big=c=>{const[x0,y0,x1,y1]=bbox(c.p);return Math.max(x1-x0,y1-y0)>650};
 for(const c of CS)if(isCl(c)&&big(c))el('path',{d:pd(c.p,1),fill:'#a08a62',opacity:.075,stroke:'none'},g);
 for(const c of CS)if(!isCl(c)||big(c))el('path',{d:pd(c.p,isCl(c)),fill:'none',stroke:'#a8966f',class:'lod-mid',style:u(.8)+';'+dash(4,3),'stroke-linecap':'round'},g);
}
function bbox(p){let a=1e9,b=1e9,c=-1e9,d=-1e9;for(const[x,y]of p){if(x<a)a=x;if(y<b)b=y;if(x>c)c=x;if(y>d)d=y}return[a,b,c,d]}
// Hill spot heights for the overlay: innermost closed contours, heights are declaredly conceptual.
function peaks(D){
 const cl=D.contours.filter(c=>c.i===1&&Math.hypot(c.p[0][0]-c.p[c.p.length-1][0],c.p[0][1]-c.p[c.p.length-1][1])<30);
 const cen=p=>{let x=0,y=0;for(const q of p){x+=q[0];y+=q[1]}return[x/p.length,y/p.length]};
 const out=[];
 for(const c of cl){const[x,y]=cen(c.p);
  if(cl.some(o=>o!==c&&inPoly(cen(o.p)[0],cen(o.p)[1],c.p)&&o.p.length<c.p.length))continue;
  const depth=cl.filter(o=>o!==c&&inPoly(x,y,o.p)).length;
  if(out.some(q=>Math.hypot(q[0]-x,q[1]-y)<400))continue;
  const wet=D.water.some(w=>{for(let i=1;i<w.p.length;i++)if(sdist([x,y],w.p[i-1],w.p[i])<w.w/2+120)return true;return false});
  if(wet)continue;
  out.push([x,y,45+depth*15+((Math.abs(x*7+y*3)|0)%9)])}
 return out;
}
function inPoly(x,y,p){let c=false;for(let i=0,j=p.length-1;i<p.length;j=i++){const[xi,yi]=p[i],[xj,yj]=p[j];if((yi>y)!==(yj>y)&&x<(xj-xi)*(y-yi)/(yj-yi)+xi)c=!c}return c}
function rng(seed){let s=seed>>>0||1;return()=>{s^=s<<13;s^=s>>>17;s^=s<<5;return(s>>>0)/4294967296}}

// --- Built-up tone (handoff block 4): a 70 m grid cell is painted when its 3×3
// neighbourhood holds 5+ houses; one path, drawn under the buildings.
function drawBuiltUp(g,D){
 const c=70,grid={};for(const b of D.buildings){const k=Math.floor(b[0]/c)+','+Math.floor(b[1]/c);grid[k]=(grid[k]||0)+1}
 let d='';for(const key in grid){const[x,y]=key.split(',').map(Number);let n=0;for(let i=-1;i<=1;i++)for(let j=-1;j<=1;j++)n+=grid[(x+i)+','+(y+j)]||0;if(n>=5)d+='M'+(x*c-8)+' '+(y*c-8)+'h'+(c+16)+'v'+(c+16)+'h'+(-c-16)+'Z'}
 el('path',{d,fill:'#e2c3a4',stroke:'#e2c3a4','stroke-width':44,'stroke-linejoin':'round',opacity:.55},g);
}

// --- Woodland and vegetation (handoff block 5).
function drawForest(g,D,defs){
 const dots=(c,r,pts)=>p=>pts.forEach(([x,y])=>el('circle',{cx:x,cy:y,r,fill:c},p));
 const hatch=pattern(defs,'lithoForest',9,dots('#8ea27f',.85,[[2,2],[7,4.5],[4,8],[9.5,9],[0,6]]));
 const hatch2=pattern(defs,'lithoForest2',7,dots('#6f8a63',1,[[2,2],[7,3],[4,7],[9,8],[5,5]]));
 for(const f of D.forest){const bar=f.t==='barrens',d=pd(f.p,1);
  el('path',{d,fill:bar?'#c4d1af':f.t},g);
  el('path',{d,fill:bar?hatch:hatch2},g);
  if(bar)el('path',{d,fill:'none',stroke:'#a6bb95',style:u(3.2),'stroke-linecap':'round'},g)}
}
function drawVeg(g,D){
 for(const v of D.veg)el('path',{d:pd(v.p),fill:'none',stroke:v.t?'#7a9069':'#95a883','stroke-width':v.t?2:1.8,style:u(v.t?1.1:.8),'stroke-linecap':'round'},g);
}
// Tree crown symbols, deterministic scatter (seed 7), mid zoom and closer.
function trees(D,step,cap,seed){const R=rng(seed),pts=[];for(const f of D.forest){const[a,b,c,d]=bbox(f.p);const st=f.t==='barrens'?step:step*.7;for(let x=a;x<c;x+=st)for(let y=b;y<d;y+=st){const px=x+(R()-.5)*st*.9,py=y+(R()-.5)*st*.9;if(inPoly(px,py,f.p)&&R()>.18)pts.push([px,py,R()])}}if(pts.length>cap){const k=cap/pts.length;return pts.filter(p=>p[2]<k||p[2]>.999)}return pts}
function drawTrees(g,D,defs,cap){
 const id='lithoTree',s=el('g',{id},defs);
 el('circle',{cx:1.8,cy:2.4,r:9,fill:'#5e4e38',opacity:.16},s);
 [[-3,1,5.5],[3,1.5,5.5],[0,-3,6]].forEach(([x,y,r])=>el('circle',{cx:x,cy:y,r,fill:'#a9bd94',stroke:'#7a9069','stroke-width':.8},s));
 const tg=el('g',{class:'lod-mid'},g);
 for(const[x,y,r]of trees(D,80,cap||2600,7))el('use',{href:'#lithoTree',transform:`translate(${x.toFixed(1)} ${y.toFixed(1)}) scale(${(.8+r*.45).toFixed(2)})`},tg);
}
// Conventional signs: marsh tufts around "Wet ground", bamboo around "Bamboo thickets",
// sparse tufts along the valley floor; nothing lands within 8–10 m of water.
function drawSymbols(g,D){
 const rr=rng(23),W=D.water.filter(w=>!w.edge);
 const wet=(x,y,pad)=>W.some(w=>{for(let i=1;i<w.p.length;i++)if(sdist([x,y],w.p[i-1],w.p[i])<w.w/2+pad)return true;return false});
 const marsh=el('g',{class:'lod-mid',stroke:'#6f8a78',fill:'none','stroke-linecap':'round',style:u(.9)},g);
 const bam=el('g',{class:'lod-mid',stroke:'#6f8a63',fill:'none','stroke-linecap':'round',style:u(.9)},g);
 const tuft=(x,y,s)=>el('path',{d:`M${(x-6*s).toFixed(1)} ${y.toFixed(1)}h${(12*s).toFixed(1)}M${x.toFixed(1)} ${y.toFixed(1)}v${(-7*s).toFixed(1)}M${(x-3.5*s).toFixed(1)} ${y.toFixed(1)}l${(-2.5*s).toFixed(1)} ${(-5*s).toFixed(1)}M${(x+3.5*s).toFixed(1)} ${y.toFixed(1)}l${(2.5*s).toFixed(1)} ${(-5*s).toFixed(1)}`},marsh);
 const cane=(x,y,s)=>el('path',{d:`M${x.toFixed(1)} ${y.toFixed(1)}v${(-16*s).toFixed(1)}M${x.toFixed(1)} ${(y-6*s).toFixed(1)}l${(5*s).toFixed(1)} ${(-4*s).toFixed(1)}M${x.toFixed(1)} ${(y-11*s).toFixed(1)}l${(-5*s).toFixed(1)} ${(-3.5*s).toFixed(1)}M${(x-1.5*s).toFixed(1)} ${(y-5*s).toFixed(1)}h${(3*s).toFixed(1)}M${(x-1.5*s).toFixed(1)} ${(y-10*s).toFixed(1)}h${(3*s).toFixed(1)}`},bam);
 const lab=t=>D.labels.find(l=>l.t===t),wg=lab('Wet ground'),bt=lab('Bamboo thickets');
 if(wg){const P=[];let t=0;while(P.length<70&&t++<1400){const a=rr()*6.283,r=260*Math.sqrt(rr()),x=wg.x+Math.cos(a)*r,y=wg.y+10+Math.sin(a)*r;if(wet(x,y,8))continue;if(P.some(q=>Math.hypot(q[0]-x,q[1]-y)<26))continue;P.push([x,y]);tuft(x,y,.8+rr()*.5)}}
 if(bt)for(let i=0;i<14;i++){const a=rr()*6.283,r=230*Math.sqrt(rr()),cx=bt.x+Math.cos(a)*r,cy=bt.y+Math.sin(a)*r+20;if(wet(cx,cy,10))continue;for(let j=0;j<4;j++)cane(cx+(j-1.5)*6+rr()*3,cy+rr()*6,.9+rr()*.4)}
 for(const v of D.valley)for(let i=1;i<v.p.length;i++){const a=v.p[i-1],b=v.p[i],L=Math.hypot(b[0]-a[0],b[1]-a[1]),nx=-(b[1]-a[1])/L,ny=(b[0]-a[0])/L;for(let t=0;t<L;t+=60){if(rr()<.55)continue;const f=t/L,of=(rr()-.5)*v.w*.9,x=a[0]+(b[0]-a[0])*f+nx*of,y=a[1]+(b[1]-a[1])*f+ny*of;if(!wet(x,y,10))tuft(x,y,.8)}}
}

// --- Buildings (handoff block 7): one node set reused via <use>; shadow from mid zoom.
function drawBuildings(g,D,defs){
 const bg=el('g',{id:'lithoBld'},defs);
 for(const[x,y,w,h,a,cl]of D.buildings)if(cl===0)el('rect',{x:-w/2,y:-h/2,width:w,height:h,transform:`translate(${x} ${y}) rotate(${a})`},bg);
 el('use',{href:'#lithoBld',fill:'#5e4e38',opacity:.26,transform:'translate(2.2 2.6)',class:'lod-mid'},g);
 el('use',{href:'#lithoBld',fill:'#b3a48c'},g);
 for(const[x,y,w,h,a,cl,f,s]of D.buildings)if(cl!==0){const t=`translate(${x} ${y}) rotate(${a})`;
  el('rect',{x:-w/2,y:-h/2,width:w,height:h,transform:`translate(3 3.5) `+t,fill:'#5e4e38',opacity:.26},g);
  el('rect',{x:-w/2,y:-h/2,width:w,height:h,transform:t,fill:f,stroke:s||null,'stroke-width':s?1.5:null},g)}
}
function drawMisc(g,D){
 for(const m of D.misc)el('path',{d:pd(m.p,m.close),fill:m.close?(m.fill||'none'):'none',stroke:m.s||'none','stroke-width':m.w,
  'stroke-dasharray':m.dash?m.dash.join(' '):null,'stroke-linecap':'round','stroke-linejoin':'round',class:m.lyr==='buildings'?'buildings':null},g);
}
function drawDots(g,D){
 for(const c of D.dots)el('circle',{cx:c.x,cy:c.y,r:c.r,fill:c.fill||'none',stroke:c.stroke||'none','stroke-width':c.w,class:c.lyr==='buildings'?'buildings':null},g);
}

// --- Marker type badges (handoff block 7): 19 glyphs, assigned by name regex,
// falling back to the category. Swap the regexes for a DB field if one appears.
const IC={house:'M-4.2 0.2L0 -4L4.2 0.2M-3 -0.8V4H3V-0.8',cross:'M0 -4.6V4.6M-3.2 -1.6H3.2',flag:'M-3 4.6V-4.6M-3 -4.3H3.8L2.2 -2L3.8 0.3H-3',book:'M0 -2.8V4M0 -2.8Q-2 -4.3 -4.5 -3.4V3Q-2 2.2 0 4Q2 2.2 4.5 3V-3.4Q2 -4.3 0 -2.8',plus:'M0 -4.2V4.2M-4.2 0H4.2',
 tree:'M0 4.6V1.6M0 -4.6L3.8 1.6H-3.8Z',bridge:'M-5 -1H5M-4 -1V3.5M4 -1V3.5M-4 3.5Q0 -0.5 4 3.5',rail:'M-3.6 -4H3.6V1.6H-3.6ZM-3.6 -1.2H3.6M-2.6 4.6L-1.6 1.6M2.6 4.6L1.6 1.6',tomb:'M-3 4V-0.8A3 3 0 0 1 3 -0.8V4ZM-4.6 4.2H4.6M0 -2V2M-1.4 -0.6H1.4',
 shop:'M-4 -1H4L3.2 4.2H-3.2ZM-2 -1V-2.4A2 2 0 0 1 2 -2.4V-1',civic:'M-4.6 -1.8L0 -4.6L4.6 -1.8ZM-3.4 -0.8V3M0 -0.8V3M3.4 -0.8V3M-4.6 4.2H4.6',factory:'M-4.6 4.2V-0.8L-1.6 1.2V-0.8L1.4 1.2V-4.6H3.6V4.2Z',
 star:'M0 -4.6L1.3 -1.5H4.5L1.9 0.5L2.9 4L0 1.9L-2.9 4L-1.9 0.5L-4.5 -1.5H-1.3Z',cup:'M-4 -2.2H2.8V0.8A3.4 3.4 0 0 1 -4 0.8ZM2.8 -1.2H4.4V0.8H2.8M-4.4 4.4H3.2',alert:'M0 -4.2V1M0 3.4V3.8',clock:'M-4 0A4 4 0 1 0 4 0A4 4 0 1 0 -4 0M0 -2.4V0L1.8 1.4',
 pipe:'M-4 0A4 4 0 1 0 4 0A4 4 0 1 0 -4 0M-1.4 0A1.4 1.4 0 1 0 1.4 0A1.4 1.4 0 1 0 -1.4 0',wave:'M-4.6 -1.2Q-2.3 -3.4 0 -1.2T4.6 -1.2M-4.6 2.6Q-2.3 .4 0 2.6T4.6 2.6',tent:'M-4.6 4.2L0 -4.2L4.6 4.2ZM0 -4.2V4.2',obelisk:'M-1.6 4L-1 -2.8L0 -4.6L1 -2.8L1.6 4ZM-3.2 4.4H3.2'};
const ICR=[['pipe',/cylinder|pumphouse|drain|culvert|standpipe|refrigerator/i],['bridge',/bridge/i],['cross',/church|seminary|baptist/i],['flag',/school/i],['book',/library/i],['plus',/hospital/i],['tomb',/cemetery/i],['rail',/train|station|bus terminal|depot/i],
 ['wave',/dam\b/i],['tent',/camp|smoke-hole|clubhouse/i],['tree',/park|woods|fairgrounds/i],['cup',/nan's|jade|falcon|silver dollar|traveller|black spot/i],['star',/theater|bijou|inn\b|hotel/i],['obelisk',/memorial|settlement/i],
 ['shop',/market|drug|freese|machen|secondhand|washateria|alley|mall|city center/i],['civic',/town house|courthouse|community|army/i],['factory',/ironworks|tool|dump|coal/i],['house',/home|house|farm|heights|cape|broadway|kersh|silver|macklin/i]];
const ICK={Homes:'house',Encounters:'alert',Historical:'clock',Civic:'civic',Outlying:'house',Barrens:'tent'};
function iconOf(name,kind){for(const[k,re]of ICR)if(re.test(name))return k;return ICK[kind]||'alert'}
function badge(g,x,y,color,icon){
 el('circle',{cx:x,cy:y,r:7.5,fill:'#fbf9f1',stroke:color,'stroke-width':1.1,'pointer-events':'none'},g);
 el('path',{d:IC[icon],transform:`translate(${x} ${y}) scale(1.1)`,fill:'none',stroke:color,'stroke-width':1.2,'stroke-linecap':'round','stroke-linejoin':'round','pointer-events':'none'},g);
}

// --- Street names along the road line (handoff block 6). Returns false when the
// road bends too much or is shorter than the text; the caller then falls back.
let RID=0;
function roadLabel(g,lab,view,roads){
 const wx=lab.x,wy=lab.y,ang=-lab.angle*Math.PI/180;let best=null;
 for(const r of roads){if(['lane','trackdash','track'].includes(r.c))continue;
  for(let i=1;i<r.p.length;i++){const a=r.p[i-1],b=r.p[i],d=sdist([wx,wy],a,b);if(d>160)continue;
   let da=Math.abs((((Math.atan2(b[1]-a[1],b[0]-a[0])-ang)%Math.PI)+Math.PI)%Math.PI);da=Math.min(da,Math.PI-da);
   const sc=d+da*260;if(!best||sc<best.sc)best={sc,r,i}}}
 if(!best)return false;
 const p=best.r.p,cum=[0];for(let i=1;i<p.length;i++)cum.push(cum[i-1]+Math.hypot(p[i][0]-p[i-1][0],p[i][1]-p[i-1][1]));
 const a=p[best.i-1],b=p[best.i],sl=cum[best.i]-cum[best.i-1]||1;
 let t=((wx-a[0])*(b[0]-a[0])+(wy-a[1])*(b[1]-a[1]))/(sl*sl);t=Math.max(0,Math.min(1,t));
 const s0=cum[best.i-1]+t*sl,txt=lab.text.toUpperCase(),fs=9,wpx=txt.length*(fs*.68+1.6)+12,h=wpx/2/view.k,T0=cum[cum.length-1];
 let s1=Math.max(0,s0-h),s2=Math.min(T0,s0+h);
 if(s2-s1<2*h*.95){if(s1===0)s2=Math.min(T0,2*h);else s1=Math.max(0,T0-2*h)}
 if(s2-s1<2*h*.95)return false;
 const at=s=>{let i=1;while(i<p.length-1&&cum[i]<s)i++;const f=(s-cum[i-1])/((cum[i]-cum[i-1])||1);return[p[i-1][0]+(p[i][0]-p[i-1][0])*f,p[i-1][1]+(p[i][1]-p[i-1][1])*f]};
 let pts=[at(s1)];for(let i=0;i<p.length;i++)if(cum[i]>s1&&cum[i]<s2)pts.push(p[i]);pts.push(at(s2));
 let turn=0;for(let i=2;i<pts.length;i++){const a1=Math.atan2(pts[i-1][1]-pts[i-2][1],pts[i-1][0]-pts[i-2][0]),a2=Math.atan2(pts[i][1]-pts[i-1][1],pts[i][0]-pts[i-1][0]);let d=Math.abs(a2-a1);if(d>Math.PI)d=2*Math.PI-d;turn+=d}
 if(turn>.9)return false;
 let sp=pts.map(q=>[(q[0]-view.cx)*view.k+view.w/2,(q[1]-view.cy)*view.k+view.h/2]);
 if(sp[sp.length-1][0]<sp[0][0])sp.reverse();
 const id='lithoRP'+(++RID);
 const df=g.querySelector('defs')||el('defs',{},g);
 el('path',{id,d:pd(sp)},df);
 const n=el('text',{class:'halo','stroke-width':3,'font-size':fs,'letter-spacing':1.6,fill:'#6b5c42',dy:3.2,'pointer-events':'none'},g);
 const tp=el('textPath',{href:'#'+id,startOffset:'50%','text-anchor':'middle'},n);tp.textContent=txt;
 return true;
}

window.DerryLitho={el,pd,u,mx,dash,FR,PAL,pattern,updatePatterns,paper,clip,frame,gridRefs,IC,iconOf,badge,roadLabel,
 adapt,prepWater,makeSlots,slotOf,drawValley,drawWater,drawCovered,drawRoads,
 drawRelief,drawBuiltUp,drawForest,drawVeg,drawTrees,drawSymbols,drawBuildings,drawDots,drawMisc,peaks,inner,chunks,dirAt};
})();

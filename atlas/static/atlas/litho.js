// Survey map style (redesign block 12): the sheet, its layers and helpers, ported
// from the Design reference renderer (handoff/blocks/12-cartography/renderer/derry-map.js).
// World coordinates here are screen-oriented (y grows downward), matching the
// inside of #world where map.js already draws geometry as (x, -y_payload).
// Colours live in map.css (.m-* classes over the --map-* tokens), not here.
(function(){
'use strict';
const NS='http://www.w3.org/2000/svg';
function el(t,a,p){const n=document.createElementNS(NS,t);for(const k in a){const v=a[k];if(v!=null&&v!==false)n.setAttribute(k,v)}if(p)p.appendChild(n);return n}
const r1=v=>Math.round(v*10)/10;
function pd(p,z){let s='M'+r1(p[0][0])+' '+r1(p[0][1]);for(let i=1;i<p.length;i++)s+='L'+r1(p[i][0])+' '+r1(p[i][1]);return z?s+'Z':s}
// u(n): stroke width pinned to n screen px at any zoom (map.js sets --u = 1/k px).
// mx(w,n): world width w, but never thinner than n screen px.
const u=n=>`stroke-width:calc(var(--u)*${n})`;
const mx=(w,n)=>`stroke-width:max(${w}px,calc(var(--u)*${n}))`;
const dash=(a,b)=>`stroke-dasharray:calc(var(--u)*${a}) calc(var(--u)*${b})`;
// The sheet frame; content outside is clipped to it.
const FR=[-6150,-3450,3450,4380];
// Zoom levels by k (screen px per metre): far < 0.16 ≤ mid < 0.42 ≤ near; house
// footprints replace the built-up tint from 0.8 (map.js sets data-z / data-bld).
const LOD={far:.16,mid:.42,plan:.8};
// Patterns keep a fixed screen size: cells are authored in screen px, scaled by 1/k on zoom.
const patterns=[];
function makePatterns(defs){
 const wood=el('pattern',{id:'dm-wood',width:10,height:10,patternUnits:'userSpaceOnUse'},defs);
 el('rect',{width:10,height:10,class:'m-wood'},wood);
 el('circle',{cx:2.5,cy:2.5,r:.9,class:'m-wood-dot'},wood);el('circle',{cx:7.5,cy:7.2,r:.9,class:'m-wood-dot'},wood);
 const crown=el('pattern',{id:'dm-crown',width:28,height:28,patternUnits:'userSpaceOnUse'},defs);
 [[6,7,4.2],[19,4,3.4],[14,17,4.6],[3,22,3.2],[24,23,3.8]].forEach(([cx,cy,r])=>el('circle',{cx,cy,r,class:'m-crown'},crown));
 patterns.push(wood,crown);
}
function updatePatterns(k){for(const p of patterns)p.setAttribute('patternTransform',`scale(${1/k})`)}

// --- Sheet: margin under everything, the land clipped to the frame, frame and grid on top.
function paper(world){el('rect',{x:-12000,y:-10000,width:22000,height:22000,class:'m-paper'},world)}
function clip(world,defs){
 const cp=el('clipPath',{id:'clipF'},defs);
 el('rect',{x:FR[0],y:FR[1],width:FR[2]-FR[0],height:FR[3]-FR[1]},cp);
 const sheet=el('g',{'clip-path':'url(#clipF)'},world);
 el('rect',{x:FR[0],y:FR[1],width:FR[2]-FR[0],height:FR[3]-FR[1],class:'m-land'},sheet);
 return sheet;
}
// The 1 km grid inside the sheet (its own slot, over the content) and one frame line.
function grid(g){let d='';for(let x=-6000;x<=FR[2];x+=1000)d+=`M${x} ${FR[1]}V${FR[3]}`;for(let y=-3000;y<=FR[3];y+=1000)d+=`M${FR[0]} ${y}H${FR[2]}`;el('path',{d,class:'m-grid',style:u(.6)},g)}
function frame(world){el('rect',{x:FR[0],y:FR[1],width:FR[2]-FR[0],height:FR[3]-FR[1],class:'m-frame',style:u(1.4)},world)}
// Grid letters A–J / 1–8 for the 1 km squares, stuck to the screen edges; drawn into the overlay every view change.
function gridRefs(g,view){
 const sx=x=>(x-view.cx)*view.k+view.w/2,sy=y=>(y-view.cy)*view.k+view.h/2;
 for(let i=0;i<10;i++){const x=sx(-5500+i*1000);if(x<20||x>view.w-20)continue;el('text',{x:r1(x),y:r1(Math.max(14,sy(FR[1])-8)),class:'gref'},g).textContent='ABCDEFGHIJ'[i]}
 for(let j=0;j<8;j++){const y=sy(-2500+j*1000);if(y<20||y>view.h-20)continue;el('text',{x:r1(Math.max(12,sx(FR[0])-10)),y:r1(y+4),class:'gref'},g).textContent=String(j+1)}
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
  if(cls==='covered'){D.covered.push({p:flip(o.points),w:o.width});continue}
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
  // Other polygons (fields, sand, yards) are areas; the remaining lines are small objects.
 if(o.points&&o.type==='poly'){D.areas.push({p:flip(o.points),fill:o.fill,stroke:o.stroke,w:o.width});continue}
 if(o.points)D.misc.push({p:flip(o.points),fill:o.fill,s:o.stroke,w:o.width,dash:o.dash,lyr:o.layer});
 }
 D.labels=(payload.labels||[]).map(l=>({t:l.text,x:l.x,y:-l.y}));
 return D;
}

// --- Slots: survey paint order (renderer layers 3–16), all inside the clipped sheet.
const SLOT_ORDER=['areas','valley','forest','relief','veg','builtup','symbols','water','buildings','roads','covered','bridges','rail','misc','dots','grid'];
function makeSlots(host){const s={};for(const n of SLOT_ORDER)s[n]=el('g',{class:'slot-'+n},host);return s}
// Payload fills of parks, yards, fields and sand → survey area classes.
const AREA={'#dce2c7':'m-park','#d7cbb5':'m-yard','#d5c7a2':'m-yard','#c3b18c':'m-yard','#e7e1bf':'m-sand','#e0ddc9':'m-field','#d4d4b7':'m-field'};
function drawAreas(g,D){for(const a of D.areas)el('path',{d:pd(a.p,1),class:AREA[a.fill]||'m-field'},g)}

// --- Line ends (renderer prep()): nothing long stops in mid-air. Rivers run out under
// the frame; a loose road or rail end joins the next line if that comes before water,
// else runs out under the frame when it is near, else a major road fades out dashed
// and a rail line ends in a buffer stop; a street may simply end. Lanes and dashed
// tracks are left alone.
function ext(p,st,L){const a=st?p[0]:p[p.length-1],b=st?p[Math.min(3,p.length-1)]:p[Math.max(0,p.length-4)],dx=a[0]-b[0],dy=a[1]-b[1],n=Math.hypot(dx,dy)||1,q=[a[0]+dx/n*L,a[1]+dy/n*L];return st?[q,...p]:[...p,q]}
function sdist(p,a,b){const dx=b[0]-a[0],dy=b[1]-a[1],L=dx*dx+dy*dy||1;let t=((p[0]-a[0])*dx+(p[1]-a[1])*dy)/L;t=Math.max(0,Math.min(1,t));return Math.hypot(a[0]+t*dx-p[0],a[1]+t*dy-p[1])}
function segX(a,b,c,d){const r=[b[0]-a[0],b[1]-a[1]],s=[d[0]-c[0],d[1]-c[1]],den=r[0]*s[1]-r[1]*s[0];if(!den)return null;const t=((c[0]-a[0])*s[1]-(c[1]-a[1])*s[0])/den,q=((c[0]-a[0])*r[1]-(c[1]-a[1])*r[0])/den;return t>=0&&t<=1&&q>=0&&q<=1?[a[0]+t*r[0],a[1]+t*r[1],Math.atan2(r[1],r[0])]:null}
// Nearest crossing of the ray o + t·d with t in (1, maxT); Infinity if none.
function rayHit(o,d,segs,maxT){let best=Infinity;maxT=maxT||Infinity;for(const[a,b]of segs){const sx=b[0]-a[0],sy=b[1]-a[1],den=d[0]*sy-d[1]*sx;if(Math.abs(den)<1e-9)continue;const t=((a[0]-o[0])*sy-(a[1]-o[1])*sx)/den,q=((a[0]-o[0])*d[1]-(a[1]-o[1])*d[0])/den;if(t>1&&t<maxT&&t<best&&q>=0&&q<=1)best=t}return best}
const MAJOR=new Set(['primary','main','highway']),MINOR=new Set(['track','trackdash','lane']);
function prep(D){
 const water=D.water.map(w=>{let p=w.p;if(w.id==='penobscot')p=ext(ext(p,1,1500),0,3500);else if(w.id==='river'&&p[0][0]<-5000)p=ext(p,1,1500);return{...w,p}});
 const valley=D.valley.map(v=>v.p[0][0]<-5000?{...v,p:ext(v.p,1,1500)}:v);
 const L=[...D.roads.map(r=>({r,p:r.p.slice(),rail:false})),...D.rail.filter(p=>p.length>1).map(p=>({p:p.slice(),rail:true}))];
 const segsOf=(skip,rail)=>{const o=[];for(const l of L)if(l!==skip&&l.rail===rail)for(let i=1;i<l.p.length;i++)o.push([l.p[i-1],l.p[i]]);return o};
 const wseg=[];for(const w of water)if(!w.edge)for(let i=1;i<w.p.length;i++)wseg.push([w.p[i-1],w.p[i]]);
 const stops=[],fades=[];
 for(const l of L){if(l.r&&(l.r.c==='lane'||l.r.c==='trackdash'))continue;
  const others=segsOf(l,l.rail),major=l.rail||MAJOR.has(l.r.c);
  for(const st of[true,false]){const p=l.p,e=st?p[0]:p[p.length-1],b=st?p[Math.min(3,p.length-1)]:p[Math.max(0,p.length-4)];
   if(others.some(([a,c])=>sdist(e,a,c)<60))continue;                       // already joined
   const dx=e[0]-b[0],dy=e[1]-b[1],n=Math.hypot(dx,dy)||1,d=[dx/n,dy/n];
   let tf=1e9;for(const[k,lim]of[[0,FR[0]],[0,FR[2]],[1,FR[1]],[1,FR[3]]])if(d[k]){const t=(lim-e[k])/d[k];if(t>0)tf=Math.min(tf,t)}
   const tl=rayHit(e,d,others,Math.min(tf+60,1600)),tw=rayHit(e,d,wseg);
   let t=0,fade=false;
   if(tl<tw&&(major||tl<320))t=tl+2;                                         // join the next line
   else if(tf<(major?2600:900)&&tf<tw)t=tf+60;                               // out under the frame
   else if(major&&!l.rail){t=Math.min(350,tw-40);fade=true}                 // open country or a bank
   else if(l.rail){stops.push([e,Math.atan2(d[1],d[0])]);continue}
   if(t<=5)continue;                                                         // a street that simply ends
   const q=[e[0]+d[0]*t,e[1]+d[1]*t];
   if(fade)fades.push({p:[e,q],c:l.r.c});else if(st)l.p.unshift(q);else l.p.push(q)}}
 return{...D,water,valley,roads:L.filter(l=>!l.rail).map(l=>({...l.r,p:l.p})),rail:L.filter(l=>l.rail).map(l=>l.p),stops,fades};
}
// Split a polyline into n runs of equal length.
function chunks(p,n){
 const acc=[0];for(let i=1;i<p.length;i++)acc.push(acc[i-1]+Math.hypot(p[i][0]-p[i-1][0],p[i][1]-p[i-1][1]));
 const T=acc[acc.length-1],at=s=>{let i=1;while(i<p.length-1&&acc[i]<s)i++;const f=(s-acc[i-1])/((acc[i]-acc[i-1])||1);return[p[i-1][0]+(p[i][0]-p[i-1][0])*f,p[i-1][1]+(p[i][1]-p[i-1][1])*f]};
 const out=[];for(let c=0;c<n;c++){const a=T*c/n,b=T*(c+1)/n,seg=[at(a)];for(let i=1;i<p.length-1;i++)if(acc[i]>a&&acc[i]<b)seg.push(p[i]);seg.push(at(b));out.push(seg)}
 return out;
}
function dirAt(p,st){const a=st?p[0]:p[p.length-1],b=st?p[1]:p[p.length-2];return[a,Math.atan2(a[1]-b[1],a[0]-b[0])]}

// Valley floor: a wide soft band under the stream, world width from the data.
function drawValley(g,D){for(const v of D.valley)el('path',{d:pd(v.p),class:'m-valley',style:`stroke-width:${v.w}px`},g)}
// --- Water: one bank stroke under the fills; brooks taper from the spring; canal and
// outlet have butt ends; near zoom adds a broken current line and the canal lock.
function drawWater(g,D){
 const flows=D.water.filter(w=>w.id!=='trib'),cut=w=>w.id.indexOf('canal')===0||w.id==='outlet'?' is-canal':'';
 for(const w of flows)el('path',{d:pd(w.p),class:'m-water-edge'+cut(w),style:`stroke-width:calc(${w.w}px + var(--u)*2.4)`},g);
 // Brooks in 6 runs, from a fifth of the width at the spring to full width at the mouth.
 const runs=D.water.filter(w=>w.id==='trib').flatMap(w=>chunks(w.p,6).map((c,i)=>[c,w.w*(.2+.8*(i+1)/6),(i+1)/6]));
 for(const[c,w,f]of runs)el('path',{d:pd(c),class:'m-water-edge',style:`stroke-width:calc(${r1(w)}px + var(--u)*${r1(.8+1.6*f)})`},g);
 for(const[c,w,f]of runs)el('path',{d:pd(c),class:'m-water',style:mx(r1(w),r1(.3+.9*f))},g);
 for(const w of flows)el('path',{d:pd(w.p),class:'m-water'+cut(w),style:mx(w.w,2)},g);
 for(const w of D.water)if(w.w>=20&&w.id!=='canal')el('path',{d:pd(w.p),class:'m-ripple lod-near',style:u(1)+';'+dash(14,10)},g);
 // Canal lock at the intake (double bar), single-bar portals at the other ends.
 const bar=(a,ang,len,off)=>{const c=Math.cos(ang),s_=Math.sin(ang),x=a[0]+c*off,y=a[1]+s_*off,nx=-s_*len/2,ny=c*len/2;el('path',{d:`M${r1(x+nx)} ${r1(y+ny)}L${r1(x-nx)} ${r1(y-ny)}`,class:'m-lock lod-near',style:mx(6,2)},g)};
 for(const w of D.water)if(w.id==='canal'&&!w.edge)for(const[a,ang]of[dirAt(w.p,1),dirAt(w.p,0)]){if(Math.hypot(a[0]+850,a[1]-280)<5){bar(a,ang,46,-14);bar(a,ang,46,-40)}else bar(a,ang,64,-3)}
}
// --- Roads: casings for secondary and up, then fills minor to major ([world width m,
// min screen px]); dashed run-outs where a major road meets water; footpaths from mid zoom.
const ROADS={track:[6,1],trackdash:[6,1],lane:[6,1],secondary:[13,1.6],primary:[19,2.4],main:[24,2.8],highway:[30,3.2]};
function drawRoads(g,D){
 const order=Object.keys(ROADS);
 for(const c of order)if(!MINOR.has(c))for(const r of D.roads)if(r.c===c){const[w,m]=ROADS[c];
  el('path',{d:pd(r.p),class:'m-road-cas',style:`stroke-width:max(calc(var(--u)*${m+1.6}),calc(${w}px + var(--u)*1.6))`},g)}
 for(const c of order)for(const r of D.roads)if(r.c===c){const[w,m]=ROADS[c];
  el('path',{d:pd(r.p),class:'m-road m-road--'+c,style:MINOR.has(c)?u(1.1)+(c==='lane'?'':';'+dash(5,3)):mx(w,m)},g)}
 for(const f of D.fades)el('path',{d:pd(f.p),class:'m-road-fade',style:mx((ROADS[f.c]||ROADS.secondary)[0]*.5,1.4)+';'+dash(5,4)},g);
 for(const p of D.paths)el('path',{d:pd(p),class:'m-path lod-mid',style:u(1)+';'+dash(2,3)},g);
}
function drawCovered(g,D){for(const c of D.covered)el('path',{d:pd(c.p),class:'m-covered',style:mx(c.w,2)+';'+dash(4,3)},g)}
// Where roads cross open water at 40° or more: [x,y,roadAngle,waterWidth,roadClass,sinΔ].
// Touches at the ends of a water line (the canal portals, the downtown hub) don't count.
function crossings(D){const out=[];const W=D.water.filter(w=>!w.edge&&w.w>=5);
 for(const r of D.roads){if(r.c==='lane'||r.c==='trackdash')continue;
  for(const w of W){const n=w.p.length;for(let i=1;i<r.p.length;i++)for(let j=1;j<n;j++){const x=segX(r.p[i-1],r.p[i],w.p[j-1],w.p[j]);if(!x)continue;
   if(Math.hypot(x[0]-w.p[0][0],x[1]-w.p[0][1])<15||Math.hypot(x[0]-w.p[n-1][0],x[1]-w.p[n-1][1])<15)continue;
   const wa=Math.atan2(w.p[j][1]-w.p[j-1][1],w.p[j][0]-w.p[j-1][0]),sn=Math.abs(Math.sin(x[2]-wa));
   if(sn<Math.sin(40*Math.PI/180)||out.some(o=>Math.hypot(o[0]-x[0],o[1]-x[1])<40))continue;
   // Both ends of the span must reach the banks: a road drawn along the river bed is no bridge.
   const L=w.w/2/sn+10,off=(e)=>{let m=1e9;for(let q=1;q<n;q++)m=Math.min(m,sdist(e,w.p[q-1],w.p[q]));return m};
   if([-1,1].some(sg=>off([x[0]+sg*L*Math.cos(x[2]),x[1]+sg*L*Math.sin(x[2])])<w.w/2))continue;
   out.push([x[0],x[1],x[2],w.w,r.c,sn])}}}
 return out}
// --- Bridges: the data's decks at every zoom; where a road crosses open water with no
// deck in the data, parapets (two lines with splayed ends) from near zoom.
function drawBridges(g,D){
 for(const b of D.bridges)el('path',{d:pd(b.p),class:'m-bridge',style:mx(r1(b.w*.4),2)},g);
 const mid=D.bridges.map(b=>[(b.p[0][0]+b.p[b.p.length-1][0])/2,(b.p[0][1]+b.p[b.p.length-1][1])/2]);
 for(const[x,y,a,ww,c,sn]of crossings(D)){if(mid.some(m=>Math.hypot(m[0]-x,m[1]-y)<80))continue;
  const hw=(ROADS[c]||ROADS.secondary)[0]/2+3,len=ww/2/sn+8,t=el('g',{class:'lod-near',transform:`translate(${r1(x)} ${r1(y)}) rotate(${r1(a*180/Math.PI)})`},g);
  for(const sy of[-1,1])el('path',{d:`M${-len-5} ${sy*(hw+4)}L${-len} ${sy*hw}L${len} ${sy*hw}L${len+5} ${sy*(hw+4)}`,class:'m-parapet',style:u(1.2)},t)}
}
// --- Rail: one line, ties from mid zoom, an 80 m buffer-stop bar at each terminus.
function drawRail(g,D){
 for(const r of D.rail)el('path',{d:pd(r),class:'m-rail',style:u(1.6)},g);
 el('path',{d:D.ties.map(t=>pd(t)).join(''),class:'m-tie lod-mid',style:u(1.2)},g);
 for(const[e,a]of D.stops){const nx=-Math.sin(a),ny=Math.cos(a);
  el('path',{d:`M${r1(e[0]-nx*40)} ${r1(e[1]-ny*40)}L${r1(e[0]+nx*40)} ${r1(e[1]+ny*40)}`,class:'m-rail-stop',style:'stroke-width:max(10px,calc(var(--u)*2.6))'},g)}
}

// --- Relief: only the bold contour set (the other one duplicates it), thin and pale.
function isClosed(p){return Math.hypot(p[0][0]-p[p.length-1][0],p[0][1]-p[p.length-1][1])<40}
function drawRelief(g,D){
 for(const c of D.contours)if(c.i===1){const z=isClosed(c.p);el('path',{d:pd(c.p,z),class:'m-contour'+(z?' is-closed':''),style:u(.8)},g)}
}
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

// --- Built-up tint below k 0.8: every house joined to every neighbour within 95 m,
// stroked 60 m wide with round caps and joins, so a street of houses reads as one
// smooth band (no beads, no staircase). One path; footprints take over from k 0.8.
function drawBuiltUp(g,D){
 const B=D.buildings,cell=95,grid=new Map();
 B.forEach((b,i)=>{const k=Math.floor(b[0]/cell)+':'+Math.floor(b[1]/cell);(grid.get(k)||grid.set(k,[]).get(k)).push(i)});
 let d='';
 B.forEach((b,i)=>{const gx=Math.floor(b[0]/cell),gy=Math.floor(b[1]/cell);
  d+=`M${r1(b[0])} ${r1(b[1])}h0`;   // a lone house still gets a dot
  for(let ox=-1;ox<=1;ox++)for(let oy=-1;oy<=1;oy++)for(const j of grid.get((gx+ox)+':'+(gy+oy))||[])
   if(j>i&&(B[j][0]-b[0])**2+(B[j][1]-b[1])**2<cell*cell)d+=`M${r1(b[0])} ${r1(b[1])}L${r1(B[j][0])} ${r1(B[j][1])}`});
 el('path',{d,class:'m-builtup lod-massing',style:'stroke-width:60px'},g);
}

// --- Woods: one patterned fill, tree crowns from near zoom, a 1px edge.
function drawForest(g,D){
 const d=D.forest.map(f=>pd(f.p,1)).join('');
 el('path',{d,class:'m-wood-area',fill:'url(#dm-wood)'},g);
 el('path',{d,class:'m-wood-crowns lod-near',fill:'url(#dm-crown)'},g);
 el('path',{d,class:'m-wood-edge',style:u(1)},g);
}
// Wet-ground ticks from mid zoom: short marks, one path.
function drawVeg(g,D){el('path',{d:D.veg.map(v=>pd(v.p)).join(''),class:'m-veg lod-mid',style:u(1)},g)}
// Conventional signs, near zoom only: marsh tufts around "Wet ground", bamboo around
// "Bamboo thickets", sparse tufts along the valley floor; nothing lands within 8–10 m of water.
function drawSymbols(g,D){
 const rr=rng(23),W=D.water.filter(w=>!w.edge);
 const wet=(x,y,pad)=>W.some(w=>{for(let i=1;i<w.p.length;i++)if(sdist([x,y],w.p[i-1],w.p[i])<w.w/2+pad)return true;return false});
 const marsh=el('g',{class:'m-symbol lod-near',style:u(.9)},g),bam=el('g',{class:'m-symbol lod-near',style:u(.9)},g);
 const tuft=(x,y,s)=>el('path',{d:`M${(x-6*s).toFixed(1)} ${y.toFixed(1)}h${(12*s).toFixed(1)}M${x.toFixed(1)} ${y.toFixed(1)}v${(-7*s).toFixed(1)}M${(x-3.5*s).toFixed(1)} ${y.toFixed(1)}l${(-2.5*s).toFixed(1)} ${(-5*s).toFixed(1)}M${(x+3.5*s).toFixed(1)} ${y.toFixed(1)}l${(2.5*s).toFixed(1)} ${(-5*s).toFixed(1)}`},marsh);
 const cane=(x,y,s)=>el('path',{d:`M${x.toFixed(1)} ${y.toFixed(1)}v${(-16*s).toFixed(1)}M${x.toFixed(1)} ${(y-6*s).toFixed(1)}l${(5*s).toFixed(1)} ${(-4*s).toFixed(1)}M${x.toFixed(1)} ${(y-11*s).toFixed(1)}l${(-5*s).toFixed(1)} ${(-3.5*s).toFixed(1)}M${(x-1.5*s).toFixed(1)} ${(y-5*s).toFixed(1)}h${(3*s).toFixed(1)}M${(x-1.5*s).toFixed(1)} ${(y-10*s).toFixed(1)}h${(3*s).toFixed(1)}`},bam);
 const lab=t=>D.labels.find(l=>l.t===t),wg=lab('Wet ground'),bt=lab('Bamboo thickets');
 if(wg){const P=[];let t=0;while(P.length<70&&t++<1400){const a=rr()*6.283,r=260*Math.sqrt(rr()),x=wg.x+Math.cos(a)*r,y=wg.y+10+Math.sin(a)*r;if(wet(x,y,8))continue;if(P.some(q=>Math.hypot(q[0]-x,q[1]-y)<26))continue;P.push([x,y]);tuft(x,y,.8+rr()*.5)}}
 if(bt)for(let i=0;i<14;i++){const a=rr()*6.283,r=230*Math.sqrt(rr()),cx=bt.x+Math.cos(a)*r,cy=bt.y+Math.sin(a)*r+20;if(wet(cx,cy,10))continue;for(let j=0;j<4;j++)cane(cx+(j-1.5)*6+rr()*3,cy+rr()*6,.9+rr()*.4)}
 for(const v of D.valley)for(let i=1;i<v.p.length;i++){const a=v.p[i-1],b=v.p[i],L=Math.hypot(b[0]-a[0],b[1]-a[1]),nx=-(b[1]-a[1])/L,ny=(b[0]-a[0])/L;for(let t=0;t<L;t+=60){if(rr()<.55)continue;const f=t/L,of=(rr()-.5)*v.w*.9,x=a[0]+(b[0]-a[0])*f+nx*of,y=a[1]+(b[1]-a[1])*f+ny*of;if(!wet(x,y,10))tuft(x,y,.8)}}
}

// --- Buildings: footprints from k 0.8 (one path) and landmarks at every zoom (one path).
function drawBuildings(g,D){
 let dB='',dK='';
 for(const[x,y,w,h,ang,cl]of D.buildings){const a=ang*Math.PI/180,c=Math.cos(a),si=Math.sin(a),hw=w/2,hh=h/2;
  const d=pd([[-hw,-hh],[hw,-hh],[hw,hh],[-hw,hh]].map(([p,q])=>[x+p*c-q*si,y+p*si+q*c]),1);
  if(cl)dK+=d;else dB+=d}
 el('path',{d:dB,class:'m-bld lod-plan',style:u(.7)},g);
 el('path',{d:dK,class:'m-bld-key',style:'stroke-width:max(calc(var(--u)*.8),4px)'},g);
}
// Small objects from the data (dam logs, rails, pipes, the ballfield fence): thin lines
// at their world width, near zoom only. Dots (wells, posts, log ends): white with an edge, from mid zoom.
function drawMisc(g,D){
 for(const m of D.misc)el('path',{d:pd(m.p),class:'m-misc lod-near'+(m.lyr==='buildings'?' buildings':''),style:mx(m.w||1,1),
  'stroke-dasharray':m.dash?m.dash.join(' '):null},g);
}
function drawDots(g,D){
 for(const c of D.dots)el('circle',{cx:c.x,cy:c.y,r:c.r,class:'m-dot lod-mid'+(c.lyr==='buildings'?' buildings':''),style:u(1)},g);
}

// --- Street names along the road line (<textPath>). Returns false when the
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
 // Plex Sans Condensed 500, 12px caps with 0.14em tracking: about 0.62em per letter.
 const s0=cum[best.i-1]+t*sl,txt=lab.text.toUpperCase(),fs=12,wpx=txt.length*(fs*.62+fs*.14)+12,h=wpx/2/view.k,T0=cum[cum.length-1];
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
 const n=el('text',{class:'lbl lbl--road',dy:4.2},g);
 const tp=el('textPath',{href:'#'+id,startOffset:'50%','text-anchor':'middle'},n);tp.textContent=txt;
 return true;
}

window.DerryLitho={el,pd,u,mx,dash,FR,LOD,makePatterns,updatePatterns,paper,clip,grid,frame,gridRefs,roadLabel,
 adapt,prep,makeSlots,drawAreas,drawValley,drawWater,drawCovered,drawRoads,drawBridges,drawRail,
 drawRelief,drawBuiltUp,drawForest,drawVeg,drawSymbols,drawBuildings,drawDots,drawMisc,peaks};
})();

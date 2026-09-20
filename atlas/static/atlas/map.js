(async function startAtlas(){

'use strict';
const [response,photoResponse]=await Promise.all([fetch('/api/v1/map/',{cache:'no-cache'}),fetch('/api/v1/photos/',{cache:'no-cache'})]);
if(!response.ok)throw new Error('Map data unavailable ('+response.status+').');
const PAYLOAD=await response.json();
// Photos are a separate data contour; the map still works if they fail to load.
const PHOTOS=photoResponse.ok?(await photoResponse.json()).features:{};
const D=PAYLOAD.data,NS='http://www.w3.org/2000/svg',q=s=>document.querySelector(s),esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const world=q('#world'),map=q('#map'),markers=q('#markers'),labels=q('#landLabels'),photoLayer=q('#photoLayer');
const state={cx:0,cy:0,k:.1,w:1000,h:700,selected:null,view:'city',active:new Set(Object.keys(PAYLOAD.colors)),search:'',names:true,relief:true,buildings:true,photos:true,measuring:false,measure:[]};
// The photo layer steps with zoom: below PHOTO_MIN_K it folds into marker badges, up to
// POLAROID_FULL_K it shows marker-sized medallions (hover pops the polaroid), and close in —
// where few places share the screen — full polaroids.
const PHOTO_MIN_K=.055,POLAROID_FULL_K=.3;
const all=[...D.sites,...D.unplaced.map(s=>({...s,kind:'Unlocated',confidence:'U',short:s.name}))];
function el(tag,attrs={},parent=null){const n=document.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs))if(v!==null&&v!==undefined)n.setAttribute(k,v);if(parent)parent.appendChild(n);return n}
function pathData(pts,close=false){return pts.map((p,i)=>(i?'L':'M')+p[0]+','+(-p[1])).join(' ')+(close?' Z':'')}
function scene(){
 const ex=PAYLOAD.extent;el('image',{x:ex[0],y:-ex[3],width:ex[2]-ex[0],height:ex[3]-ex[1],href:PAYLOAD.relief,class:'relief'},world);
 const lighten=c=>'#'+[1,3,5].map(i=>Math.round(parseInt(c.slice(i,i+2),16)*.62+255*.38).toString(16).padStart(2,'0')).join('');
 for(const o of PAYLOAD.base){let n;const at={fill:o.fill||'none',stroke:o.stroke||'none','stroke-width':o.width||0,'stroke-linecap':'round','stroke-linejoin':'round',class:o.layer||'base'};if(o.dash)at['stroke-dasharray']=o.dash.join(' ');
  if(o.type==='line'||o.type==='poly')n=el('path',{...at,d:pathData(o.points,o.type==='poly')},world);
  else if(o.type==='circle')n=el('circle',{...at,cx:o.x,cy:-o.y,r:o.r},world);
  else if(o.type==='rect')n=el('rect',{...at,x:-o.w/2,y:-o.h/2,width:o.w,height:o.h,transform:`translate(${o.x},${-o.y}) rotate(${-o.angle})`},world);
  // Open water reads flat as one tint; a narrower lighter core over the fill keeps the banks darker.
  if(o.type==='line'&&!o.dash&&o.stroke===PAYLOAD.palette.water)el('path',{d:pathData(o.points),fill:'none',stroke:lighten(o.stroke),'stroke-width':o.width*.5,'stroke-linecap':'round','stroke-linejoin':'round',class:o.layer||'base'},world);
 }
}
function screen(x,y){return [(x-state.cx)*state.k+state.w/2,(state.cy-y)*state.k+state.h/2]}
function geo(x,y){return [state.cx+(x-state.w/2)/state.k,state.cy-(y-state.h/2)/state.k]}
function fit(id){const v=PAYLOAD.views.find(v=>v.id===id);state.view=id;const [a,b,c,d]=v.bounds;state.cx=(a+c)/2;state.cy=(b+d)/2;state.k=Math.min((state.w-60)/(c-a),(state.h-100)/(d-b));render();}
function hits(s){return (s.kind==='Unlocated'||state.active.has(s.kind))&&(!state.search||[s.id,s.name,s.short,s.note,s.period].join(' ').toLowerCase().includes(state.search));}
function format(m){return m>=1000?(m/1000).toLocaleString('en',{maximumFractionDigits:2})+' km':Math.round(m).toLocaleString('en')+' m'}
function intersects(a,b,pad=2){return !(a[2]+pad<b[0]||a[0]-pad>b[2]||a[3]+pad<b[1]||a[1]-pad>b[3])}
function render(){
 const {w,h,k,cx,cy}=state;map.setAttribute('viewBox',`0 0 ${w} ${h}`);world.setAttribute('transform',`translate(${w/2-cx*k},${h/2+cy*k}) scale(${k})`);
 markers.replaceChildren();labels.replaceChildren();const occupied=[],names=[];
 const points=D.sites.filter(hits).filter(s=>state.search||s.id===state.selected||k>.14||s.rank===1||s.kind==='Outlying').sort((a,b)=>(a.id===state.selected?-1:b.id===state.selected?1:a.rank-b.rank||a.id-b.id));
 for(const s of points){const [x,y]=screen(s.x,s.y);if(x<-30||y<-30||x>w+30||y>h+30)continue;let mx=x,my=y,ok=false;
  for(const r of [0,19,33,48]){for(let i=0;i<(r?12:1);i++){const dx=Math.cos(i*Math.PI/6)*r,dy=Math.sin(i*Math.PI/6)*r,bb=[x+dx-9,y+dy-9,x+dx+9,y+dy+9];if(!occupied.some(b=>intersects(bb,b,1))){mx=x+dx;my=y+dy;occupied.push(bb);ok=true;break}}if(ok)break}
  const color=PAYLOAD.colors[s.kind],g=el('g',{class:'mark',tabindex:'0',role:'button','aria-label':s.id+'. '+s.name,'data-id':s.id},markers);
  if(Math.abs(mx-x)+Math.abs(my-y)>2){el('path',{d:`M${x},${y}L${mx},${my}`,stroke:color,'stroke-width':.75,fill:'none','pointer-events':'none'},g);el('circle',{cx:x,cy:y,r:1.7,fill:color},g)}
  if(s.id===state.selected)el('circle',{cx:mx,cy:my,r:14,fill:'#fbf7e0',stroke:'#a88746','stroke-width':2.5},g);
  // A pale halo under each symbol lifts it off busy ground such as the Barrens green.
  if(s.confidence==='C')el('path',{d:`M${mx},${my-12.4}L${mx+12.4},${my}L${mx},${my+12.4}L${mx-12.4},${my}Z`,fill:'#fffef7'},g);
  else el('circle',{cx:mx,cy:my,r:10.5,fill:'#fffef7'},g);
  if(s.confidence==='C')el('path',{d:`M${mx},${my-11}L${mx+11},${my}L${mx},${my+11}L${mx-11},${my}Z`,fill:'#f8f5e8',stroke:color,'stroke-width':1.3},g);
  else el('circle',{cx:mx,cy:my,r:9,fill:s.confidence==='A'?color:'#f8f5e8',stroke:color,'stroke-width':1.3},g);
  const txt=el('text',{x:mx,y:my+3.2,'text-anchor':'middle',fill:s.confidence==='A'?'#fff':color},g);txt.textContent=String(s.id).padStart(2,'0');const title=el('title',{},g);title.textContent=s.name;
  // Sepia dot: photographs exist here, but the view is too far out for polaroids.
  if(state.photos&&PHOTOS[String(s.id)]&&k<=PHOTO_MIN_K)el('circle',{cx:mx+8.2,cy:my-8.2,r:3.4,fill:'#7a6752',stroke:'#fffef7','stroke-width':1.1,'pointer-events':'none'},g);
  g.addEventListener('click',e=>{e.stopPropagation();if(!state.measuring)select(s.id,false)});g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(s.id,false)}});
  if(state.names&&(s.id===state.selected||k>.42||s.rank===1||(k>.2&&s.rank===2)))names.push({s,mx,my});
 }
 photoLayer.replaceChildren();if(state.photos&&k>PHOTO_MIN_K)drawPhotos(occupied);
 for(const {s,mx,my}of names){const tw=s.short.length*6.5;let placed=false;for(const dy of [4,-13]){for(const left of [false,true]){const tx=mx+(left?-14:14),ty=my+dy,bb=[left?tx-tw:tx,ty-11,left?tx:tx+tw,ty+3];if(bb[0]<7||bb[2]>w-7||bb[1]<7||bb[3]>h-7||occupied.some(b=>intersects(bb,b)))continue;const t=el('text',{x:tx,y:ty,'text-anchor':left?'end':'start',class:'map-name'},markers);t.textContent=s.short;occupied.push(bb);placed=true;break}if(placed)break}}
 for(const l of [...PAYLOAD.labels].sort((a,b)=>({region:0,road:1,water:2,land:3}[a.kind]-{region:0,road:1,water:2,land:3}[b.kind]))){if(l.kind==='road'&&k<.15)continue;if(l.views.includes('camp')&&l.kind!=='road'&&k<.40)continue;if(l.kind==='region'&&k>.65)continue;const[x,y]=screen(...[l.x+(l.web_offset?.[0]||0),l.y+(l.web_offset?.[1]||0)]);if(x<10||y<10||x>w-10||y>h-10)continue;const sz=l.kind==='region'?16:11,tw=l.text.length*(sz*.57),a=l.angle*Math.PI/180,ww=Math.abs(tw*Math.cos(a))+Math.abs(sz*Math.sin(a)),hh=Math.abs(tw*Math.sin(a))+Math.abs(sz*Math.cos(a));const bb=[x-ww/2-3,y-hh/2-3,x+ww/2+3,y+hh/2+3];if(occupied.some(b=>intersects(bb,b,3)))continue;occupied.push(bb);const t=el('text',{x,y,transform:`rotate(${-l.angle} ${x} ${y})`,'text-anchor':'middle',class:'map-road',style:l.kind==='region'?'font:600 16px Georgia,serif':l.kind==='water'?'font-style:italic;fill:#507e89':''},labels);t.textContent=l.text;}
 const target=130/k,base=10**Math.floor(Math.log10(target)),n=[1,2,5,10].filter(x=>x*base<=target).pop()||1,val=n*base;q('#scaleLine').style.width=(val*k)+'px';q('#scaleText').textContent=format(val);
 document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===state.view));
 drawMeasure();
}
// The photo layer: polaroids pinned to the map, tilt fixed per place so nothing jitters.
// Mid zoom draws marker-sized medallions instead and keeps the polaroid as a hover pop-up.
function drawPhotos(occupied){
 if(!q('#photoClip')){const defs=el('defs',{},map);const cp=el('clipPath',{id:'photoClip'},defs);el('circle',{r:11},cp)}
 const full=state.k>=POLAROID_FULL_K,FR=46,FH=57,IMG=40,R=12;
 // Medallions search rings of positions (top first) like markers do; a ring of 24 clears
 // the place's own marker, whose occupied box reaches 9+pad from the anchor.
 const offs=full?[[0,-46],[36,-36],[-36,-36],[44,0],[-44,0],[0,48],[36,38],[-36,38]]:[];
 if(!full)for(const r of [24,34,46])for(let i=0;i<12;i++){const a=-Math.PI/2+i*Math.PI/6;offs.push([Math.cos(a)*r,Math.sin(a)*r])}
 const bw=full?FR/2+2:R+2,bh=full?FH/2+2:R+2;
 for(const [key,f] of Object.entries(PHOTOS)){
  if(!f.anchor)continue;const [ax,ay]=screen(f.anchor[0],f.anchor[1]);
  if(ax<-60||ay<-60||ax>state.w+60||ay>state.h+60)continue;
  let px=null,py=null;
  for(const [dx,dy] of offs){const nx=ax+dx,ny=ay+dy,bb=[nx-bw,ny-bh,nx+bw,ny+bh];
   if(!occupied.some(b=>intersects(bb,b,1))){px=nx;py=ny;occupied.push(bb);break}}
  if(px===null)continue;
  const p0=f.photos[0];let hsh=0;for(const c of key)hsh=(hsh*31+c.charCodeAt(0))%997;const tilt=hsh%7-3;
  el('path',{d:`M${ax},${ay}L${px},${py}`,stroke:'#8a7a5c','stroke-width':.8,fill:'none'},photoLayer);
  el('circle',{cx:ax,cy:ay,r:1.8,fill:'#8a7a5c'},photoLayer);
  const g=el('g',{class:'polaroid',transform:`translate(${px},${py})`,tabindex:'0',role:'button','data-key':key,'aria-label':'Photographs · '+f.name},photoLayer);
  if(!full){const m=el('g',{class:'medallion'},g);
   el('circle',{r:R+.5,fill:'#fffef7',stroke:'#c9c0a4','stroke-width':.7},m);
   el('image',{href:p0.thumb,x:-R+1,y:-R+1,width:2*R-2,height:2*R-2,'clip-path':'url(#photoClip)',preserveAspectRatio:'xMidYMid slice'},m)}
  const t=el('g',{class:'polaroid-tilt'+(full?'':' pop'),style:'--tilt:'+tilt+'deg'},g);
  el('rect',{x:-FR/2,y:-FH/2,width:FR,height:FH,fill:'#fffef7',stroke:'#c9c0a4','stroke-width':.7},t);
  el('image',{href:p0.thumb,x:-IMG/2,y:-FH/2+3,width:IMG,height:IMG,preserveAspectRatio:'xMidYMid slice'},t);
  // The white bottom strip carries the caption a real polaroid would: year and count.
  const strip=[p0.year,f.photos.length>1?'×'+f.photos.length:''].filter(Boolean).join(' · ');
  if(strip){const yr=el('text',{x:0,y:FH/2-4.5,'text-anchor':'middle',class:'polaroid-year'},t);yr.textContent=strip}
  const title=el('title',{},g);title.textContent=f.name+(p0.caption?' — '+p0.caption:'');
  g.addEventListener('pointerenter',()=>{if(g!==photoLayer.lastElementChild)photoLayer.appendChild(g)});
  g.addEventListener('click',e=>{e.stopPropagation();if(!state.measuring)openPhotoFeature(key)});
  g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openPhotoFeature(key)}});
 }
}
// A polaroid opens the place card when the place has one; roads and other outlines go to the gallery.
function openPhotoFeature(key){const f=PHOTOS[key];if(!f)return;if(f.object_type==='site')select(Number(key),false);else if(f.object_type==='unplaced')select(key,false);else location.href='/photos/?place='+key}
function list(){const result=all.filter(hits);q('#count').textContent=result.length+' places · '+D.sites.filter(hits).length+' mapped';q('#list').innerHTML=result.length?result.map(s=>`<li><button data-place="${s.id}" class="${state.selected===s.id?'selected':''}"><span class="num" style="color:${PAYLOAD.colors[s.kind]||'#697166'}">${String(s.id).padStart(2,'0')}</span><span><span class="item-title">${esc(s.name)}</span><span class="item-sub">${esc(s.period)} · ${s.confidence==='U'?'Unlocated / off map':s.confidence+' location'}</span></span></button></li>`).join(''):'<li class="empty">No matching places. Try a shorter name or enable more categories.</li>';q('#list').querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>select(/^U/.test(b.dataset.place)?b.dataset.place:Number(b.dataset.place),true)));}
function select(id,focus){const s=all.find(s=>s.id===id);if(!s)return;state.selected=id;q('#intro').hidden=true;const panel=q('#detail');panel.hidden=false;const conf={A:'A · Text-anchored relationship',B:'B · Inferred position',C:'C · Proposed location',U:'U · Unlocated / off map'};
 const refs=[];for(const r of s.sources||[]){const g=refs.find(g=>g.reference===r.reference);if(g){if(r.note)g.notes.push(r.note)}else refs.push({reference:r.reference,notes:r.note?[r.note]:[]})}
 const fp=PHOTOS[String(s.id)];
 const photoRow=fp?`<div class="card-photos">${fp.photos.map(p=>`<a class="card-photo" href="/photos/${p.id}/" title="${esc(p.caption)}"><img src="${esc(p.thumb)}" alt="${esc(p.caption||s.name)}" loading="lazy"></a>`).join('')}</div><p class="card-photos-more"><a href="/photos/?place=${esc(String(s.id))}">All photographs of this place →</a></p>`:'';
 panel.innerHTML=`<div class="detail-top"><div><div class="eyebrow">Place ${esc(String(s.id).padStart(2,'0'))}</div><h2>${esc(s.name)}</h2></div><button class="close" id="closeDetail" aria-label="Close place">×</button></div><div class="meta">${esc(s.period)}</div><p><span class="badge">${conf[s.confidence]}</span></p><p>${esc(s.note)}</p>${photoRow}<details open><summary>Sources & evidence</summary><ul class="refs">${refs.length?refs.map(g=>`<li>${esc(g.reference)}${g.notes.map(n=>'<br>'+esc(n)).join('')}</li>`).join(''):`<li>${esc(s.reference)}</li>`}</ul></details>`;
 q('#closeDetail').onclick=closeDetail;q('#scroll').scrollTop=0;
 if(typeof id==='number'&&focus){state.cx=s.x;state.cy=s.y;state.k=Math.max(state.k,.48);state.view='';}
 list();render();if(matchMedia('(max-width:780px)').matches&&!q('#workspace').classList.contains('open')){q('#workspace').classList.add('open');q('#placesToggle').setAttribute('aria-expanded','true');state.panelAutoOpened=true;}
}
function closeDetail(){state.selected=null;q('#detail').hidden=true;q('#intro').hidden=false;if(state.panelAutoOpened){state.panelAutoOpened=false;q('#workspace').classList.remove('open');q('#placesToggle').setAttribute('aria-expanded','false');}list();render()}
function zoom(f,x=state.w/2,y=state.h/2){const [gx,gy]=geo(x,y);state.k=Math.min(4,Math.max(.012,state.k*f));state.cx=gx-(x-state.w/2)/state.k;state.cy=gy+(y-state.h/2)/state.k;state.view='';render()}
function showToast(msg){q('#toast').textContent=msg;q('#toast').hidden=!msg}
function drawMeasure(){const layer=q('#measureLayer');layer.replaceChildren();if(!state.measure.length)return;state.measure.forEach(p=>{const[x,y]=screen(...p);el('circle',{cx:x,cy:y,r:4,fill:'#a34b35',stroke:'#fff','stroke-width':1.3},layer)});if(state.measure.length===2){const a=screen(...state.measure[0]),b=screen(...state.measure[1]);el('path',{d:`M${a}L${b}`,fill:'none',stroke:'#a34b35','stroke-width':2,'stroke-dasharray':'5 3'},layer);showToast(format(Math.hypot(state.measure[0][0]-state.measure[1][0],state.measure[0][1]-state.measure[1][1]))+' · straight line in this reconstruction');}}
function toggleMeasure(force){state.measuring=force===undefined?!state.measuring:force;state.measure=[];q('#measure').classList.toggle('on',state.measuring);q('#measure').setAttribute('aria-pressed',state.measuring);map.classList.toggle('measuring',state.measuring);showToast(state.measuring?'Select two points to measure. Drag to pan. Escape clears.':'');render()}
scene();
q('#methodGeometry').textContent=D.method_geometry;
q('#filters').innerHTML=Object.keys(PAYLOAD.colors).map(c=>`<label><input type="checkbox" checked data-kind="${c}">${c}</label>`).join('');q('#filters').querySelectorAll('input').forEach(x=>x.onchange=()=>{x.checked?state.active.add(x.dataset.kind):state.active.delete(x.dataset.kind);list();render()});
q('#sources').innerHTML=D.web_sources.map(s=>`<div class="source"><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${s.id} · ${esc(s.title)}</a><p>${esc(s.role)}</p></div>`).join('');
q('#search').oninput=e=>{state.search=e.target.value.trim().toLowerCase();q('#clearSearch').hidden=!e.target.value;list();render()};q('#clearSearch').onclick=()=>{q('#search').value='';state.search='';q('#clearSearch').hidden=true;list();render();q('#search').focus()};
q('#showPhotos').onchange=e=>{state.photos=e.target.checked;render()};q('#showNames').onchange=e=>{state.names=e.target.checked;render()};q('#showRelief').onchange=e=>{world.querySelectorAll('.relief').forEach(n=>n.style.display=e.target.checked?'':'none')};q('#showBuildings').onchange=e=>{world.querySelectorAll('.buildings').forEach(n=>n.style.display=e.target.checked?'':'none')};
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>fit(b.dataset.view));q('#zoomIn').onclick=()=>zoom(1.4);q('#zoomOut').onclick=()=>zoom(1/1.4);q('#reset').onclick=()=>fit('city');q('#measure').onclick=()=>toggleMeasure();
q('#aboutBtn').onclick=()=>q('#about').showModal();q('#closeAbout').onclick=()=>q('#about').close();q('#placesToggle').onclick=()=>{const open=q('#workspace').classList.toggle('open');q('#placesToggle').setAttribute('aria-expanded',open);state.panelAutoOpened=false};
q('#panelClose').onclick=()=>{state.panelAutoOpened=false;q('#workspace').classList.remove('open');q('#placesToggle').setAttribute('aria-expanded','false')};
const pointers=new Map();let last=null,start=null,moved=false,lastPinch=0,hadPinch=false;
function local(e){const r=map.getBoundingClientRect();return [e.clientX-r.left,e.clientY-r.top]}
map.addEventListener('pointerdown',e=>{if(e.button!==0)return;const p=local(e);pointers.set(e.pointerId,p);map.setPointerCapture(e.pointerId);start=p;last=p;moved=false;if(pointers.size>1){hadPinch=true;const v=[...pointers.values()];lastPinch=Math.hypot(v[0][0]-v[1][0],v[0][1]-v[1][1])}map.classList.add('dragging')});
map.addEventListener('pointermove',e=>{if(!pointers.has(e.pointerId))return;const p=local(e);pointers.set(e.pointerId,p);if(pointers.size===2){const v=[...pointers.values()],d=Math.hypot(v[0][0]-v[1][0],v[0][1]-v[1][1]);if(lastPinch>0&&d>0)zoom(d/lastPinch,(v[0][0]+v[1][0])/2,(v[0][1]+v[1][1])/2);lastPinch=d;moved=true;return}if(last){const dx=p[0]-last[0],dy=p[1]-last[1];if(start&&Math.hypot(p[0]-start[0],p[1]-start[1])>4)moved=true;if(moved){state.cx-=dx/state.k;state.cy+=dy/state.k;state.view='';render()}}last=p});
map.addEventListener('pointerup',e=>{const p=local(e),wasMoved=moved||hadPinch;pointers.delete(e.pointerId);if(!pointers.size){map.classList.remove('dragging');last=null;lastPinch=0;hadPinch=false}else last=[...pointers.values()][0];if(state.measuring&&!wasMoved){if(state.measure.length===2)state.measure=[];state.measure.push(geo(...p));drawMeasure()}if(!state.measuring&&!wasMoved){const hit=document.elementFromPoint(e.clientX,e.clientY);const pol=hit?.closest('.polaroid');if(pol)openPhotoFeature(pol.dataset.key);else{const target=hit?.closest('.mark');if(target)select(Number(target.dataset.id),false)}}});
map.addEventListener('pointercancel',e=>{pointers.delete(e.pointerId);last=null;map.classList.remove('dragging')});
map.addEventListener('wheel',e=>{e.preventDefault();zoom(Math.exp(-Math.max(-120,Math.min(120,e.deltaY))*.003),...local(e))},{passive:false});map.addEventListener('dblclick',e=>{if(!state.measuring&&!e.target.closest('.mark,.polaroid'))zoom(1.8,...local(e))});
map.addEventListener('keydown',e=>{if(e.key==='+'||e.key==='='){e.preventDefault();zoom(1.4)}else if(e.key==='-'){e.preventDefault();zoom(1/1.4)}else if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();state.cx+=({'ArrowLeft':-80,'ArrowRight':80}[e.key]||0)/state.k;state.cy+=({'ArrowUp':80,'ArrowDown':-80}[e.key]||0)/state.k;state.view='';render()}});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(state.measuring)toggleMeasure(false);else closeDetail()}});
// Deep link from the photo gallery: /?place=12 or /?place=U3 opens the place card.
function deepLink(){const p=new URLSearchParams(location.search).get('place');if(p)select(/^\d+$/.test(p)?Number(p):p,true)}
new ResizeObserver(entries=>{const r=entries[0].contentRect;state.w=r.width;state.h=r.height;if(!state.ready){state.ready=true;fit('city');deepLink()}else render()}).observe(q('.stage'));
list();
// Exposed read-only diagnostics make the offline artifact easy to validate.
window.DerryAtlas={get revision(){return PAYLOAD.revision},get siteCount(){return D.sites.length},get unlocatedCount(){return D.unplaced.length},get photoFeatureCount(){return Object.keys(PHOTOS).length},get view(){return {...state,active:[...state.active]}},select,fit,format};

})().catch(error=>{const el=document.querySelector('#toast');el.hidden=false;el.textContent=error.message+' Please reload the page.';console.error(error);});

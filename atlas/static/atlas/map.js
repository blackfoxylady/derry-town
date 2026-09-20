(async function startAtlas(){

'use strict';
const response=await fetch('/api/v1/map/',{cache:'no-cache'});
if(!response.ok)throw new Error('Map data unavailable ('+response.status+').');
const PAYLOAD=await response.json();
const D=PAYLOAD.data,NS='http://www.w3.org/2000/svg',q=s=>document.querySelector(s),esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const world=q('#world'),map=q('#map'),markers=q('#markers'),labels=q('#landLabels');
const state={cx:0,cy:0,k:.1,w:1000,h:700,selected:null,view:'city',active:new Set(Object.keys(PAYLOAD.colors)),search:'',names:true,relief:true,buildings:true,measuring:false,measure:[]};
const all=[...D.sites,...D.unplaced.map(s=>({...s,kind:'Unlocated',confidence:'U',short:s.name}))];
function el(tag,attrs={},parent=null){const n=document.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs))if(v!==null&&v!==undefined)n.setAttribute(k,v);if(parent)parent.appendChild(n);return n}
function pathData(pts,close=false){return pts.map((p,i)=>(i?'L':'M')+p[0]+','+(-p[1])).join(' ')+(close?' Z':'')}
function scene(){
 const ex=PAYLOAD.extent;el('image',{x:ex[0],y:-ex[3],width:ex[2]-ex[0],height:ex[3]-ex[1],href:PAYLOAD.relief,class:'relief'},world);
 for(const o of PAYLOAD.base){let n;const at={fill:o.fill||'none',stroke:o.stroke||'none','stroke-width':o.width||0,'stroke-linecap':'round','stroke-linejoin':'round',class:o.layer||'base'};if(o.dash)at['stroke-dasharray']=o.dash.join(' ');
  if(o.type==='line'||o.type==='poly')n=el('path',{...at,d:pathData(o.points,o.type==='poly')},world);
  else if(o.type==='circle')n=el('circle',{...at,cx:o.x,cy:-o.y,r:o.r},world);
  else if(o.type==='rect')n=el('rect',{...at,x:-o.w/2,y:-o.h/2,width:o.w,height:o.h,transform:`translate(${o.x},${-o.y}) rotate(${-o.angle})`},world);
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
  if(s.confidence==='C')el('path',{d:`M${mx},${my-11}L${mx+11},${my}L${mx},${my+11}L${mx-11},${my}Z`,fill:'#f8f5e8',stroke:color,'stroke-width':1.3},g);
  else el('circle',{cx:mx,cy:my,r:9,fill:s.confidence==='A'?color:'#f8f5e8',stroke:color,'stroke-width':1.3},g);
  const txt=el('text',{x:mx,y:my+3.2,'text-anchor':'middle',fill:s.confidence==='A'?'#fff':color},g);txt.textContent=String(s.id).padStart(2,'0');const title=el('title',{},g);title.textContent=s.name;
  g.addEventListener('click',e=>{e.stopPropagation();if(!state.measuring)select(s.id,false)});g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(s.id,false)}});
  if(state.names&&(s.id===state.selected||k>.42||s.rank===1||(k>.2&&s.rank===2)))names.push({s,mx,my});
 }
 for(const {s,mx,my}of names){const tw=s.short.length*6.5;let placed=false;for(const dy of [4,-13]){for(const left of [false,true]){const tx=mx+(left?-14:14),ty=my+dy,bb=[left?tx-tw:tx,ty-11,left?tx:tx+tw,ty+3];if(bb[0]<7||bb[2]>w-7||bb[1]<7||bb[3]>h-7||occupied.some(b=>intersects(bb,b)))continue;const t=el('text',{x:tx,y:ty,'text-anchor':left?'end':'start',class:'map-name'},markers);t.textContent=s.short;occupied.push(bb);placed=true;break}if(placed)break}}
 for(const l of [...PAYLOAD.labels].sort((a,b)=>({region:0,road:1,water:2,land:3}[a.kind]-{region:0,road:1,water:2,land:3}[b.kind]))){if(l.kind==='road'&&k<.15)continue;if(l.views.includes('camp')&&l.kind!=='road'&&k<.40)continue;if(l.kind==='region'&&k>.65)continue;const[x,y]=screen(...[l.x+(l.web_offset?.[0]||0),l.y+(l.web_offset?.[1]||0)]);if(x<10||y<10||x>w-10||y>h-10)continue;const sz=l.kind==='region'?16:11,tw=l.text.length*(sz*.57),a=l.angle*Math.PI/180,ww=Math.abs(tw*Math.cos(a))+Math.abs(sz*Math.sin(a)),hh=Math.abs(tw*Math.sin(a))+Math.abs(sz*Math.cos(a));const bb=[x-ww/2-3,y-hh/2-3,x+ww/2+3,y+hh/2+3];if(occupied.some(b=>intersects(bb,b,3)))continue;occupied.push(bb);const t=el('text',{x,y,transform:`rotate(${-l.angle} ${x} ${y})`,'text-anchor':'middle',class:'map-road',style:l.kind==='region'?'font:600 16px Georgia,serif':l.kind==='water'?'font-style:italic;fill:#507e89':''},labels);t.textContent=l.text;}
 const target=130/k,base=10**Math.floor(Math.log10(target)),n=[1,2,5,10].filter(x=>x*base<=target).pop()||1,val=n*base;q('#scaleLine').style.width=(val*k)+'px';q('#scaleText').textContent=format(val);
 document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===state.view));
 drawMeasure();
}
function list(){const result=all.filter(hits);q('#count').textContent=result.length+' places · '+D.sites.filter(hits).length+' mapped';q('#list').innerHTML=result.length?result.map(s=>`<li><button data-place="${s.id}" class="${state.selected===s.id?'selected':''}"><span class="num" style="color:${PAYLOAD.colors[s.kind]||'#697166'}">${String(s.id).padStart(2,'0')}</span><span><span class="item-title">${esc(s.name)}</span><span class="item-sub">${esc(s.period)} · ${s.confidence==='U'?'Unlocated / off map':s.confidence+' location'}</span></span></button></li>`).join(''):'<li class="empty">No matching places. Try a shorter name or enable more categories.</li>';q('#list').querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>select(/^U/.test(b.dataset.place)?b.dataset.place:Number(b.dataset.place),true)));}
function select(id,focus){const s=all.find(s=>s.id===id);if(!s)return;state.selected=id;q('#intro').hidden=true;const panel=q('#detail');panel.hidden=false;const conf={A:'A · Text-anchored relationship',B:'B · Inferred position',C:'C · Proposed location',U:'U · Unlocated / off map'};
 panel.innerHTML=`<div class="detail-top"><div><div class="eyebrow">Place ${esc(String(s.id).padStart(2,'0'))}</div><h2>${esc(s.name)}</h2></div><button class="close" id="closeDetail" aria-label="Close place">×</button></div><div class="meta">${esc(s.period)}</div><p><span class="badge">${conf[s.confidence]}</span></p><p>${esc(s.note)}</p><details open><summary>Sources & evidence</summary><ul class="refs">${s.sources?s.sources.map(r=>`<li>${esc(r.reference)}<br>${r.paragraph===null?'':`<b>P${String(r.paragraph).padStart(5,'0')}</b>`}${r.note?'<br>'+esc(r.note):''}</li>`).join(''):`<li>${esc(s.reference)}</li>`}</ul></details><p class="note">P numbers identify paragraphs in the supplied EPUB extraction, not printed pages. Every plotted coordinate is reconstructed.</p>`;
 q('#closeDetail').onclick=closeDetail;q('#scroll').scrollTop=0;
 if(typeof id==='number'&&focus){state.cx=s.x;state.cy=s.y;state.k=Math.max(state.k,.48);state.view='';}
 list();render();if(matchMedia('(max-width:780px)').matches){q('#workspace').classList.add('open');q('#placesToggle').setAttribute('aria-expanded','true');}
}
function closeDetail(){state.selected=null;q('#detail').hidden=true;q('#intro').hidden=false;list();render()}
function zoom(f,x=state.w/2,y=state.h/2){const [gx,gy]=geo(x,y);state.k=Math.min(4,Math.max(.012,state.k*f));state.cx=gx-(x-state.w/2)/state.k;state.cy=gy+(y-state.h/2)/state.k;state.view='';render()}
function showToast(msg){q('#toast').textContent=msg;q('#toast').hidden=!msg}
function drawMeasure(){const layer=q('#measureLayer');layer.replaceChildren();if(!state.measure.length)return;state.measure.forEach(p=>{const[x,y]=screen(...p);el('circle',{cx:x,cy:y,r:4,fill:'#a34b35',stroke:'#fff','stroke-width':1.3},layer)});if(state.measure.length===2){const a=screen(...state.measure[0]),b=screen(...state.measure[1]);el('path',{d:`M${a}L${b}`,fill:'none',stroke:'#a34b35','stroke-width':2,'stroke-dasharray':'5 3'},layer);showToast(format(Math.hypot(state.measure[0][0]-state.measure[1][0],state.measure[0][1]-state.measure[1][1]))+' · straight line in this reconstruction');}}
function toggleMeasure(force){state.measuring=force===undefined?!state.measuring:force;state.measure=[];q('#measure').classList.toggle('on',state.measuring);q('#measure').setAttribute('aria-pressed',state.measuring);map.classList.toggle('measuring',state.measuring);showToast(state.measuring?'Select two points to measure. Drag to pan. Escape clears.':'');render()}
scene();
q('#methodGeometry').textContent=D.method_geometry;
q('#filters').innerHTML=Object.keys(PAYLOAD.colors).map(c=>`<label><input type="checkbox" checked data-kind="${c}">${c}</label>`).join('');q('#filters').querySelectorAll('input').forEach(x=>x.onchange=()=>{x.checked?state.active.add(x.dataset.kind):state.active.delete(x.dataset.kind);list();render()});
q('#sources').innerHTML=D.web_sources.map(s=>`<div class="source"><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${s.id} · ${esc(s.title)}</a><p>${esc(s.role)}</p></div>`).join('');
q('#search').oninput=e=>{state.search=e.target.value.trim().toLowerCase();list();render()};q('#clearSearch').onclick=()=>{q('#search').value='';state.search='';list();render();q('#search').focus()};
q('#showNames').onchange=e=>{state.names=e.target.checked;render()};q('#showRelief').onchange=e=>{world.querySelectorAll('.relief').forEach(n=>n.style.display=e.target.checked?'':'none')};q('#showBuildings').onchange=e=>{world.querySelectorAll('.buildings').forEach(n=>n.style.display=e.target.checked?'':'none')};
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>fit(b.dataset.view));q('#zoomIn').onclick=()=>zoom(1.4);q('#zoomOut').onclick=()=>zoom(1/1.4);q('#reset').onclick=()=>fit('city');q('#measure').onclick=()=>toggleMeasure();
q('#aboutBtn').onclick=()=>q('#about').showModal();q('#closeAbout').onclick=()=>q('#about').close();q('#placesToggle').onclick=()=>{const open=q('#workspace').classList.toggle('open');q('#placesToggle').setAttribute('aria-expanded',open)};
const pointers=new Map();let last=null,start=null,moved=false,lastPinch=0,hadPinch=false;
function local(e){const r=map.getBoundingClientRect();return [e.clientX-r.left,e.clientY-r.top]}
map.addEventListener('pointerdown',e=>{if(e.button!==0)return;const p=local(e);pointers.set(e.pointerId,p);map.setPointerCapture(e.pointerId);start=p;last=p;moved=false;if(pointers.size>1){hadPinch=true;const v=[...pointers.values()];lastPinch=Math.hypot(v[0][0]-v[1][0],v[0][1]-v[1][1])}map.classList.add('dragging')});
map.addEventListener('pointermove',e=>{if(!pointers.has(e.pointerId))return;const p=local(e);pointers.set(e.pointerId,p);if(pointers.size===2){const v=[...pointers.values()],d=Math.hypot(v[0][0]-v[1][0],v[0][1]-v[1][1]);if(lastPinch>0&&d>0)zoom(d/lastPinch,(v[0][0]+v[1][0])/2,(v[0][1]+v[1][1])/2);lastPinch=d;moved=true;return}if(last){const dx=p[0]-last[0],dy=p[1]-last[1];if(start&&Math.hypot(p[0]-start[0],p[1]-start[1])>4)moved=true;if(moved){state.cx-=dx/state.k;state.cy+=dy/state.k;state.view='';render()}}last=p});
map.addEventListener('pointerup',e=>{const p=local(e),wasMoved=moved||hadPinch;pointers.delete(e.pointerId);if(!pointers.size){map.classList.remove('dragging');last=null;lastPinch=0;hadPinch=false}else last=[...pointers.values()][0];if(state.measuring&&!wasMoved){if(state.measure.length===2)state.measure=[];state.measure.push(geo(...p));drawMeasure()}if(!state.measuring&&!wasMoved){const target=document.elementFromPoint(e.clientX,e.clientY)?.closest('.mark');if(target)select(Number(target.dataset.id),false)}});
map.addEventListener('pointercancel',e=>{pointers.delete(e.pointerId);last=null;map.classList.remove('dragging')});
map.addEventListener('wheel',e=>{e.preventDefault();zoom(Math.exp(-Math.max(-120,Math.min(120,e.deltaY))*.003),...local(e))},{passive:false});map.addEventListener('dblclick',e=>{if(!state.measuring&&!e.target.closest('.mark'))zoom(1.8,...local(e))});
map.addEventListener('keydown',e=>{if(e.key==='+'||e.key==='='){e.preventDefault();zoom(1.4)}else if(e.key==='-'){e.preventDefault();zoom(1/1.4)}else if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();state.cx+=({'ArrowLeft':-80,'ArrowRight':80}[e.key]||0)/state.k;state.cy+=({'ArrowUp':80,'ArrowDown':-80}[e.key]||0)/state.k;state.view='';render()}});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(state.measuring)toggleMeasure(false);else closeDetail()}});
// Deep link from the photo gallery: /?place=12 or /?place=U3 opens the place card.
function deepLink(){const p=new URLSearchParams(location.search).get('place');if(p)select(/^\d+$/.test(p)?Number(p):p,true)}
new ResizeObserver(entries=>{const r=entries[0].contentRect;state.w=r.width;state.h=r.height;if(!state.ready){state.ready=true;fit('city');deepLink()}else render()}).observe(q('.stage'));
list();
// Exposed read-only diagnostics make the offline artifact easy to validate.
window.DerryAtlas={get revision(){return PAYLOAD.revision},get siteCount(){return D.sites.length},get unlocatedCount(){return D.unplaced.length},get view(){return {...state,active:[...state.active]}},select,fit,format};

})().catch(error=>{const el=document.querySelector('#toast');el.hidden=false;el.textContent=error.message+' Please reload the page.';console.error(error);});

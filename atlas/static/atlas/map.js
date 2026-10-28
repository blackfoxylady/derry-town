(async function startAtlas(){

'use strict';
// URLs come from the template (window.ATLAS_URLS); the fallback keeps the offline artifact working.
const URLS=window.ATLAS_URLS||{mapData:'/api/v1/map/',photoData:'/api/v1/photos/',gallery:'/photos/',photo:'/photos/0/',place:'/places/x/'};
const photoUrl=id=>URLS.photo.replace('/0/','/'+id+'/');
// The slug mirrors Django's slugify for these ASCII names; a stale slug 301-redirects anyway.
const slugify=s=>String(s).toLowerCase().replace(/['’]/g,'').replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'');
const placeUrl=s=>{const n=s.slug||slugify(s.name);return URLS.place.replace('/x/','/'+String(s.id).toLowerCase()+(n?'-'+n:'')+'/')};
// i18n: the jsi18n catalog defines gettext/ngettext; the offline artifact falls back to English.
const _=typeof gettext==='function'?gettext:s=>s;
const n_=typeof ngettext==='function'?ngettext:(s,p,n)=>n===1?s:p;
const p_=typeof pgettext==='function'?pgettext:(c,s)=>s;
const LANG=document.documentElement.lang||'en';
// The directory is fully expanded in server HTML. On phones only, progressively
// collapse it to native accordions while leaving every link in the document.
const directoryMedia=matchMedia('(max-width:780px)');
function syncDirectory(){const groups=[...document.querySelectorAll('.place-group')];if(!groups.length)return;
 const target=location.hash&&document.getElementById(location.hash.slice(1));
 groups.forEach((group,index)=>{group.open=!directoryMedia.matches||group===target||(!target&&index===0)})}
syncDirectory();directoryMedia.addEventListener('change',syncDirectory);
addEventListener('hashchange',()=>{const target=document.getElementById(location.hash.slice(1));if(target?.classList.contains('place-group'))target.open=true});
const [response,photoResponse]=await Promise.all([fetch(URLS.mapData+'?lang='+LANG,{cache:'no-cache'}),fetch(URLS.photoData+'?lang='+LANG,{cache:'no-cache'})]);
if(!response.ok)throw new Error(_('Map data unavailable')+' ('+response.status+').');
const PAYLOAD=await response.json();
// Photos are a separate data contour; the map still works if they fail to load.
const PHOTOS=photoResponse.ok?(await photoResponse.json()).features:{};
const D=PAYLOAD.data,NS='http://www.w3.org/2000/svg',q=s=>document.querySelector(s),esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const world=q('#world'),map=q('#map'),markers=q('#markers'),labels=q('#landLabels'),photoLayer=q('#photoLayer');
const state={cx:0,cy:0,k:.1,w:1000,h:700,selected:null,view:'city',active:new Set(Object.keys(PAYLOAD.colors)),search:'',names:true,relief:true,buildings:true,photos:true,measuring:false,measure:[]};
// The photo layer steps with zoom: below PHOTO_MIN_K it folds into sepia dots on the markers, up to
// POLAROID_FULL_K it shows marker-sized medallions (hover pops the polaroid), and close in —
// where few places share the screen — full polaroids.
const PHOTO_MIN_K=.055,POLAROID_FULL_K=.3;
// The zoom cap: 20 m ≈ 45 px. The minimum fits the whole sheet on a 390 px phone.
const MIN_K=.012,MAX_K=2.2;
// Litho world data (post extension) and hill spot heights, built once in scene().
let LITHO_D=null,LITHO_PEAKS=null;
const all=[...D.sites,...D.unplaced.map(s=>({...s,kind:'Unlocated',confidence:'U',short:s.name}))];
function el(tag,attrs={},parent=null){const n=document.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs))if(v!==null&&v!==undefined)n.setAttribute(k,v);if(parent)parent.appendChild(n);return n}
function scene(){
 // Survey sheet (litho.js): margin under everything, the land clipped to the frame,
 // layers in fixed slots, the frame on top. Colours come from map.css.
 const L=window.DerryLitho,defs=el('defs',{},map);
 map.classList.add('dm');L.makePatterns(defs);L.paper(world);
 const slots=L.makeSlots(L.clip(world,defs)),D=L.prep(L.adapt(PAYLOAD));LITHO_D=D;LITHO_PEAKS=L.peaks(D);
 // The Layers toggles target these classes: 'relief' and 'buildings'.
 slots.relief.classList.add('relief');slots.builtup.classList.add('buildings');slots.buildings.classList.add('buildings');
 L.drawAreas(slots.areas,D);L.drawValley(slots.valley,D);L.drawForest(slots.forest,D);L.drawRelief(slots.relief,D);L.drawVeg(slots.veg,D);
 L.drawBuiltUp(slots.builtup,D);L.drawSymbols(slots.symbols,D);L.drawWater(slots.water,D);L.drawBuildings(slots.buildings,D);
 L.drawRoads(slots.roads,D);L.drawCovered(slots.covered,D);L.drawBridges(slots.bridges,D);L.drawRail(slots.rail,D);L.drawMisc(slots.misc,D);L.drawDots(slots.dots,D);L.grid(slots.grid);
 L.frame(world);
}
function screen(x,y){return [(x-state.cx)*state.k+state.w/2,(state.cy-y)*state.k+state.h/2]}
function geo(x,y){return [state.cx+(x-state.w/2)/state.k,state.cy-(y-state.h/2)/state.k]}
function fit(id){const v=PAYLOAD.views.find(v=>v.id===id);state.view=id;const [a,b,c,d]=v.bounds;state.cx=(a+c)/2;state.cy=(b+d)/2;state.k=Math.min((state.w-60)/(c-a),(state.h-100)/(d-b));render();}
function catOk(s){return s.kind==='Unlocated'||state.active.has(s.kind)}
function searchOk(s){return !state.search||[s.id,s.name,s.short,s.note,s.period,...(s.search_aliases||[])].join(' ').toLowerCase().replace(/–/g,'-').includes(state.search.replace(/–/g,'-'))}
function hits(s){return catOk(s)&&searchOk(s)}
function format(m){return m>=1000?(m/1000).toLocaleString(LANG,{maximumFractionDigits:2})+' '+_('km'):Math.round(m).toLocaleString(LANG)+' '+_('m')}
function intersects(a,b,pad=2){return !(a[2]+pad<b[0]||a[0]-pad>b[2]||a[3]+pad<b[1]||a[1]-pad>b[3])}
// Letter-spaced source labels ("T H E  B A R R E N S") → plain words; the spacing comes from CSS.
const spaced=t=>/^\S( {1,2}\S)+$/.test(t)&&t.split(/ {2,}/).every(w=>w.split(' ').every(c=>c.length===1))?t.split(/ {2,}/).map(w=>w.replace(/ /g,'')).join(' '):t;
function render(){
 const {w,h,k,cx,cy}=state,L=window.DerryLitho;map.setAttribute('viewBox',`0 0 ${w} ${h}`);world.setAttribute('transform',`translate(${w/2-cx*k},${h/2+cy*k}) scale(${k})`);
 // --u is one screen pixel in world units, so styles pin stroke widths to the screen
 // via calc(var(--u)*N); data-z and data-bld drive the LOD classes.
 const z=k<L.LOD.far?'far':k<L.LOD.mid?'mid':'near';map.style.setProperty('--u',(1/k)+'px');map.dataset.z=z;
 map.dataset.bld=k<L.LOD.plan?'tint':'plan';L.updatePatterns(k);
 q('#zoomIn').disabled=k>=MAX_K-1e-9;
 markers.replaceChildren();labels.replaceChildren();const occupied=[];
 const inView=(x,y,m)=>x>-m&&y>-m&&x<w+m&&y<h+m;
 // Area, water and land labels first: region and water names block place labels.
 for(const l of PAYLOAD.labels){
  if(l.kind==='road'&&z==='far')continue;if(l.kind==='land'&&z!=='near')continue;
  if(l.kind==='water'&&(l.size<=10?z!=='near':l.size===11&&z==='far'))continue;   // brooks and arms near, canal names from mid
  const wx=l.x+(l.web_offset?.[0]||0),wy=l.y+(l.web_offset?.[1]||0),[x,y]=screen(wx,wy);if(!inView(x,y,80))continue;
  // Streets run along the road line; sharp bends fall back to a straight label.
  if(l.kind==='road'&&L.roadLabel(labels,{x:wx,y:-wy,angle:l.angle,text:l.text},{cx,cy:-cy,k,w,h},LITHO_D.roads))continue;
  const t=el('text',{x:0,y:0,transform:`translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${-l.angle})`,'text-anchor':'middle',class:'lbl lbl--'+l.kind},labels);
  t.textContent=l.kind==='region'?spaced(l.text):l.kind==='road'?l.text.toUpperCase():l.text;
  const half=t.textContent.length*(l.kind==='region'?11:6)/2;
  if(l.kind==='region'||l.kind==='water')occupied.push([x-half,y-10,x+half,y+6]);
 }
 // Markers at their true position, all the same size: far zoom draws dots (the selected
 // place and search matches stay full markers); a search dims the places it misses.
 const match=state.search?new Set(D.sites.filter(searchOk).map(s=>s.id)):null;
 const isMatch=s=>match&&match.has(s.id),rank=s=>s.id===state.selected?3:isMatch(s)?2:match?0:1;
 const shown=D.sites.filter(catOk).sort((a,b)=>rank(a)-rank(b)||a.id-b.id),placed=[];
 const hitLayer=el('g',{class:'mk-hits'},markers);
 for(const s of shown){const [x,y]=screen(s.x,s.y);if(!inView(x,y,30))continue;
  const sel=s.id===state.selected,dim=match&&!match.has(s.id)&&!sel,full=z!=='far'||sel||isMatch(s);
  const c=s.confidence.toLowerCase(),t=`translate(${x.toFixed(1)} ${y.toFixed(1)})`;
  // An invisible 44 px tap target under every marker (dots and discs are smaller).
  el('circle',{class:'mk-hit',r:22,transform:t,'data-id':s.id},hitLayer);
  const g=el('g',{class:`mk mk--${s.kind.toLowerCase()} mk--${c}${sel?' is-selected':''}${dim?' is-dim':''}${isMatch(s)?' is-match':''}`,transform:t,
   tabindex:dim?'-1':'0',role:'button','data-id':s.id,'aria-label':`${s.id} ${s.name}, ${KIND_SHORT[s.kind]||s.kind}, ${CONF_META[s.confidence]}`},markers);
  if(!full){el('circle',{class:'mk__dot',r:5},g);occupied.push([x-6,y-6,x+6,y+6])}
  else{el('circle',{class:'mk__focus',r:19},g);el('circle',{class:'mk__ring',r:18},g);
   if(c!=='a')el('circle',{class:'mk__halo',r:15},g);
   el('circle',{class:'mk__disc',r:sel?13:12},g);
   el('text',{class:'mk__num',y:.5},g).textContent=String(s.id).padStart(2,'0');
   occupied.push([x-16,y-16,x+16,y+16]);if(!dim)placed.push(s)}
  el('title',{},g).textContent=s.name;
  // Sepia dot: photographs exist here, but the view is too far out for polaroids.
  if(state.photos&&!dim&&PHOTOS[String(s.id)]&&k<=PHOTO_MIN_K)el('circle',{class:'ph-dot',cx:full?9:6,cy:full?-9:-6,r:2.6},g);
  g.addEventListener('click',e=>{e.stopPropagation();if(!state.measuring)select(s.id,false)});g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(s.id,false);markers.querySelector(`.mk[data-id="${s.id}"]`)?.focus()}});
 }
 // Conceptual spot heights (▲≈NN) from mid zoom; part of the relief layer.
 if(state.relief&&z!=='far')for(const[px,py,hh]of LITHO_PEAKS){const[sx,sy]=screen(px,-py);
  if(!inView(sx,sy,20))continue;
  const bb=[sx-5,sy-7,sx+34,sy+6];if(occupied.some(b=>intersects(bb,b)))continue;occupied.push(bb);
  el('path',{d:`M${sx} ${sy-4.2}L${sx+3.8} ${sy+2.4}H${sx-3.8}Z`,class:'peak-mark'},labels);
  const pt=el('text',{x:sx+6,y:sy+3.5,class:'peak'},labels);pt.textContent='≈'+hh;}
 // Photos of places hidden by a category filter or missed by a search are left out.
 const off=new Set(D.sites.filter(s=>!catOk(s)||(match&&!match.has(s.id))).map(s=>String(s.id)));
 photoLayer.replaceChildren();if(state.photos&&k>PHOTO_MIN_K)drawPhotos(occupied,off);
 // Place labels, greedy: selected first, then A → B → C, by number; right of the marker,
 // else left; a label that fits neither is skipped (the selected one never is).
 if(state.names&&(z!=='far'||state.selected!=null||match)){const R={A:0,B:1,C:2};
  for(const s of placed.sort((a,b)=>(b.id===state.selected)-(a.id===state.selected)||R[a.confidence]-R[b.confidence]||a.id-b.id)){
   if(z==='mid'&&s.confidence==='C'&&s.id!==state.selected&&!match)continue;
   const[x,y]=screen(s.x,s.y),tw=s.short.length*6.6+4,right=[x+18,y-9,x+18+tw,y+7],left=[x-18-tw,y-9,x-18,y+7];
   const box=!occupied.some(b=>intersects(right,b,0))?right:!occupied.some(b=>intersects(left,b,0))?left:null;
   if(!box&&s.id!==state.selected)continue;const b=box||right;occupied.push(b);
   const t=el('text',{x:(b===left?b[2]:b[0]).toFixed(1),y:(y+4.5).toFixed(1),'text-anchor':b===left?'end':'start',class:'lbl lbl--place'+(s.id===state.selected?' is-selected':'')},labels);t.textContent=s.short}}
 L.gridRefs(labels,{cx,cy:-cy,k,w,h});
 const target=130/k,base=10**Math.floor(Math.log10(target)),n=[1,2,5,10].filter(x=>x*base<=target).pop()||1,val=n*base;q('#scaleLine').style.width=(val*k)+'px';q('#scaleText').textContent=format(val);
 document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===state.view));
 drawMeasure();
}
// The photo layer: polaroids pinned to the map, tilt fixed per place so nothing jitters.
// Mid zoom draws marker-sized medallions instead and keeps the polaroid as a hover pop-up.
function drawPhotos(occupied,off){
 if(!q('#photoClip')){const defs=el('defs',{},map);const cp=el('clipPath',{id:'photoClip'},defs);el('circle',{r:11},cp)}
 const full=state.k>=POLAROID_FULL_K,FR=46,FH=57,IMG=40,R=12;
 // Medallions search rings of positions (top first); a ring of 32 clears the place's own
 // marker, whose occupied box reaches 16 px from the anchor.
 const offs=full?[[0,-50],[42,-42],[-42,-42],[50,0],[-50,0],[0,52],[42,44],[-42,44]]:[];
 if(!full)for(const r of [32,44,56])for(let i=0;i<12;i++){const a=-Math.PI/2+i*Math.PI/6;offs.push([Math.cos(a)*r,Math.sin(a)*r])}
 const bw=full?FR/2+2:R+2,bh=full?FH/2+2:R+2;
 for(const [key,f] of Object.entries(PHOTOS)){
  if(!f.anchor||off.has(key))continue;const [ax,ay]=screen(f.anchor[0],f.anchor[1]);
  if(ax<-60||ay<-60||ax>state.w+60||ay>state.h+60)continue;
  let px=null,py=null;
  for(const [dx,dy] of offs){const nx=ax+dx,ny=ay+dy,bb=[nx-bw,ny-bh,nx+bw,ny+bh];
   if(!occupied.some(b=>intersects(bb,b,1))){px=nx;py=ny;occupied.push(bb);break}}
  if(px===null)continue;
  const p0=f.photos[0];let hsh=0;for(const c of key)hsh=(hsh*31+c.charCodeAt(0))%997;const tilt=hsh%7-3;
  el('path',{d:`M${ax},${ay}L${px},${py}`,stroke:'#8a7a5c','stroke-width':.8,fill:'none'},photoLayer);
  el('circle',{cx:ax,cy:ay,r:1.8,fill:'#8a7a5c'},photoLayer);
  const g=el('g',{class:'polaroid',transform:`translate(${px},${py})`,tabindex:'0',role:'button','data-key':key,'aria-label':_('Photographs')+' · '+f.name},photoLayer);
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
function openPhotoFeature(key){const f=PHOTOS[key];if(!f)return;if(f.object_type==='site')select(Number(key),false);else if(f.object_type==='unplaced')select(key,false);else location.href=f.gallery||URLS.gallery+'?place='+key}
// Confidence terms (shared with the place pages): full label with the letter, lowercase for meta lines.
const CONF={A:'A · '+_('Named in the novel'),B:'B · '+_('Inferred'),C:'C · '+_('Proposed'),U:'U · '+_('No location')};
const CONF_META={A:_('named in the novel'),B:_('inferred'),C:_('proposed'),U:_('no location')};
// Short category names, as in meta lines ("Civic" / "Город"): marker labels for screen readers.
const KIND_SHORT={Homes:p_('kind short','Homes'),Civic:p_('kind short','Civic'),Encounters:p_('kind short','Encounters'),Historical:p_('kind short','Historical'),Barrens:p_('kind short','Barrens'),Outlying:p_('kind short','Outlying')};
function list(){const result=all.filter(hits),mapped=D.sites.filter(hits).length;q('#count').textContent=result.length+' '+n_('place','places',result.length)+' · '+mapped+' '+_('mapped');q('#list').innerHTML=result.length?result.map(s=>`<li><button data-place="${s.id}" class="${state.selected===s.id?'selected':''}"><span class="num" style="color:${PAYLOAD.colors[s.kind]||'#697166'}">${String(s.id).padStart(2,'0')}</span><span><span class="item-title">${esc(s.name)}</span><span class="item-sub">${esc(s.period)} · ${esc(CONF_META[s.confidence]||'')}</span></span></button></li>`).join(''):'<li class="empty">'+esc(_('No matching places. Try a shorter name or enable more categories.'))+'</li>';q('#list').querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>select(/^U/.test(b.dataset.place)?b.dataset.place:Number(b.dataset.place),true)));}
function select(id,focus){const s=all.find(s=>s.id===id);if(!s)return;state.selected=id;q('#intro').hidden=true;const panel=q('#detail');panel.hidden=false;const conf=CONF;
 const refs=s.refs||[];
 const fp=PHOTOS[String(s.id)];
 const photoRow=fp?`<div class="card-photos">${fp.photos.map(p=>`<a class="card-photo" href="${photoUrl(p.id)}" title="${esc(p.caption)}"><img src="${esc(p.thumb)}" alt="${esc(p.caption||s.name)}" loading="lazy"></a>`).join('')}</div><p class="card-photos-more"><a href="${esc(fp.gallery||URLS.gallery+'?place='+String(s.id))}">${esc(_('All photographs of this place'))} →</a></p>`:'';
 panel.innerHTML=`<div class="detail-top"><div><div class="eyebrow">${esc(_('Place %s').replace('%s',String(s.id).padStart(2,'0')))}</div><h2>${esc(s.name)}</h2></div><button class="close" id="closeDetail" aria-label="${esc(_('Close place'))}">×</button></div><div class="meta">${esc(s.period)}</div><p><span class="badge">${conf[s.confidence]}</span></p><p>${esc(s.note)}</p>${photoRow}${refs.length?`<details open><summary>${esc(_('Sources & evidence'))}</summary><ul class="refs">${refs.map(r=>`<li>${esc(r)}</li>`).join('')}</ul></details>`:''}<p class="card-page"><a href="${placeUrl(s)}" target="_blank" rel="noopener">${esc(_('Place page'))} →</a></p>`;
 q('#closeDetail').onclick=closeDetail;q('#scroll').scrollTop=0;
 if(typeof id==='number'&&focus){state.cx=s.x;state.cy=s.y;state.k=Math.max(state.k,.48);state.view='';}
 list();render();if(matchMedia('(max-width:780px)').matches&&!q('#workspace').classList.contains('open')){q('#workspace').classList.add('open');q('#placesToggle').setAttribute('aria-expanded','true');state.panelAutoOpened=true;}
}
function closeDetail(){state.selected=null;q('#detail').hidden=true;q('#intro').hidden=false;if(state.panelAutoOpened){state.panelAutoOpened=false;q('#workspace').classList.remove('open');q('#placesToggle').setAttribute('aria-expanded','false');}list();render()}
function zoom(f,x=state.w/2,y=state.h/2){const [gx,gy]=geo(x,y);state.k=Math.min(MAX_K,Math.max(MIN_K,state.k*f));state.cx=gx-(x-state.w/2)/state.k;state.cy=gy+(y-state.h/2)/state.k;state.view='';render()}
function showToast(msg){q('#toast').textContent=msg;q('#toast').hidden=!msg}
function drawMeasure(){const layer=q('#measureLayer');layer.replaceChildren();if(!state.measure.length)return;state.measure.forEach(p=>{const[x,y]=screen(...p);el('circle',{cx:x,cy:y,r:4,fill:'#a34b35',stroke:'#fff','stroke-width':1.3},layer)});if(state.measure.length===2){const a=screen(...state.measure[0]),b=screen(...state.measure[1]);el('path',{d:`M${a}L${b}`,fill:'none',stroke:'#a34b35','stroke-width':2,'stroke-dasharray':'5 3'},layer);showToast(format(Math.hypot(state.measure[0][0]-state.measure[1][0],state.measure[0][1]-state.measure[1][1]))+' · '+_('straight line in this reconstruction'));}}
function toggleMeasure(force){state.measuring=force===undefined?!state.measuring:force;state.measure=[];q('#measure').classList.toggle('on',state.measuring);q('#measure').setAttribute('aria-pressed',state.measuring);map.classList.toggle('measuring',state.measuring);showToast(state.measuring?_('Select two points to measure. Drag to pan. Escape clears.'):'');render()}
scene();
// Category keys are canonical data; only the visible labels translate.
const KIND_LABELS={Homes:_('Homes'),Civic:_('Civic'),Encounters:_('Encounters'),Historical:_('Historical'),Barrens:_('Barrens'),Outlying:_('Outlying')};
q('#filters').innerHTML=Object.keys(PAYLOAD.colors).map(c=>`<label><input type="checkbox" checked data-kind="${c}">${esc(KIND_LABELS[c]||c)}</label>`).join('');
q('#filters').querySelectorAll('input').forEach(x=>x.onchange=()=>{x.checked?state.active.add(x.dataset.kind):state.active.delete(x.dataset.kind);list();render()});
q('#search').oninput=e=>{state.search=e.target.value.trim().toLowerCase();q('#clearSearch').hidden=!e.target.value;list();render()};q('#clearSearch').onclick=()=>{q('#search').value='';state.search='';q('#clearSearch').hidden=true;list();render();q('#search').focus()};
q('#showPhotos').onchange=e=>{state.photos=e.target.checked;render()};q('#showNames').onchange=e=>{state.names=e.target.checked;render()};q('#showRelief').onchange=e=>{state.relief=e.target.checked;world.querySelectorAll('.relief').forEach(n=>n.style.display=state.relief?'':'none');render()};q('#showBuildings').onchange=e=>{world.querySelectorAll('.buildings').forEach(n=>n.style.display=e.target.checked?'':'none')};
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>fit(b.dataset.view));q('#zoomIn').onclick=()=>zoom(1.4);q('#zoomOut').onclick=()=>zoom(1/1.4);q('#reset').onclick=()=>fit('city');q('#measure').onclick=()=>toggleMeasure();
q('#placesToggle').onclick=()=>{const open=q('#workspace').classList.toggle('open');q('#placesToggle').setAttribute('aria-expanded',open);state.panelAutoOpened=false};
q('#panelClose').onclick=()=>{state.panelAutoOpened=false;q('#workspace').classList.remove('open');q('#placesToggle').setAttribute('aria-expanded','false')};
const pointers=new Map();let last=null,start=null,moved=false,lastPinch=0,hadPinch=false;
function local(e){const r=map.getBoundingClientRect();return [e.clientX-r.left,e.clientY-r.top]}
map.addEventListener('pointerdown',e=>{if(e.button!==0)return;const p=local(e);pointers.set(e.pointerId,p);map.setPointerCapture(e.pointerId);start=p;last=p;moved=false;if(pointers.size>1){hadPinch=true;const v=[...pointers.values()];lastPinch=Math.hypot(v[0][0]-v[1][0],v[0][1]-v[1][1])}map.classList.add('dragging')});
map.addEventListener('pointermove',e=>{if(!pointers.has(e.pointerId))return;const p=local(e);pointers.set(e.pointerId,p);if(pointers.size===2){const v=[...pointers.values()],d=Math.hypot(v[0][0]-v[1][0],v[0][1]-v[1][1]);if(lastPinch>0&&d>0)zoom(d/lastPinch,(v[0][0]+v[1][0])/2,(v[0][1]+v[1][1])/2);lastPinch=d;moved=true;return}if(last){const dx=p[0]-last[0],dy=p[1]-last[1];if(start&&Math.hypot(p[0]-start[0],p[1]-start[1])>4)moved=true;if(moved){state.cx-=dx/state.k;state.cy+=dy/state.k;state.view='';render()}}last=p});
map.addEventListener('pointerup',e=>{const p=local(e),wasMoved=moved||hadPinch;pointers.delete(e.pointerId);if(!pointers.size){map.classList.remove('dragging');last=null;lastPinch=0;hadPinch=false}else last=[...pointers.values()][0];if(state.measuring&&!wasMoved){if(state.measure.length===2)state.measure=[];state.measure.push(geo(...p));drawMeasure()}if(!state.measuring&&!wasMoved){const hit=document.elementFromPoint(e.clientX,e.clientY);const pol=hit?.closest('.polaroid');if(pol)openPhotoFeature(pol.dataset.key);else{const target=hit?.closest('.mk,.mk-hit');if(target)select(Number(target.dataset.id),false)}}});
map.addEventListener('pointercancel',e=>{pointers.delete(e.pointerId);last=null;map.classList.remove('dragging')});
map.addEventListener('wheel',e=>{e.preventDefault();zoom(Math.exp(-Math.max(-120,Math.min(120,e.deltaY))*.003),...local(e))},{passive:false});map.addEventListener('dblclick',e=>{if(!state.measuring&&!e.target.closest('.mk,.mk-hit,.polaroid'))zoom(1.8,...local(e))});
map.addEventListener('keydown',e=>{if(e.key==='+'||e.key==='='){e.preventDefault();zoom(1.4)}else if(e.key==='-'){e.preventDefault();zoom(1/1.4)}else if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();state.cx+=({'ArrowLeft':-80,'ArrowRight':80}[e.key]||0)/state.k;state.cy+=({'ArrowUp':80,'ArrowDown':-80}[e.key]||0)/state.k;state.view='';render()}});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(state.measuring)toggleMeasure(false);else closeDetail()}});
// Deep link from the photo gallery: /?place=12 or /?place=U3 opens the place card.
function deepLink(){const p=new URLSearchParams(location.search).get('place');if(p)select(/^\d+$/.test(p)?Number(p):p,true)}
new ResizeObserver(entries=>{const r=entries[0].contentRect;state.w=r.width;state.h=r.height;if(!state.ready){state.ready=true;fit('city');deepLink()}else render()}).observe(q('.stage'));
list();
// Exposed read-only diagnostics make the offline artifact easy to validate.
window.DerryAtlas={get revision(){return PAYLOAD.revision},get siteCount(){return D.sites.length},get unlocatedCount(){return D.unplaced.length},get photoFeatureCount(){return Object.keys(PHOTOS).length},get view(){return {...state,active:[...state.active]}},select,fit,format,
 // Exact view (payload metres, y up), for side-by-side checks against the reference renderer.
 setView(cx,cy,k){state.cx=cx;state.cy=cy;state.k=k;state.view='';render()}};

})().catch(error=>{const el=document.querySelector('#toast');el.hidden=false;el.textContent=error.message+' '+(typeof gettext==='function'?gettext('Please reload the page.'):'Please reload the page.');console.error(error);});

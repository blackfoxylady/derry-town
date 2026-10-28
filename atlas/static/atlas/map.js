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
const state={cx:0,cy:0,k:.1,w:1000,h:700,selected:null,view:'city',active:new Set(Object.keys(PAYLOAD.colors)),search:'',sort:'number',withPhotos:false,hide:new Set(),list:'all',names:true,relief:true,buildings:true,photos:true,measuring:false,measure:[]};
// The photo layer follows the map LOD (block 13): far — sepia dots by the markers, mid —
// medallions at the marker's shoulder (hover or keyboard focus pops the polaroid out), near —
// polaroids on a leader. Card 50 × 62 with a 42 px photo.
const PW=50,PH=62,PI=42;
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
// Views fit with a 24 px margin (D40), above the phone sheet when there is one.
function fit(id){const v=PAYLOAD.views.find(v=>v.id===id),pad=ui.sheetCover();state.view=id;const [a,b,c,d]=v.bounds;state.k=Math.min((state.w-48)/(c-a),(state.h-48-pad)/(d-b));state.cx=(a+c)/2;state.cy=(b+d)/2-pad/2/state.k;render();}
// Filters (block 10): Category, With photos and the A/B/C key remove places from the map and the
// list; skip leaves one of them out, for the counts next to that control.
function filterOk(s,skip){return (skip==='kind'||s.kind==='Unlocated'||state.active.has(s.kind))&&(skip==='photos'||!state.withPhotos||!!PHOTOS[String(s.id)])&&(skip==='hide'||!state.hide.has(s.confidence))}
// Search (block 10): number, EN and RU names, aliases, note and period; state.search is the
// normalised query once it is long enough (map-ui.js), '' otherwise.
const norm=t=>String(t).toLowerCase().replace(/[–—]/g,'-').replace(/ё/g,'е');
// One or two digits look up a map number ("5" is place 5, not every year with a 5 in it).
function searchOk(s){return !state.search||(/^\d{1,2}$/.test(state.search)?String(s.id)===state.search:norm([s.id,s.name,s.short,s.note,s.period,...(s.search_aliases||[])].join(' ')).includes(state.search))}
// The list: filters and search, and only the unlocated places after "No location →" (the map keeps them all).
function hits(s){return filterOk(s)&&searchOk(s)&&(state.list!=='unlocated'||s.confidence==='U')}
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
 let match=state.search?new Set(D.sites.filter(searchOk).map(s=>s.id)):null;if(match&&!match.size)match=null;
 const isMatch=s=>match&&match.has(s.id),rank=s=>s.id===state.selected?3:isMatch(s)?2:match?0:1;
 const shown=D.sites.filter(s=>filterOk(s)||s.id===state.selected).sort((a,b)=>rank(a)-rank(b)||a.id-b.id),placed=[];
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
  if(state.photos&&!dim&&PHOTOS[String(s.id)]&&z==='far')el('circle',{class:'ph-dot',cx:full?9:6,cy:full?-9:-6,r:2.6},g);
  g.addEventListener('click',e=>{e.stopPropagation();if(!state.measuring)select(s.id,{opener:{mk:s.id}})});g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(s.id,{opener:{mk:s.id}})}});
  g.addEventListener('pointerenter',()=>ui.hot(s.id));g.addEventListener('pointerleave',()=>ui.hot(null));
 }
 // Conceptual spot heights (▲≈NN) from mid zoom; part of the relief layer.
 if(state.relief&&z!=='far')for(const[px,py,hh]of LITHO_PEAKS){const[sx,sy]=screen(px,-py);
  if(!inView(sx,sy,20))continue;
  const bb=[sx-5,sy-7,sx+34,sy+6];if(occupied.some(b=>intersects(bb,b)))continue;occupied.push(bb);
  el('path',{d:`M${sx} ${sy-4.2}L${sx+3.8} ${sy+2.4}H${sx-3.8}Z`,class:'peak-mark'},labels);
  const pt=el('text',{x:sx+6,y:sy+3.5,class:'peak'},labels);pt.textContent='≈'+hh;}
 // Photos of places hidden by a category filter or missed by a search are left out.
 const off=new Set(D.sites.filter(s=>!filterOk(s)||(match&&!match.has(s.id))).map(s=>String(s.id)));
 photoLayer.replaceChildren();if(state.photos)drawPhotos(occupied,off,z);
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
 document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===state.view)));
 drawMeasure();
}
// Prints search a ring round the marker (top first) after every marker is placed, so they
// never cover one; the selected place keeps its print even when no spot is free.
const PRINT_OFFS=[[0,-60],[44,-44],[-44,-44],[54,0],[-54,0],[0,60],[44,46],[-44,46]];
function drawPhotos(occupied,off,z){
 if(!q('#photoClip')){const defs=el('defs',{},map);const cp=el('clipPath',{id:'photoClip'},defs);el('circle',{r:9},cp)}
 const leaders=el('g',{class:'ph-leaders'},photoLayer),near=[];
 for(const [key,f] of Object.entries(PHOTOS)){
  // Places hidden by a category filter or missed by a search lose their photos; so do streets
  // and other outlines while a search is on (they never match one).
  if(!f.anchor||off.has(key))continue;const site=f.object_type==='site';if(!site&&state.search)continue;
  const [ax,ay]=screen(f.anchor[0],f.anchor[1]);if(ax<-60||ay<-60||ax>state.w+60||ay>state.h+60)continue;
  // Far: places carry their dot on the marker; a street's photo sits as a dot on its anchor.
  if(z==='far'){if(!site)el('circle',{class:'ph-dot',cx:ax,cy:ay,r:2.6},photoLayer);continue}
  if(z==='mid'){const g=photoButton(key,f,site?ax+17:ax,site?ay-17:ay,'ph-medal');
   el('circle',{class:'ph-focus',r:14},g);el('circle',{class:'ph-medal__ring',r:11},g);
   el('image',{href:f.photos[0].thumb,x:-9,y:-9,width:18,height:18,preserveAspectRatio:'xMidYMid slice','clip-path':'url(#photoClip)'},g);
   if(f.photos.length>1)el('text',{class:'ph-count',x:9,y:-7},g).textContent='×'+f.photos.length;
   photoPrint(g,f,'translate(0 -58) scale(1.9)','ph-pop');continue}
  near.push([key,f,ax,ay,site]);
 }
 for(const [key,f,ax,ay,site] of near){
  const box=([dx,dy])=>[ax+dx-PW/2-2,ay+dy-PH/2-2,ax+dx+PW/2+2,ay+dy+PH/2+2];
  let o=PRINT_OFFS.find(o=>!occupied.some(b=>intersects(box(o),b,0)));
  if(!o&&site&&Number(key)===state.selected)o=PRINT_OFFS[0];if(!o)continue;occupied.push(box(o));
  // The leader starts at the marker edge; a street's at its anchor point.
  const d=Math.hypot(...o),r=site?14:0,px=ax+o[0],py=ay+o[1];
  el('path',{class:'ph-leader',d:`M${(ax+o[0]/d*r).toFixed(1)} ${(ay+o[1]/d*r).toFixed(1)}L${px.toFixed(1)} ${py.toFixed(1)}`},leaders);
  if(!site)el('circle',{class:'ph-anchor',cx:ax,cy:ay,r:1.8},leaders);
  // Tilt −3…3°, fixed per place, so a print never jumps on redraw.
  let h=0;for(const c of key)h=(h*31+c.charCodeAt(0))%997;
  photoPrint(photoButton(key,f,px,py,'ph-near'),f,'',null,h%7-3);
 }
}
// The caption a real polaroid would carry: the first photo's year and the count.
function photoCaption(f){return [f.photos[0].year,f.photos.length>1?'×'+f.photos.length:''].filter(Boolean).join(' · ')}
// A medallion or a print: one focusable button per place. Mouse hover and keyboard focus
// raise it ('is-up': mid pops the polaroid, near straightens and grows); touch just opens.
function photoButton(key,f,x,y,cls){const cap=photoCaption(f);
 const g=el('g',{class:'ph '+cls,transform:`translate(${x.toFixed(1)} ${y.toFixed(1)})`,tabindex:'0',role:'button','data-key':key,'aria-label':_('Photographs')+' · '+f.name+(cap?' · '+cap:'')},photoLayer);
 g.addEventListener('pointerenter',e=>{if(e.pointerType!=='mouse')return;g.classList.add('is-up');if(g!==photoLayer.lastElementChild)photoLayer.appendChild(g)});
 g.addEventListener('pointerleave',()=>g.classList.remove('is-up'));
 // Moving a focused node would drop focus and the Tab order, so focus draws a raised copy on top.
 g.addEventListener('focus',()=>{if(!g.matches(':focus-visible'))return;const c=g.cloneNode(true);
  c.classList.add('is-up','ph-copy');c.removeAttribute('tabindex');c.removeAttribute('role');c.removeAttribute('aria-label');c.setAttribute('aria-hidden','true');photoLayer.appendChild(c);g._copy=c});
 g.addEventListener('blur',()=>{g._copy?.remove();g._copy=null});
 g.addEventListener('click',e=>{e.stopPropagation();if(!state.measuring)openPhotoFeature(key)});
 g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openPhotoFeature(key)}});
 return g}
function photoPrint(parent,f,transform,cls,tilt=0){const cap=photoCaption(f);
 const p=el('g',{class:'ph-print'+(cls?' '+cls:''),transform:transform||null},parent),t=el('g',{class:'ph-print__body',style:'--tilt:'+tilt+'deg'},p);
 if(!cls)el('rect',{class:'ph-focus',x:-PW/2-3,y:-PH/2-3,width:PW+6,height:PH+6},t);
 el('rect',{class:'ph-print__shadow',x:-PW/2+1,y:-PH/2+2,width:PW,height:PH},t);
 el('rect',{class:'ph-print__card',x:-PW/2,y:-PH/2,width:PW,height:PH},t);
 el('image',{href:f.photos[0].thumb,x:-PI/2,y:-PH/2+4,width:PI,height:PI,preserveAspectRatio:'xMidYMid slice'},t);
 if(cap)el('text',{class:'ph-print__cap',x:0,y:PH/2-5,'text-anchor':'middle'},t).textContent=cap}
// A polaroid opens the place card when the place has one; roads and other outlines go to the gallery.
function openPhotoFeature(key){const f=PHOTOS[key];if(!f)return;if(f.object_type==='site')select(Number(key));else if(f.object_type==='unplaced')select(key);else location.href=f.gallery||URLS.gallery+'?place='+key}
// Confidence terms (shared with the place pages): full label with the letter, lowercase for meta lines.
const CONF_META={A:_('named in the novel'),B:_('inferred'),C:_('proposed'),U:_('no location')};
// Short category names, as in meta lines ("Civic" / "Город"): marker labels for screen readers.
const KIND_SHORT={Homes:p_('kind short','Homes'),Civic:p_('kind short','Civic'),Encounters:p_('kind short','Encounters'),Historical:p_('kind short','Historical'),Barrens:p_('kind short','Barrens'),Outlying:p_('kind short','Outlying')};
function resetFilters(){state.active=new Set(Object.keys(PAYLOAD.colors));state.withPhotos=false;state.hide=new Set()}
// Choosing a place centres it unless it already sits in the middle 60% of the visible map (on
// the phone, the part above the card sheet); from the list, the pager or a link it also zooms
// in to street level. An unlocated place leaves the map.
function select(id,opts={}){const s=all.find(s=>s.id===id);if(!s)return;if(typeof opts!=='object')opts={};
 state.selected=id;
 if(typeof id==='number'){const cover=ui.cover(),vh=state.h-cover,[x,y]=screen(s.x,s.y),inMiddle=x>state.w*.2&&x<state.w*.8&&y>vh*.2&&y<vh*.8;
  const centre=()=>{state.cx=s.x;state.cy=s.y-cover/2/state.k;state.view=''};
  if(opts.zoom&&state.k<.48){state.k=.48;centre()}else if(!inMiddle)centre()}
 render();ui.open(s,opts)}
// Closing (× or Esc) drops the ring and leaves the map where it is; focus returns to the opener.
function closeDetail(){if(state.selected==null)return;const id=state.selected;state.selected=null;render();
 const back=ui.close();(back||q(`#markers .mk[data-id="${id}"]`)||map).focus()}
// "Zoom to N places": fit the results with 48 px around them (above the phone sheet), over
// 300 ms, instantly under reduced motion. One place gets street zoom.
function zoomToPlaces(places){const pts=places.filter(s=>typeof s.id==='number');if(!pts.length)return;
 const xs=pts.map(s=>s.x),ys=pts.map(s=>s.y),pad=ui.sheetCover(),[a,b,c,d]=[Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys)];
 const k=pts.length===1?Math.max(state.k,.9):Math.min(1.2,(state.w-96)/Math.max(c-a,1),(state.h-96-pad)/Math.max(d-b,1));
 const to={k:Math.max(MIN_K,Math.min(MAX_K,k)),cx:(a+c)/2},from={k:state.k,cx:state.cx,cy:state.cy};to.cy=(b+d)/2-pad/2/to.k;state.view='';
 if(matchMedia('(prefers-reduced-motion: reduce)').matches){Object.assign(state,to);render();return}
 const t0=performance.now();(function step(t){const p=Math.min(1,(t-t0)/300),e=p<.5?2*p*p:1-(-2*p+2)**2/2;
  state.k=from.k*(to.k/from.k)**e;state.cx=from.cx+(to.cx-from.cx)*e;state.cy=from.cy+(to.cy-from.cy)*e;render();if(p<1)requestAnimationFrame(step)})(t0)}
function zoom(f,x=state.w/2,y=state.h/2){const [gx,gy]=geo(x,y);state.k=Math.min(MAX_K,Math.max(MIN_K,state.k*f));state.cx=gx-(x-state.w/2)/state.k;state.cy=gy+(y-state.h/2)/state.k;state.view='';render()}
function showToast(msg){q('#toast').textContent=msg;q('#toast').hidden=!msg}
function drawMeasure(){const layer=q('#measureLayer');layer.replaceChildren();if(!state.measure.length)return;state.measure.forEach(p=>{const[x,y]=screen(...p);el('circle',{cx:x,cy:y,r:4,fill:'#a34b35',stroke:'#fff','stroke-width':1.3},layer)});if(state.measure.length===2){const a=screen(...state.measure[0]),b=screen(...state.measure[1]);el('path',{d:`M${a}L${b}`,fill:'none',stroke:'#a34b35','stroke-width':2,'stroke-dasharray':'5 3'},layer);showToast(format(Math.hypot(state.measure[0][0]-state.measure[1][0],state.measure[0][1]-state.measure[1][1]))+' · '+_('straight line in this reconstruction'));}}
function toggleMeasure(force){state.measuring=force===undefined?!state.measuring:force;state.measure=[];q('#measure').classList.toggle('on',state.measuring);q('#measure').setAttribute('aria-pressed',state.measuring);map.classList.toggle('measuring',state.measuring);showToast(state.measuring?_('Select two points to measure. Drag to pan. Escape clears.'):'');render()}
// Category keys are canonical data; only the visible labels translate.
// Editorial order, as in the directory below the map.
const KIND_ORDER=['Homes','Civic','Barrens','Encounters','Historical','Outlying'];
const KIND_LABELS={Homes:_('Homes'),Civic:_('Civic'),Encounters:_('Encounters'),Historical:_('Historical'),Barrens:_('Barrens'),Outlying:_('Outlying')};
scene();
const ui=window.DerryMapUI({state,all,photos:PHOTOS,placeUrl,photoUrl,galleryUrl:URLS.gallery,hits,filterOk,searchOk,norm,kindShort:KIND_SHORT,kindLabels:KIND_LABELS,kinds:[...KIND_ORDER.filter(k=>k in PAYLOAD.colors),...Object.keys(PAYLOAD.colors).filter(k=>!KIND_ORDER.includes(k))],confMeta:CONF_META,_,n_,select,close:closeDetail,render,zoomToPlaces,resetFilters});
q('#showPhotos').onchange=e=>{state.photos=e.target.checked;render()};q('#showNames').onchange=e=>{state.names=e.target.checked;render()};q('#showRelief').onchange=e=>{state.relief=e.target.checked;world.querySelectorAll('.relief').forEach(n=>n.style.display=state.relief?'':'none');render()};q('#showBuildings').onchange=e=>{world.querySelectorAll('.buildings').forEach(n=>n.style.display=e.target.checked?'':'none')};
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>fit(b.dataset.view));q('#zoomIn').onclick=()=>zoom(1.4);q('#zoomOut').onclick=()=>zoom(1/1.4);q('#reset').onclick=()=>fit('city');q('#measure').onclick=()=>toggleMeasure();
const pointers=new Map();let last=null,start=null,moved=false,lastPinch=0,hadPinch=false;
function local(e){const r=map.getBoundingClientRect();return [e.clientX-r.left,e.clientY-r.top]}
map.addEventListener('pointerdown',e=>{if(e.button!==0)return;const p=local(e);pointers.set(e.pointerId,p);map.setPointerCapture(e.pointerId);start=p;last=p;moved=false;if(pointers.size>1){hadPinch=true;const v=[...pointers.values()];lastPinch=Math.hypot(v[0][0]-v[1][0],v[0][1]-v[1][1])}map.classList.add('dragging')});
map.addEventListener('pointermove',e=>{if(!pointers.has(e.pointerId))return;const p=local(e);pointers.set(e.pointerId,p);if(pointers.size===2){const v=[...pointers.values()],d=Math.hypot(v[0][0]-v[1][0],v[0][1]-v[1][1]);if(lastPinch>0&&d>0)zoom(d/lastPinch,(v[0][0]+v[1][0])/2,(v[0][1]+v[1][1])/2);lastPinch=d;moved=true;return}if(last){const dx=p[0]-last[0],dy=p[1]-last[1];if(start&&Math.hypot(p[0]-start[0],p[1]-start[1])>4)moved=true;if(moved){state.cx-=dx/state.k;state.cy+=dy/state.k;state.view='';render()}}last=p});
map.addEventListener('pointerup',e=>{const p=local(e),wasMoved=moved||hadPinch;pointers.delete(e.pointerId);if(!pointers.size){map.classList.remove('dragging');last=null;lastPinch=0;hadPinch=false}else last=[...pointers.values()][0];if(state.measuring&&!wasMoved){if(state.measure.length===2)state.measure=[];state.measure.push(geo(...p));drawMeasure()}if(!state.measuring&&!wasMoved){const hit=document.elementFromPoint(e.clientX,e.clientY);const pol=hit?.closest('.ph');if(pol)openPhotoFeature(pol.dataset.key);else{const target=hit?.closest('.mk,.mk-hit');if(target)select(Number(target.dataset.id),{opener:{mk:target.dataset.id}})}}});
map.addEventListener('pointercancel',e=>{pointers.delete(e.pointerId);last=null;map.classList.remove('dragging')});
map.addEventListener('wheel',e=>{e.preventDefault();zoom(Math.exp(-Math.max(-120,Math.min(120,e.deltaY))*.003),...local(e))},{passive:false});map.addEventListener('dblclick',e=>{if(!state.measuring&&!e.target.closest('.mk,.mk-hit,.ph'))zoom(1.8,...local(e))});
map.addEventListener('keydown',e=>{if(e.key==='+'||e.key==='='){e.preventDefault();zoom(1.4)}else if(e.key==='-'){e.preventDefault();zoom(1/1.4)}else if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();state.cx+=({'ArrowLeft':-80,'ArrowRight':80}[e.key]||0)/state.k;state.cy+=({'ArrowUp':80,'ArrowDown':-80}[e.key]||0)/state.k;state.view='';render()}});
// Only from the map page itself (panel or stage): Esc down in the directory leaves the card alone.
document.addEventListener('keydown',e=>{if(e.key!=='Escape'||e.defaultPrevented||!(e.target===document.body||e.target.closest?.('.app')))return;if(ui.closeTip())return;if(state.measuring)toggleMeasure(false);else closeDetail()});
// Deep link from the photo gallery: /?place=12 or /?place=U3 opens the place card.
// Read before the first apply() rewrites the address.
const START_PLACE=new URLSearchParams(location.search).get('place');
function deepLink(){const p=START_PLACE;if(p)select(/^\d+$/.test(p)?Number(p):p.toUpperCase(),{zoom:true,focus:false})}
new ResizeObserver(entries=>{const r=entries[0].contentRect;state.w=r.width;state.h=r.height;if(!state.ready){state.ready=true;fit('city');deepLink()}else render()}).observe(q('.stage'));
ui.apply();
// Exposed read-only diagnostics make the offline artifact easy to validate.
window.DerryAtlas={get revision(){return PAYLOAD.revision},get siteCount(){return D.sites.length},get unlocatedCount(){return D.unplaced.length},get photoFeatureCount(){return Object.keys(PHOTOS).length},get view(){return {...state,active:[...state.active]}},select,close:closeDetail,fit,format,
 // Exact view (payload metres, y up), for side-by-side checks against the reference renderer.
 setView(cx,cy,k){state.cx=cx;state.cy=cy;state.k=k;state.view='';render()}};

})().catch(error=>{const el=document.querySelector('#toast');el.hidden=false;el.textContent=error.message+' '+(typeof gettext==='function'?gettext('Please reload the page.'):'Please reload the page.');console.error(error);});

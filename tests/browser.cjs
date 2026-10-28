const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
 const out=process.env.BROWSER_OUTPUT||'docs/verification/screenshots';fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE||undefined,args:process.env.CHROMIUM_NO_SANDBOX==='1'?['--no-sandbox']:[]});
 const reports=[];
 for(const [name,size] of [['desktop',{width:1440,height:1000}],['mobile',{width:390,height:844}]]){
  const context=await browser.newContext({viewport:size,isMobile:name==='mobile',hasTouch:name==='mobile',deviceScaleFactor:1});
  const analyticsRequests=[];
  await context.route(url=>/googletagmanager\.com|mc\.yandex\.ru/.test(url.href),route=>route.abort());
  const page=await context.newPage();const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',request=>{if(/googletagmanager\.com|mc\.yandex\.ru/.test(request.url()))analyticsRequests.push(request.url())});
  page.on('response',r=>{if(r.url().startsWith(process.env.DERRY_URL||'http://127.0.0.1:8765')&&r.status()>=400)errors.push(r.status()+' '+r.url())});
  await page.goto(process.env.DERRY_URL||'http://127.0.0.1:8765',{waitUntil:'networkidle'});
  assert.equal(await page.locator('#cookieConsent').isVisible(),true);
  assert.equal(analyticsRequests.length,0);
  await page.screenshot({path:path.join(out,name+'-cookie-consent.png'),fullPage:true});
  if(name==='desktop'){
   await page.locator('[data-cookie-reject]').click();
   await page.reload({waitUntil:'networkidle'});
   assert.equal(await page.locator('#cookieConsent').isVisible(),false);
   assert.equal(analyticsRequests.length,0);
  }else{
   await page.locator('[data-cookie-accept]').click();
   await page.waitForFunction(()=>typeof window.gtag==='function'&&typeof window.ym==='function');
   assert.equal(await page.locator('#cookieConsent').isVisible(),false);
   assert(analyticsRequests.some(url=>url.includes('googletagmanager.com')));
   assert(analyticsRequests.some(url=>url.includes('mc.yandex.ru')));
  }
  await page.waitForFunction(()=>window.DerryAtlas?.siteCount===84,null,{timeout:120000});
  assert.equal(await page.evaluate(()=>DerryAtlas.unlocatedCount),8);
  // The crawlable directory is present independently of the JS-built sidebar.
  assert.equal(await page.locator('.dir-list a').count(),92);
  assert.equal(await page.locator('.dir-list a[href="/places/12-derry-public-library/"]').count(),1);
  // Below the map (block 14): the four-row confidence legend and a jump chip per group.
  assert.equal(await page.locator('.map-legend-card li').count(),4);
  assert.equal(await page.locator('.dir-nav a').count(),7);
  assert.equal(await page.locator('.directory-jump').isVisible(),true);
  assert.equal(await page.locator('.place-group[open]').count(),name==='mobile'?1:7);
  // Survey sheet: margin + land clipped into slot groups + one frame; houses are two paths
  // (footprints, landmarks), the built-up tint one, the woods three; no cartouche, no tree symbols.
  assert(await page.locator('#world .slot-water *').count()>10);
  assert.equal(await page.locator('#world .slot-buildings path').count(),2);
  assert.equal(await page.locator('#world .m-builtup').count(),1);
  assert.equal(await page.locator('#world .slot-forest path').count(),3);
  assert.equal(await page.locator('#world .m-frame').count(),1);
  assert.equal(await page.locator('#world use, #world text').count(),0);
  assert.equal(await page.evaluate(()=>document.querySelector('#map').dataset.bld),'tint');
  // Markers: same-size A/B/C shapes at their true position, far zoom as dots; no type
  // badges, leader lines or filters; U places are not drawn.
  assert(await page.locator('#markers .mk').count()>15);
  assert.equal(await page.locator('#markers .mk[data-id^="U"]').count(),0);
  assert.equal(await page.locator('#markers path, #map [filter]').count(),0);
  assert.equal(await page.locator('#markers .mk--a').first().getAttribute('aria-label').then(t=>/^\d+ .+, .+, .+$/.test(t)),true);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  // Block 09: no page header; a hidden H1, the skip link to the map, the brand in the panel head
  // (desktop) or the brand chip (phone); both open the site menu.
  assert.equal(await page.locator('h1').count(),1);
  assert.match(await page.locator('h1').innerText(),/^Map of Derry, Maine/);
  assert.equal(await page.locator('.skip-link[href="#map"]').count(),1);
  const menuOpener=name==='mobile'?'.brand-chip':'.index-head [data-menu-open]';
  assert.equal(await page.locator(menuOpener).isVisible(),true);
  await page.locator(menuOpener).click();
  assert.equal(await page.locator('#site-menu').isVisible(),true);
  assert.equal(await page.locator('#site-menu a[href="/method/"]').count(),1);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#site-menu').isVisible(),false);
  await page.screenshot({path:path.join(out,name+'-town.png'),fullPage:true});
  // The list: 92 rows, the number in the marker style, meta "Kind · period · confidence".
  assert.equal(await page.locator('#list .place-row').count(),92);
  // No matches: the final copy is concise, and its button resets the search.
  await page.locator('#search').fill('lighthouse');
  await page.waitForFunction(()=>DerryAtlas.view.search==='lighthouse');
  assert.equal(await page.locator('#list .list-empty h3').innerText(),'Nothing in Derry matches “lighthouse”');
  assert.equal(await page.locator('#list .list-empty p').innerText(),'Try a different search.');
  assert.equal(await page.locator('#list [data-clear-search]').innerText(),'Clear search');
  await page.locator('#list [data-clear-search]').click();
  assert.equal(await page.locator('#search').inputValue(),'');
  assert.equal(await page.locator('#list .place-row').count(),92);
  assert.match(await page.locator('#list .place-row[data-place="5"] .place-row__meta').innerText(),/^Civic · .+ · inferred$/);
  if(name==='mobile'){
   // Phone (block 09b): a bottom sheet over a full-screen map: peek → "List ↑" → full → "Show map".
   assert.equal(await page.locator('#index').getAttribute('data-sheet'),'peek');
   assert.equal(await page.locator('#list').isVisible(),false);
   await page.locator('[data-sheet-to="full"]').click();
   assert.equal(await page.locator('#index').getAttribute('data-sheet'),'full');
   assert.equal(await page.locator('#list').isVisible(),true);
   // Category is a modal sheet: Tab stays inside, Esc closes it and restores the opener.
   await page.locator('#catBtn').click();
   assert.equal(await page.locator('#catMenu').getAttribute('role'),'dialog');
   assert.equal(await page.locator('#catMenu').getAttribute('aria-modal'),'true');
   await page.locator('#catMenu [data-cat-close]').focus();
   await page.keyboard.press('Shift+Tab');
   assert.equal(await page.evaluate(()=>document.activeElement.hasAttribute('data-cat-apply')),true);
   await page.keyboard.press('Tab');
   assert.equal(await page.evaluate(()=>document.activeElement.hasAttribute('data-cat-close')),true);
   await page.locator('#map').focus();
   await page.keyboard.press('Tab');
   assert.equal(await page.evaluate(()=>document.activeElement.hasAttribute('data-cat-close')),true);
   await page.keyboard.press('Escape');
   assert.equal(await page.evaluate(()=>document.activeElement.id),'catBtn');
   assert.equal(await page.locator('#catMenu').getAttribute('role'),'group');
   assert.equal(await page.locator('#catMenu').getAttribute('aria-modal'),null);
   await page.locator('.sheet-pill').click();
   assert.equal(await page.locator('#index').getAttribute('data-sheet'),'peek');
  }
  await page.locator('#search').fill('library');
  // Block 10: results after a 150 ms pause, the match marked, "Zoom to N places", the pill; the map stays put.
  await page.waitForFunction(()=>DerryAtlas.view.search==='library');
  assert.equal(await page.locator('#count').innerText(),'3 places match');
  assert.equal(await page.locator('#list mark').count(),3);
  if(name==='desktop')assert.deepEqual(await page.locator('#mapKey .key__count').allInnerTexts(),['2','1','0','0']);
  assert.match(page.url(),/\?q=library$/);
  if(name==='desktop')assert.match(await page.locator('#mapPill').innerText(),/Showing 3 results for “library”/);
  if(name==='mobile')assert.equal(await page.locator('#index').getAttribute('data-sheet'),'half');
  assert((await page.locator('#list .place-row').count())>=1);
  await page.locator('#list .place-row[data-place="12"]').click();
  // The card replaces the list; focus goes to its heading; ?place follows the card.
  assert.equal(await page.locator('#browse').isVisible(),false);
  assert.match(await page.locator('#detail h2').innerText(),/Library/);
  assert.equal(await page.evaluate(()=>document.activeElement.id),'place-title');
  assert.match(await page.locator('#detail .place-card__back').textContent(),/Back to results/);
  if(name==='mobile'){
   assert.equal(await page.locator('#index').getAttribute('data-sheet'),'card');
   // The place stays visible above the card sheet.
   const mk=await page.locator('#markers .mk[data-id="12"]').boundingBox(),sheetTop=(await page.locator('#index').boundingBox()).y;
   assert(mk&&mk.y+mk.height<sheetTop);
  }
  assert.match(page.url(),/\?q=library&place=12$/);
  assert.match(await page.locator('.lang a[hreflang="ru"]').first().getAttribute('href'),/place=12/);
  assert.match(await page.locator('#detail .card-sec summary').innerText(),/In the novel\s*3 chapters/i);
  await page.screenshot({path:path.join(out,name+'-library.png'),fullPage:true});
  // Pager: every place in map-number order; Esc closes and returns focus to the row.
  assert.equal(await page.locator('#detail .place-card__pager .t-meta').innerText(),'1 / 3');
  await page.locator('#detail [data-step="1"]').click();
  assert.equal(await page.evaluate(()=>DerryAtlas.view.selected),13);
  await page.locator('#detail [data-step="-1"]').click();
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#detail').isVisible(),false);
  assert.equal(await page.evaluate(()=>document.activeElement.dataset.place),'12');
  if(name==='mobile')assert.equal(await page.locator('#index').getAttribute('data-sheet'),'half');
  assert.doesNotMatch(page.url(),/place=/);
  // Esc in the field clears the query and leaves the map where it is.
  const before=await page.evaluate(()=>{const v=DerryAtlas.view;return [v.cx,v.cy,v.k].join()});
  await page.locator('#search').press('Escape');
  assert.equal(await page.locator('#search').inputValue(),'');
  assert.equal(await page.evaluate(()=>{const v=DerryAtlas.view;return [v.cx,v.cy,v.k].join()}),before);
  assert.equal(await page.locator('#list .place-row').count(),92);
  // Sort: Name A–Z through the listbox; the order lands in the address.
  if(name==='desktop'){
   await page.locator('#sortBtn').click();await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');
   assert.match(page.url(),/sort=name/);
   assert.equal(await page.locator('#list .place-row__title').first().innerText(),'127 Lower Main Street');
   await page.locator('#sortBtn').click();await page.keyboard.press('ArrowUp');await page.keyboard.press('Enter');
   assert.doesNotMatch(page.url(),/sort=/);
  }
  // Filters: the key hides C on the map and in the list; Category and With photos; all in the address.
  if(name==='desktop'){
   const rows=await page.locator('#list .place-row').count();
   await page.locator('#mapKey [data-hide="C"]').click();
   assert.equal(await page.locator('#markers .mk--c').count(),0);
   assert(await page.locator('#list .place-row').count()<rows);
   assert.match(page.url(),/hide=C/);
   await page.locator('#mapKey [data-hide="C"]').click();
   await page.locator('#catBtn').click();
   await page.locator('#catOpts [data-kind="Homes"]').click();
   assert.match(await page.locator('#catBtn').innerText(),/5 of 6/);
   assert.match(page.url(),/kind=civic,barrens,encounters,historical,outlying/);
   await page.keyboard.press('Escape');
   assert.equal(await page.evaluate(()=>document.activeElement.id),'catBtn');
   await page.locator('#catBtn').click();await page.locator('[data-cat-all]').click();await page.keyboard.press('Escape');
   await page.locator('#mapKey [data-list="unlocated"]').click();
   assert.equal(await page.locator('#list .place-row').count(),8);
   await page.locator('#listAll').click();
   assert.equal(await page.locator('#list .place-row').count(),92);
   assert.doesNotMatch(page.url(),/kind=|hide=|list=/);
  }
  await page.locator('#search').fill('Juniper Hill');
  await page.waitForFunction(()=>DerryAtlas.view.search==='juniper hill');
  await page.locator('#list .place-row').click();
  assert.match(await page.locator('#detail').innerText(),/No location/i);
  assert.equal(await page.locator('#detail .num--u').innerText(),'U4');
  if(name==='desktop')assert.match(await page.locator('#mapNotice').innerText(),/has no point on the map/);
  assert.equal(await page.locator('#detail .place-card__pager .t-meta').innerText(),'1 / 1');
  await page.locator('#detail button[data-close][aria-label]').click();
  await page.locator('#clearSearch').click();
  // Without a search the pager walks all 92 places: 84 → U1.
  await page.evaluate(()=>DerryAtlas.select(84));
  await page.locator('#detail [data-step="1"]').click();
  assert.equal(await page.evaluate(()=>DerryAtlas.view.selected),'U1');
  await page.locator('#detail button[data-close][aria-label]').click();
  assert.equal(await page.locator('#mapNotice').innerText(),'');
  // Block 11: on the phone the views, measure, the key and the layers live in the "Map" sheet.
  const viewBtn=async view=>{if(name==='mobile'){await page.locator('#mapSheetBtn').click();await page.locator(`#mapSheet [data-view="${view}"]`).click()}else await page.locator(`.viewbar [data-view="${view}"]`).click()};
  for(const view of ['central','barrens','camp']){
   await viewBtn(view);
   assert.equal(await page.evaluate(()=>DerryAtlas.view.view),view);
  }
  await page.screenshot({path:path.join(out,name+'-clearing.png'),fullPage:true});
  const k=await page.evaluate(()=>DerryAtlas.view.k);
  await page.locator('#zoomIn').click();assert((await page.evaluate(()=>DerryAtlas.view.k))>k);
  // The zoom cap is k 2.2: + is disabled there.
  for(let i=0;i<12;i++)await page.evaluate(()=>document.querySelector('#zoomIn').disabled||document.querySelector('#zoomIn').click());
  assert.equal(await page.evaluate(()=>Math.round(DerryAtlas.view.k*100)),220);
  assert.equal(await page.locator('#zoomIn').isDisabled(),true);
  await viewBtn('camp');
  await page.locator('#map').focus();await page.keyboard.press('ArrowRight');
  // Layers: a popover (desktop) or the Map sheet (phone); relief starts off on the phone; the
  // choice survives a reload.
  const L=name==='mobile'?'#sheet-':'#';
  if(name==='mobile'){assert.equal(await page.evaluate(()=>DerryAtlas.view.relief),false);await page.locator('#mapSheetBtn').click();await page.locator(L+'showRelief').check()}
  else await page.locator('#layersBtn').click();
  await page.locator(L+'showRelief').uncheck();
  assert.equal(await page.locator('#world .relief').first().evaluate(n=>getComputedStyle(n).display),'none');
  assert.equal(await page.locator('#landLabels .peak').count(),0);
  await page.locator(L+'showRelief').check();
  await page.locator(L+'showBuildings').uncheck();
  assert.equal(await page.locator('#world .buildings').first().evaluate(n=>getComputedStyle(n).display),'none');
  await page.locator(L+'showBuildings').check();
  assert(await page.locator('.lbl--place').count()>0);await page.locator(L+'showNames').uncheck();assert.equal(await page.locator('.lbl--place').count(),0);
  await page.locator(L+'showNames').check();
  await page.locator(L+'showPhotos').uncheck();assert.equal(await page.locator('#photoLayer .ph,.ph-dot').count(),0);
  assert.equal(JSON.parse(await page.evaluate(()=>localStorage.getItem('derry.layers'))).photos,false);
  await page.locator(L+'showPhotos').check();
  await page.keyboard.press('Escape');
  assert.equal(await page.locator(name==='mobile'?'#mapSheet':'#layers').isVisible(),false);
  // Photo layer (block 13): sepia dots far out, medallions at mid zoom (hover pops the print),
  // polaroids close in. Desktop only (hover); a fresh install may hold zero photos.
  if(name==='desktop'&&await page.evaluate(()=>DerryAtlas.photoFeatureCount)){
   await page.evaluate(()=>DerryAtlas.fit('city'));
   assert(await page.locator('#markers .ph-dot').count()>0);
   assert.equal(await page.locator('#photoLayer .ph').count(),0);
   await page.evaluate(()=>DerryAtlas.setView(-1510,-540,.3));
   const med=page.locator('#photoLayer .ph-medal[data-key="12"]');
   if(await med.count()){
    assert.match(await med.getAttribute('aria-label'),/^Photographs · Derry Public Library/);
    assert(!await med.locator('.ph-pop').isVisible());
    await med.hover();assert(await med.locator('.ph-pop').isVisible());
   }
   await page.evaluate(()=>DerryAtlas.setView(-1510,-540,.9));
   assert(await page.locator('#photoLayer .ph-near').count()>0);
   const pol=page.locator('#photoLayer .ph-near[data-key="12"]');
   if(await pol.count()){
    await pol.click();
    assert.match(await page.locator('#detail').innerText(),/Library/);
    assert(await page.locator('#detail .card-photo').count()>0);
    assert(await page.locator('#detail .place-card__more a').count()===1);
   }
   await page.evaluate(()=>DerryAtlas.fit('city'));
  }
  // Measure: metres and feet, with the reconstruction caveat; Esc leaves the mode.
  if(name==='mobile'){await page.locator('#mapSheetBtn').click();await page.locator('[data-measure-start]').click()}
  else await page.locator('#measure').click();
  assert.equal(await page.locator('#measureHint').isVisible(),true);
  const box=await page.locator('#map').boundingBox();
  await page.mouse.click(box.x+box.width*.25,box.y+box.height*.3);
  await page.mouse.click(box.x+box.width*.65,box.y+box.height*.45);
  assert.match(await page.locator('#measureResult').textContent(),/^≈ [\d.,]+ (m|km) · [\d,]+ ft · in the reconstruction$/);
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('#measureHint').isVisible(),false);
  const url=process.env.DERRY_URL||'http://127.0.0.1:8765';
  await page.goto(url+'/method/',{waitUntil:'networkidle'});
  assert.match(await page.locator('.method-page h1').innerText(),/Built from the novel/);
  assert.equal(await page.locator('.source-list__item').count(),7);
  assert.equal(await page.locator('.matrix__row').count(),4);
  // Place index: all tiles are server-rendered; places.js filters, sorts and keeps the URL.
  await page.goto(url+'/places/',{waitUntil:'networkidle'});
  assert.equal(await page.locator('.tile').count(),92);
  const search=name==='mobile'?'#placeSearchPhone':'#placeSearch';
  await page.locator(search).fill('library');
  await page.waitForFunction(()=>/library/.test(location.search));
  assert.equal(await page.locator('.tile:visible').filter({hasText:'Derry Public Library'}).count(),1);
  await page.locator(search).press('Escape');
  await page.waitForFunction(()=>!/q=/.test(location.search));
  if(name==='mobile'){
    await page.locator('#openFilters').click();
    assert.equal(await page.locator('#placeFilters[role="dialog"]').count(),1);
  }
  await page.locator('#placeFilters label:has(input[name="sure"][value="u"])').click();
  assert.equal(await page.locator('.tile:visible').count(),8);
  assert.match(page.url(),/sure=u/);
  // Faceted counts: with "No location" checked the categories count only U places (none have one).
  assert.equal(await page.locator('#placeFilters input[name="kind"]:disabled').count(),
               await page.locator('#placeFilters input[name="kind"]').count());
  await page.locator((name==='mobile'?'#placeFilters':'.index-results__tools')+' [data-view="compact"]').click();
  assert.equal(await page.locator('#placesList').evaluate(n=>n.classList.contains('index-list--compact')),true);
  if(name==='mobile'){
    await page.locator('#placeFilters .index-filters__foot [data-close-filters]').click();
    assert.equal(await page.locator('#openFilters').evaluate(b=>b.classList.contains('btn--primary')),true);
  }
  assert.match(page.url(),/view=compact/);
  // Old links keep working: ?confidence=U&location=unlocated → sure=u
  await page.goto(url+'/places/?confidence=U&location=unlocated',{waitUntil:'networkidle'});
  assert.equal(await page.locator('.tile:visible').count(),8);
  assert.match(page.url(),/sure=u/);
  assert.doesNotMatch(page.url(),/confidence=|location=/);
  // Photo gallery: map deep link and back; a fresh install may hold zero photos.
  await page.goto(url+'/?place=12',{waitUntil:'networkidle'});
  await page.waitForFunction(()=>window.DerryAtlas?.view.selected===12,null,{timeout:120000});
  assert.match(await page.locator('#detail h2').innerText(),/Place 12:/i);
  // The deep link centres the place (on the phone, in the map above the card sheet).
  assert.equal(await page.evaluate(()=>Math.round(DerryAtlas.view.cx)),-1510);
  if(name==='desktop')assert.equal(await page.evaluate(()=>Math.round(DerryAtlas.view.cy)),-540);
  // The card links to the standalone place page (indexable, English slug), in a new tab.
  const placeLink=page.locator('#detail .place-card__foot a');
  const placeHref=await placeLink.getAttribute('href');
  assert.equal(await placeLink.getAttribute('target'),'_blank');
  assert.equal(await placeLink.getAttribute('rel'),'noopener');
  assert.match(await placeLink.innerText(),/Open place page\s+\(opens in a new tab\)/);
  assert.match(placeHref,/^\/places\/12(-|\/)/);
  const mapUrl=page.url(),popupPromise=page.waitForEvent('popup');
  await placeLink.click();
  const placePopup=await popupPromise;
  await placePopup.waitForLoadState('networkidle');
  assert.equal(page.url(),mapUrl);
  assert.equal(placePopup.url(),url+placeHref);
  await placePopup.close();
  await page.goto(url+placeHref,{waitUntil:'networkidle'});
  assert.match(await page.locator('.place-page h1').innerText(),/\S/);
  assert.equal(await page.locator('.crumbs li').count(),3);
  assert.equal(await page.locator('.related__row').count(),2);
  const relatedHrefs=await page.locator('.related__list a').evaluateAll(links=>links.map(a=>a.getAttribute('href')));
  assert.equal(relatedHrefs.length,8);
  assert.equal(new Set(relatedHrefs).size,relatedHrefs.length);
  // The Russian version serves the same map under /ru/.
  await page.goto(url+'/ru/',{waitUntil:'networkidle'});
  await page.waitForFunction(()=>window.DerryAtlas?.siteCount===84,null,{timeout:120000});
  assert.equal(await page.locator('html').getAttribute('lang'),'ru');
  await page.locator('#search').fill('квакозябра');
  await page.waitForFunction(()=>DerryAtlas.view.search==='квакозябра');
  assert.equal(await page.locator('#list .list-empty h3').innerText(),'В Дерри нет «квакозябра».');
  assert.equal(await page.locator('#list .list-empty p').innerText(),'Попробуйте изменить поисковую фразу.');
  assert.equal(await page.locator('#list [data-clear-search]').innerText(),'Очистить поиск');
  await page.locator('#list [data-clear-search]').click();
  assert.equal(await page.locator('#search').inputValue(),'');
  await page.goto(url+'/photos/',{waitUntil:'networkidle'});
  assert.equal(await page.locator('.crumbs li').count(),2);
  assert.match(await page.locator('#galleryStatus').innerText(),/\d+ photographs?/);
  // Gallery filters in the browser: up to two values reach the URL, a third only sessionStorage.
  const charOpts='#galleryFilters button[data-group="character"]:not([aria-disabled])';
  if(name==='desktop'&&await page.locator(charOpts).count()>=3){
   await page.locator(charOpts).nth(0).click();
   await page.waitForURL(/\/photos\/character\/[^/]+\/$/);
   await page.locator(charOpts+'[aria-checked="false"]').nth(0).click();
   await page.waitForURL(/\/photos\/\?character=[^&,]+,[^&,]+$/);
   const twoUrl=page.url();
   await page.locator(charOpts+'[aria-checked="false"]').nth(0).click();
   assert.equal(page.url(),twoUrl);
   assert.equal(await page.locator('#galleryChips .chip').count(),3);
   assert.equal(JSON.parse(await page.evaluate(()=>sessionStorage.getItem('derry.gallery'))).sel.character.length,3);
   await page.locator('.gallery-results__clear').click();
   await page.waitForURL(/\/photos\/$/);
   assert.equal(await page.locator('#galleryChips .chip').count(),0);
  }
  if(name==='mobile'){
   await page.locator('#openGalleryFilters').click();
   assert.equal(await page.locator('#galleryFilters').getAttribute('role'),'dialog');
   await page.keyboard.press('Escape');
   assert.equal(await page.locator('#galleryFilters').getAttribute('role'),null);
  }
  if(await page.locator('.gallery-item').count()){
   await page.locator('.gallery-item__link').first().click();
   await page.waitForURL(/\/photos\/\d+\/$/);
   assert.equal(await page.locator('.crumbs li').count(),3);
   assert(await page.locator('.viewer__facts').isVisible());
   assert.match(await page.locator('[data-counter]').innerText(),/^\d+ \/ \d+$/);
   const toMap=page.locator('a:has-text("Show on the map")');
   if(await toMap.count()){await toMap.first().click();await page.waitForFunction(()=>typeof window.DerryAtlas?.view.selected==='number',null,{timeout:120000})}
  }
  assert.deepEqual(errors,[]);
  reports.push({viewport:name,dimensions:size,checks:'map, 84+8 counts, server-rendered place directories, catalog search and filters, detail, unlocated, four views, zoom, keyboard, layers, photo layer, ruler, method page, place page, ru version, gallery deep links',errors});
  await context.close();
 }
 // Responsive regression: with a plain (non-mobile) viewport the layout viewport cannot
 // expand to fit overflowing content, so any real overflow shows up as scrollWidth > 390.
 {
  const url=process.env.DERRY_URL||'http://127.0.0.1:8765';
  const context=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:1});
  const page=await context.newPage();
  await page.goto(url+'/photos/',{waitUntil:'networkidle'});
  const photoHref=await page.locator('.gallery-item__link').count()?await page.locator('.gallery-item__link').first().getAttribute('href'):null;
  const pages=['/','/places/','/photos/','/method/','/places/12-derry-public-library/',
   '/is-derry-maine-real/','/how-bangor-inspired-derry-maine/','/books-set-in-derry-maine/'];
  if(photoHref)pages.push(photoHref);
  for(const lang of ['','/ru'])for(const p of pages){
   await page.goto(url+lang+p,{waitUntil:'networkidle'});
   if(p==='/')await page.waitForFunction(()=>window.DerryAtlas?.siteCount===84,null,{timeout:120000});
   const m=await page.evaluate(()=>{const r=document.querySelector('.lang').getBoundingClientRect();return{over:document.documentElement.scrollWidth-window.innerWidth,langIn:r.left>=0&&r.right<=window.innerWidth}});
   assert.equal(m.over<=0,true,(lang+p)+' overflows horizontally by '+m.over+'px at 390px');
   assert.equal(m.langIn,true,(lang+p)+' clips the language switcher at 390px');
  }
  reports.push({viewport:'narrow-390',dimensions:{width:390,height:844},checks:'no horizontal overflow, language switcher reachable (en+ru: map, place directory, gallery, photo, place, method, editorial hubs)',errors:[]});
  await context.close();
 }
 fs.writeFileSync(path.join(out,'browser-report.json'),JSON.stringify({browser:browser.version(),reports},null,2));
 console.log(JSON.stringify(reports,null,2));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});

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
  await page.waitForFunction(()=>window.DerryAtlas?.siteCount===84,{timeout:120000});
  assert.equal(await page.evaluate(()=>DerryAtlas.unlocatedCount),8);
  // The crawlable directory is present independently of the JS-built sidebar.
  assert.equal(await page.locator('.place-directory-list a').count(),92);
  assert.equal(await page.locator('.place-directory-list a[href="/places/12-derry-public-library/"]').count(),1);
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
  assert(await page.locator('.brand h1').evaluate(n=>n.getBoundingClientRect().top>=0));
  await page.screenshot({path:path.join(out,name+'-town.png'),fullPage:true});
  if(name==='mobile')await page.locator('#placesToggle').click();
  await page.locator('#search').fill('library');
  assert((await page.locator('#list button').count())>=1);
  await page.locator('#list button[data-place="12"]').click();
  assert.match(await page.locator('#detail').innerText(),/Library/);
  await page.screenshot({path:path.join(out,name+'-library.png'),fullPage:true});
  await page.locator('#clearSearch').click();
  await page.locator('#search').fill('Juniper Hill');
  await page.locator('#list button').click();
  assert.match(await page.locator('#detail').innerText(),/U · No location/);
  await page.locator('#clearSearch').click();
  if(name==='mobile')await page.locator('#placesToggle').click();
  for(const view of ['central','barrens','camp']){
   await page.locator(`[data-view="${view}"]`).click();
   assert.equal(await page.evaluate(()=>DerryAtlas.view.view),view);
  }
  await page.screenshot({path:path.join(out,name+'-clearing.png'),fullPage:true});
  const k=await page.evaluate(()=>DerryAtlas.view.k);
  await page.locator('#zoomIn').click();assert((await page.evaluate(()=>DerryAtlas.view.k))>k);
  // The zoom cap is k 2.2: + is disabled there.
  for(let i=0;i<12;i++)await page.evaluate(()=>document.querySelector('#zoomIn').disabled||document.querySelector('#zoomIn').click());
  assert.equal(await page.evaluate(()=>Math.round(DerryAtlas.view.k*100)),220);
  assert.equal(await page.locator('#zoomIn').isDisabled(),true);
  await page.locator(`[data-view="camp"]`).click();
  await page.locator('#map').focus();await page.keyboard.press('ArrowRight');
  await page.locator('.map-legend summary').click();
  await page.locator('#showRelief').uncheck();
  assert.equal(await page.locator('#world .relief').first().evaluate(n=>getComputedStyle(n).display),'none');
  assert.equal(await page.locator('#landLabels .peak').count(),0);
  await page.locator('#showRelief').check();
  await page.locator('#showBuildings').uncheck();
  assert.equal(await page.locator('#world .buildings').first().evaluate(n=>getComputedStyle(n).display),'none');
  await page.locator('#showBuildings').check();
  assert(await page.locator('.lbl--place').count()>0);await page.locator('#showNames').uncheck();assert.equal(await page.locator('.lbl--place').count(),0);
  await page.locator('#showNames').check();
  await page.locator('#showPhotos').uncheck();assert.equal(await page.locator('#photoLayer .ph,.ph-dot').count(),0);
  await page.locator('#showPhotos').check();
  await page.locator('.map-legend summary').click();
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
    assert(await page.locator('#detail .card-photos-more a').count()===1);
   }
   await page.evaluate(()=>DerryAtlas.fit('city'));
  }
  await page.locator('#measure').click();
  const box=await page.locator('#map').boundingBox();
  await page.mouse.click(box.x+box.width*.25,box.y+box.height*.48);
  await page.mouse.click(box.x+box.width*.65,box.y+box.height*.55);
  assert.match(await page.locator('#toast').innerText(),/( m| km) · straight line/);
  await page.keyboard.press('Escape');
  // Sources & method lives on its own page now, linked from the header.
  const url=process.env.DERRY_URL||'http://127.0.0.1:8765';
  assert.equal(await page.locator('header a:has-text("Sources & method")').getAttribute('href'),'/method/');
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
  await page.waitForFunction(()=>window.DerryAtlas?.view.selected===12,{timeout:120000});
  assert.match(await page.locator('#detail').innerText(),/Place 12/i);
  // The card links to the standalone place page (indexable, English slug).
  const placeHref=await page.locator('#detail .card-page a').getAttribute('href');
  assert.match(placeHref,/^\/places\/12(-|\/)/);
  await page.goto(url+placeHref,{waitUntil:'networkidle'});
  assert.match(await page.locator('.place-page h1').innerText(),/\S/);
  assert.equal(await page.locator('.crumbs li').count(),3);
  assert.equal(await page.locator('.related__row').count(),2);
  const relatedHrefs=await page.locator('.related__list a').evaluateAll(links=>links.map(a=>a.getAttribute('href')));
  assert.equal(relatedHrefs.length,8);
  assert.equal(new Set(relatedHrefs).size,relatedHrefs.length);
  // The Russian version serves the same map under /ru/.
  await page.goto(url+'/ru/',{waitUntil:'networkidle'});
  await page.waitForFunction(()=>window.DerryAtlas?.siteCount===84,{timeout:120000});
  assert.equal(await page.locator('html').getAttribute('lang'),'ru');
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
   if(await toMap.count()){await toMap.first().click();await page.waitForFunction(()=>typeof window.DerryAtlas?.view.selected==='number',{timeout:120000})}
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
   if(p==='/')await page.waitForFunction(()=>window.DerryAtlas?.siteCount===84,{timeout:120000});
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

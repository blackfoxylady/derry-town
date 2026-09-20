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
  const page=await context.newPage();const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{if(r.url().startsWith(process.env.DERRY_URL||'http://127.0.0.1:8765')&&r.status()>=400)errors.push(r.status()+' '+r.url())});
  await page.goto(process.env.DERRY_URL||'http://127.0.0.1:8765',{waitUntil:'networkidle'});
  await page.waitForFunction(()=>window.DerryAtlas?.siteCount===83,{timeout:120000});
  assert.equal(await page.evaluate(()=>DerryAtlas.unlocatedCount),9);
  assert.equal(await page.locator('#world>*').count(),3071);
  assert(await page.locator('.mark').count()>15);
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
  assert.match(await page.locator('#detail').innerText(),/Unlocated/);
  await page.locator('#clearSearch').click();
  if(name==='mobile')await page.locator('#placesToggle').click();
  for(const view of ['central','barrens','camp']){
   await page.locator(`[data-view="${view}"]`).click();
   assert.equal(await page.evaluate(()=>DerryAtlas.view.view),view);
  }
  await page.screenshot({path:path.join(out,name+'-clearing.png'),fullPage:true});
  const k=await page.evaluate(()=>DerryAtlas.view.k);
  await page.locator('#zoomIn').click();assert((await page.evaluate(()=>DerryAtlas.view.k))>k);
  await page.locator('#map').focus();await page.keyboard.press('ArrowRight');
  await page.locator('.map-legend summary').click();
  await page.locator('#showRelief').uncheck();
  assert.equal(await page.locator('#world .relief').first().evaluate(n=>getComputedStyle(n).display),'none');
  await page.locator('#showRelief').check();
  await page.locator('#showBuildings').uncheck();
  assert.equal(await page.locator('#world .buildings').first().evaluate(n=>getComputedStyle(n).display),'none');
  await page.locator('#showBuildings').check();
  await page.locator('#showNames').uncheck();assert.equal(await page.locator('.map-name').count(),0);
  await page.locator('#showNames').check();
  await page.locator('.map-legend summary').click();
  await page.locator('#measure').click();
  const box=await page.locator('#map').boundingBox();
  await page.mouse.click(box.x+box.width*.25,box.y+box.height*.48);
  await page.mouse.click(box.x+box.width*.65,box.y+box.height*.55);
  assert.match(await page.locator('#toast').innerText(),/( m| km) · straight line/);
  await page.keyboard.press('Escape');
  await page.locator('#aboutBtn').click();assert(await page.locator('#about').isVisible());
  assert.equal(await page.locator('#sources .source').count(),7);
  await page.locator('#closeAbout').click();
  // Photo gallery: map deep link and back; a fresh install may hold zero photos.
  const url=process.env.DERRY_URL||'http://127.0.0.1:8765';
  await page.goto(url+'/?place=12',{waitUntil:'networkidle'});
  await page.waitForFunction(()=>window.DerryAtlas?.view.selected===12,{timeout:120000});
  assert.match(await page.locator('#detail').innerText(),/Place 12/i);
  await page.goto(url+'/photos/',{waitUntil:'networkidle'});
  assert.match(await page.locator('.status').innerText(),/\d+ photographs?/);
  if(await page.locator('.card').count()){
   await page.locator('.card .pic').first().click();
   await page.waitForURL(/\/photos\/\d+\/$/);
   assert(await page.locator('.facts').isVisible());
   const toMap=page.locator('a:has-text("Show on the map")');
   if(await toMap.count()){await toMap.first().click();await page.waitForFunction(()=>typeof window.DerryAtlas?.view.selected==='number',{timeout:120000})}
  }
  assert.deepEqual(errors,[]);
  reports.push({viewport:name,dimensions:size,checks:'map, 83+9 counts, search, detail, unlocated, four views, zoom, keyboard, layers, ruler, source dialog, gallery deep links',errors});
  await context.close();
 }
 fs.writeFileSync(path.join(out,'browser-report.json'),JSON.stringify({browser:browser.version(),reports},null,2));
 console.log(JSON.stringify(reports,null,2));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});

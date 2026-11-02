const $ = id => document.getElementById(id);
let session = null, character = null, currentFile = null, candidateBlob = null, fontURL = null, generation = 0, revision = 0, timer = null, flippable = [], accentSources = {}, candidateMethod = 'generated';
const groups = [
  ['Capitals', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'],
  ['Lowercase', 'abcdefghijklmnopqrstuvwxyz'],
  ['Accented letters', 'àèìǹòùẁỳâĉêĝĥîĵôŝûŵŷãĩñõũỹäëïöüẅÿåůāēīōūăĕğĭŏŭǎčďěǐľňǒřšťǔžċḋėġṅżőűáćéíḱĺńóŕśúẃýźçģķļņŗşţąęįųḍḥḳḷṇṛṣṭẓșț'],
  ['Numbers', '0123456789'],
  ['Basic symbols', Array.from({length: 94}, (_, i) => String.fromCharCode(i + 33)).filter(c => !/[A-Za-z0-9]/.test(c)).join('')],
  ['Typographic punctuation', '‘’“”–—…•'],
  ['Currency & legal', '€£¥¢©®™'],
  ['International punctuation', '¿¡«»‹›'],
  ['Useful marks', '°×÷±µ§¶†‡']
];
const samples = [
  'naïve Noël über möbel süd',
  'Hello, world! Meet us @ 7:30.',
  'Save 25% on coffee & cake!',
  'Order #42: 2 cups + 1 treat = $12.50',
  'Is it A/B testing? Yes (version 2.0).',
  'Your code: [ABC-123] {ready}',
  'Write to hello@example.com & say "Hi!"',
  'From 9-5: ideas, notes & more.',
  'Set x > 2, y < 10; then x = y.',
  'File_name: v1.2 / path\\to\\type',
  "It's a 100% good day: why not?",
  'Try *bold* + _underline_ ~ or ^more^.',
  'A | B: `type` at $5.00',
  '“Hello…” — it’s 20° today • enjoy!',
  'Tea & cake: €12, £10 or ¥1,500 © 2026',
  '¿Listo? ¡Vamos! «Oui» ‹yes›',
  '2 × 3 = 6; 8 ÷ 2 = 4 ± 1 µm § 2 ¶ 4 † ‡ ® ™ ¢'
];
let uploadURL = null;
const controls = ['size', 'spacing', 'offset', 'horizontal'];
function status(message) { $('status').textContent = message; }
function ready() {
  $('bulk-prepare').disabled = !session || !$('rights').checked || bulkBusy;
  const source = accentSources[character], accent = !!source, unavailable = source === 'missing base' || (source && source.includes('safely separable'));
  $('generate').disabled = !session || !character || !$('rights').checked || unavailable;
  const flip = flippable.includes(character);
  $('generate-text').textContent = accent ? (source === 'AI accent' ? 'Generate an accent' : 'Create accented letter') : flip ? 'Create from upright character' : 'Generate character';
  $('method-note').textContent = unavailable ? 'This font needs a usable base letter and, for some letters, a separable i or j dot.' : accent ? (source === 'AI accent' ? 'No suitable mark was found. Generation sends a specimen to fal and may incur API charges.' : `Uses the font’s ${source}; no image generation or API charge.`) : flip ? 'Uses the existing upright character; no image generation or API charge.' : 'Generation sends a rendered specimen to fal and may incur API charges. Limited to 100 attempts per day, resetting at midnight Pacific time.';
}
function resetResult() { revision++; clearTimeout(timer); $('empty').hidden = false; $('result').hidden = true; $('download').removeAttribute('href'); if(fontURL) URL.revokeObjectURL(fontURL); fontURL = null; }
function drawSymbols(missing = []) {
  const missingSet = new Set(missing);
  $('symbols').replaceChildren();
  for (const [label, chars] of groups) {
    const section = document.createElement('section'); section.className = 'symbol-group';
    const heading = document.createElement('h3'); heading.textContent = label; section.append(heading);
    const grid = document.createElement('div'); grid.className = 'symbol-grid';
    for (const c of chars) {
      const b = document.createElement('button'); b.type='button'; b.disabled=!session; b.className='symbol' + (missingSet.has(c) ? ' missing' : '') + (c === character ? ' selected' : ''); b.textContent=c;
      b.setAttribute('aria-label', `${c} ${!session ? 'not yet checked' : missingSet.has(c) ? 'missing or empty' : 'present'}`); b.setAttribute('aria-pressed', c===character);
      b.onclick=()=>{ if (character !== c) { generation++; resetResult(); character=c; drawSymbols(missing); ready(); status(''); } }; grid.append(b);
    }
    section.append(grid); $('symbols').append(section);
  }
}
function exampleForCharacter(c) {
  const matches = samples.filter(text => text.includes(c));
  return matches.length ? matches[Math.floor(Math.random() * matches.length)] : `Aa ${c} 123`;
}
function drawSample(missing) {
  const missingSet = new Set(missing);
  const score = text => new Set([...text].filter(c => missingSet.has(c))).size;
  const best = Math.max(...samples.map(score));
  const choices = samples.filter(text => score(text) === best);
  let text = choices[Math.floor(Math.random() * choices.length)];
  // If the phrases don't contain any missing character, include one explicitly.
  if (!best && missing.length) text += `  /  ${missing[Math.floor(Math.random() * missing.length)]}`;
  $('sample').replaceChildren();
  let present = '';
  for (const c of text) {
    if (!missingSet.has(c)) { present += c; continue; }
    if (present) { $('sample').append(document.createTextNode(present)); present = ''; }
    const span = document.createElement('span'); span.className = 'sample-missing'; span.textContent = c;
    span.setAttribute('aria-label', `${c} missing or empty`); $('sample').append(span);
  }
  if (present) $('sample').append(document.createTextNode(present));
  $('sample-wrap').hidden = false;
}
async function post(path, data) {
  const r = await fetch(path,{method:'POST',body:data});
  if (!r.ok) { const body=await r.json().catch(()=>({})); throw new Error(body.error || 'Something went wrong. Please try again.'); }
  return r;
}
document.querySelector('.upload').addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('font').click(); } });
async function loadFont(file) {
  if(!file)return;
  resetBulk();
  const token=++generation; session=null; character=null; flippable=[]; accentSources={}; currentFile=file; candidateBlob=null; resetResult(); drawSymbols(); ready(); $('font-info').hidden=true; $('sample-wrap').hidden=true; $('filename').textContent=file.name; status('Checking your font…');
  try { const data=new FormData(); data.append('font',file); const info=await (await post('/api/font',data)).json(); if(token!==generation)return; const url=URL.createObjectURL(file); const face=new FontFace('FontFillerUpload', `url(${url})`); try { await face.load(); } catch (error) { URL.revokeObjectURL(url); throw new Error('Could not display this font in your browser.'); } if(token!==generation){URL.revokeObjectURL(url);return;} for(const existing of document.fonts) if(existing.family==='FontFillerUpload') document.fonts.delete(existing); document.fonts.add(face); if(uploadURL) URL.revokeObjectURL(uploadURL); uploadURL=url; session=info.session; flippable=info.flippable || []; accentSources=info.accent_sources || {}; character=info.missing[0] || null; drawSymbols(info.missing); drawSample(info.missing); $('font-info').textContent=`${info.family} · ${info.missing.length} missing or empty characters`; $('font-info').hidden=false; status(info.missing.length ? '' : 'No missing characters in this set. Choose one to try a replacement.'); ready(); }
  catch(e){if(token===generation)status(e.message);}
}
$('font').addEventListener('change', e => { const file = e.target.files[0]; e.target.value = ''; loadFont(file); });
const upload = document.querySelector('.upload');
for (const event of ['dragenter', 'dragover']) upload.addEventListener(event, e => { e.preventDefault(); upload.classList.add('drag-over'); if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'; });
for (const event of ['dragleave', 'drop']) upload.addEventListener(event, e => { e.preventDefault(); if (event === 'drop' || !upload.contains(e.relatedTarget)) upload.classList.remove('drag-over'); });
upload.addEventListener('drop', e => {
  const files = e.dataTransfer.files;
  if (files.length !== 1) { status('Please drop one font file at a time.'); return; }
  loadFont(files[0]);
});
$('rights').addEventListener('change', ready);
async function create(forceAI=false){
 if(!session||!character||!$('rights').checked)return;
 const token=++generation, activeCharacter=character, flip=flippable.includes(character), accent=!!accentSources[character];
 const useAI=accent && (forceAI || accentSources[character]==='AI accent');
 resetResult(); $('generate').disabled=true; $('again').disabled=true;
 status(useAI ? `Generating an accent for ${activeCharacter}… This can take a minute.` : accent ? `Preparing ${activeCharacter} from your font…` : flip ? `Preparing ${activeCharacter} from its upright character…` : `Generating ${activeCharacter}… This can take a minute.`);
 try {
   candidateMethod = accent ? (useAI ? 'accent-ai' : 'accent') : flip ? 'flip' : 'generated'; candidateBlob = null;
   if (candidateMethod==='generated' || candidateMethod==='accent-ai') {
     const data=new FormData(); data.append('font',currentFile); data.append('character',activeCharacter); data.append('method',candidateMethod);
     const result=await (await post('/api/generate',data)).json(); if(token!==generation)return;
     candidateBlob=await (await fetch(result.image)).blob(); if(token!==generation)return;
   }
   $('candidate').textContent='…'; $('candidate').style.fontFamily=''; $('candidate-label').textContent=activeCharacter;
   $('candidate-description').textContent=accent ? (useAI ? 'AI-generated accent on your original letter.' : `Accent made from the font’s ${accentSources[activeCharacter]}.`) : flip ? 'Rotated from the existing upright character in your font.' : 'Your traced character, shown in the updated font.';
   $('again').hidden=flip; $('again').textContent=accent ? (useAI ? '↻ Generate another AI accent' : '✳ Try an AI accent (may incur charges)') : '↻ Generate another';
   $('spacing-control').hidden=accent; $('horizontal-control').hidden=!accent; $('fixed-note').hidden=accent; $('size-label').textContent=accent?'Accent size':'Size';
   $('preview').style.fontFamily=''; $('preview').textContent=exampleForCharacter(activeCharacter);
   for(const id of controls) $(id).value=(id==='offset'||id==='horizontal')?0:100;
   updateLabels(); $('empty').hidden=true; $('result').hidden=false; status('Preparing your preview…'); await preview(token);
 } catch(e){if(token===generation)status(e.message);} finally{if(token===generation){$('again').disabled=false;ready();}}
}
$('generate').onclick=()=>create(false); $('again').onclick=()=>create(!!accentSources[character]);
function updateLabels(){ $('size-value').textContent=$('size').value+'%'; $('spacing-value').textContent=$('spacing').value+'%'; $('offset-value').textContent=$('offset').value; $('horizontal-value').textContent=$('horizontal').value; }
async function preview(token=generation){
 const version=++revision; const data=new FormData(); data.append('font',currentFile);data.append('method',candidateMethod); if(candidateBlob) data.append('image',candidateBlob,'glyph.png');data.append('character',character);data.append('scale',Number($('size').value)/100);data.append('spacing',Number($('spacing').value)/100);data.append('offset',Number($('offset').value)/100);data.append('horizontal',Number($('horizontal').value)/100);
 try {const response=await post('/api/export',data); const overhang=response.headers.get('X-Accent-Overhang')==='1', collision=response.headers.get('X-Accent-Collision')==='1', unattached=response.headers.get('X-Accent-Unattached')==='1', nudged=response.headers.get('X-Accent-Nudged')==='1'; const blob=await response.blob(); if(version!==revision||token!==generation)return; const url=URL.createObjectURL(blob); const face=new FontFace('FontFillerPreview',`url(${url})`); await face.load(); if(version!==revision||token!==generation){URL.revokeObjectURL(url);return;} for(const existing of document.fonts) if(existing.family==='FontFillerPreview')document.fonts.delete(existing); document.fonts.add(face); $('candidate').textContent=character; $('candidate').style.fontFamily='FontFillerPreview, sans-serif'; $('candidate').setAttribute('aria-label', `Generated character: ${character}`); $('preview').style.fontFamily='FontFillerPreview, sans-serif'; $('download').href=url; $('download').download='font-filler.' + (blob.type === 'font/otf' ? 'otf' : 'ttf'); if(fontURL)URL.revokeObjectURL(fontURL); fontURL=url; status([nudged ? 'The accent position was adjusted automatically. Review it and use the controls to change it.' : '', overhang ? 'The accent extends beyond the letter’s advance. Check it beside neighboring characters.' : '', collision ? 'The floating accent may overlap the letter. Check its position.' : '', unattached ? 'The accent may not connect to the letter. Check its position.' : ''].filter(Boolean).join(' '));}
 catch(e){if(version===revision && token===generation)status(e.message);}
}
for(const id of controls) $(id).addEventListener('input',()=>{updateLabels(); revision++; $('download').removeAttribute('href'); clearTimeout(timer); timer=setTimeout(()=>preview(),200);});
drawSymbols();

let bulkFont = null, bulkURL = null, bulkRemaining = [], bulkCandidates = [], bulkRun = 0, bulkBusy = false, bulkShownFont = null;
function resetBulk() {
  bulkRun++; bulkBusy=false; bulkFont=null; bulkShownFont=null; bulkRemaining=[]; bulkCandidates=[];
  if (bulkURL) URL.revokeObjectURL(bulkURL); bulkURL=null;
  $('bulk-ready').hidden=true; $('bulk-list').replaceChildren(); $('bulk-status').textContent='';
  $('bulk-download').hidden=true; $('bulk-download').removeAttribute('href');
  $('bulk-apply').disabled=true; $('bulk-generate').disabled=true;
}
function bulkFileFromBase64(encoded) {
  const raw=atob(encoded), bytes=new Uint8Array(raw.length);
  for(let i=0;i<raw.length;i++) bytes[i]=raw.charCodeAt(i);
  return new File([bytes], currentFile.name, {type:currentFile.type});
}
function refreshBulk() {
  const n=Number($('bulk-grid').value)**2, count=bulkRemaining.length;
  $('bulk-summary').textContent=`${count} characters remain missing in the supported character set.`;
  $('bulk-cost').textContent=count ? `Up to ${Math.ceil(count/n)} image requests, roughly $${(Math.ceil(count/n)*.01).toFixed(2)} plus token charges; retries cost more. The shared daily limit applies.` : 'No supported characters remain missing.';
  $('bulk-generate').disabled=bulkBusy||!bulkFont||!count||!$('rights').checked;
  $('bulk-apply').disabled=bulkBusy||!$('rights').checked||!bulkCandidates.some(c=>c.selected && c.image);
  if(bulkFont && bulkShownFont!==bulkFont) {
    bulkShownFont=bulkFont;
    if(bulkURL) URL.revokeObjectURL(bulkURL);
    bulkURL=URL.createObjectURL(bulkFont); $('bulk-download').href=bulkURL;
    const shown=bulkFont, face=new FontFace('FontFillerBulk',`url(${bulkURL})`); face.load().then(loaded=>{if(shown!==bulkFont)return; for(const old of document.fonts) if(old.family==='FontFillerBulk')document.fonts.delete(old); document.fonts.add(loaded); $('bulk-preview').style.fontFamily='FontFillerBulk, sans-serif';}).catch(()=>{});
    $('bulk-download').download=currentFile.name.toLowerCase().endsWith('.otf')?'font-filler-bulk.otf':'font-filler-bulk.ttf';
    $('bulk-download').hidden=false;
  }
}
$('bulk-grid').addEventListener('change',refreshBulk);
$('rights').addEventListener('change',()=>{if(bulkFont)refreshBulk();});
$('bulk-prepare').onclick=async()=>{
  if(!session || !$('rights').checked)return;
  const run=++bulkRun; $('bulk-prepare').disabled=true; $('bulk-status').textContent='Preparing characters from your font…';
  try {
    const form=new FormData();form.append('font',currentFile);const result=await (await post('/api/bulk/prepare',form)).json();if(run!==bulkRun)return;
    bulkFont=bulkFileFromBase64(result.font);bulkRemaining=result.remaining;bulkCandidates=[];$('bulk-list').replaceChildren();$('bulk-ready').hidden=false;
    $('bulk-status').textContent=`Prepared ${result.added.length} characters: ${result.added.join(' ') || 'none'}. ${result.warnings.join(' ')}`; $('bulk-preview').textContent=result.added.join(' ') || 'Aa 123';refreshBulk();
  } catch(e){if(run===bulkRun)$('bulk-status').textContent=e.message;} finally {if(run===bulkRun)ready();}
};
function drawBulkCandidates(){
 $('bulk-list').replaceChildren();
 for(const c of bulkCandidates){
  const card=document.createElement('label');card.className='bulk-candidate';
  const check=document.createElement('input');check.type='checkbox';check.checked=!!c.selected;check.disabled=!c.image;check.addEventListener('change',()=>{c.selected=check.checked;refreshBulk();});
  const title=document.createElement('strong');title.textContent=`Requested: ${c.character}`;
  card.append(check,title);
  if(c.image){const img=document.createElement('img');img.src=c.image;img.alt=`Generated candidate for ${c.character}; review before selecting`;card.append(img);}
  const note=document.createElement('small');note.textContent=c.warnings.length?c.warnings.join(' '):'Review shape and identity.';card.append(note);$('bulk-list').append(card);
 }
 refreshBulk();
}
$('bulk-generate').onclick=async()=>{
 if(!bulkFont || !$('rights').checked || !bulkRemaining.length)return;
 const run=++bulkRun, size=Number($('bulk-grid').value), n=size*size, existing=new Set(bulkCandidates.map(c=>c.character)), todo=bulkRemaining.filter(c=>!existing.has(c));
 if(!todo.length){$('bulk-status').textContent='All remaining characters already have candidates. Review them below.';return;}
 bulkBusy=true;drawBulkCandidates();$('bulk-generate').disabled=true;$('bulk-prepare').disabled=true;$('bulk-grid').disabled=true;
 try {
  for(let i=0;i<todo.length;i+=n){
   if(run!==bulkRun)return;
   $('bulk-status').textContent=`Generating batch ${Math.floor(i/n)+1} of ${Math.ceil(todo.length/n)}…`;
   const form=new FormData();form.append('font',bulkFont);form.append('characters',todo.slice(i,i+n).join(''));form.append('grid',size);
   const result=await (await post('/api/bulk/generate',form)).json();if(run!==bulkRun)return;
   bulkCandidates.push(...result.crops.map(c=>({...c,selected:false})));drawBulkCandidates();$('bulk-generate').disabled=true;
  }
  $('bulk-status').textContent='Review each candidate, select the ones you want, then add them to the font.';
 }catch(e){if(run===bulkRun)$('bulk-status').textContent=`Generation stopped: ${e.message} Completed candidates are available below.`;}
 finally{if(run===bulkRun){bulkBusy=false;$('bulk-grid').disabled=false;ready();refreshBulk();}}
};
$('bulk-apply').onclick=async()=>{
 const chosen=bulkCandidates.filter(c=>c.selected && c.image);if(!chosen.length||!bulkFont||!$('rights').checked||bulkBusy)return;
 const run=++bulkRun; bulkBusy=true; $('bulk-apply').disabled=true;$('bulk-generate').disabled=true;$('bulk-prepare').disabled=true; $('bulk-status').textContent='Adding reviewed characters…';
 let added=0, failures=[];
 try{
  for(let i=0;i<chosen.length;i+=16){
   const batch=chosen.slice(i,i+16), form=new FormData(); form.append('font',bulkFont);form.append('characters',batch.map(c=>c.character).join(''));
   for(const c of batch) form.append('images',await (await fetch(c.image)).blob(),'glyph.png');
   const result=await (await post('/api/bulk/apply',form)).json();if(run!==bulkRun)return;
   bulkFont=bulkFileFromBase64(result.font);bulkRemaining=result.remaining;added+=result.added.length;failures.push(...result.failed.map(f=>`${f.character}: ${f.error}`));
   const done=new Set(result.added);bulkCandidates=bulkCandidates.filter(c=>!done.has(c.character));
  }
  $('bulk-status').textContent=`Added ${added} reviewed characters. ${failures.join(' ')}`; $('bulk-preview').textContent += ' ' + chosen.slice(0,added).map(c=>c.character).join(' ');drawBulkCandidates();
 }catch(e){if(run===bulkRun)$('bulk-status').textContent=`Stopped after adding ${added}: ${e.message}`;}
 finally{if(run===bulkRun){bulkBusy=false;ready();drawBulkCandidates();}}
};

// A quiet, rolling field of type, held still when reduced motion is requested.
(() => {
  const canvas = $('glyph-field'), ctx = canvas.getContext('2d');
  if (!ctx) return;
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const glyphs = 'aegmnorsuvxyz23456789&%+?';
  let width, height, frame = 0, last = 0;
  function resize() {
    const ratio = Math.min(devicePixelRatio || 1, 2);
    width = innerWidth; height = innerHeight;
    canvas.width = width * ratio; canvas.height = height * ratio;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    draw(0);
  }
  function draw(time) {
    ctx.clearRect(0, 0, width, height);
    ctx.font = '11px monospace';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    const step = 16, t = time * 0.00018;
    for (let y = 0; y < height + step; y += step) {
      for (let x = 0; x < width + step; x += step) {
        const wave = (Math.sin(x * .009 + y * .005 + t) + Math.sin(y * .011 - x * .004 - t * .8) + 2) / 4;
        const alpha = .035 + wave * .19;
        ctx.fillStyle = `rgba(126, 174, 112, ${alpha})`;
        const index = (Math.floor(x / step) * 17 + Math.floor(y / step) * 31) % glyphs.length;
        ctx.fillText(glyphs[index], x, y);
      }
    }
  }
  function animate(time) {
    if (motion.matches || document.hidden) { frame = 0; return; }
    if (time - last > 50) { draw(time); last = time; }
    frame = requestAnimationFrame(animate);
  }
  function update() {
    if (frame) cancelAnimationFrame(frame);
    frame = 0; draw(0);
    if (!motion.matches && !document.hidden) frame = requestAnimationFrame(animate);
  }
  addEventListener('resize', resize);
  document.addEventListener('visibilitychange', update);
  motion.addEventListener('change', update);
  resize(); update();
})();

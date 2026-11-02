import base64,json,subprocess,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; DEST=Path(__file__).resolve().parent
URL='https://font-filler-a68787bhi-kans-projects-d62f37a9.vercel.app'
CASES=[('allura','Allura-Regular.ttf','$'),('cameo','Cameoantique-VLPw.ttf','&'),('pazea','Pazea-2v4Wd.ttf','&'),('alex','AlexBrush-Regular.ttf','&'),('abril','AbrilFatface-Regular.ttf','%'),('abhaya','AbhayaLibre-Regular.ttf','@'),('spaceship','CfSpaceshipRegular-2d4e.ttf','@')]
def run(job):
 count,(name,font,char)=job; method='sheet' if count==0 else 'three'; file=DEST/f'{name}-{method}.json';start=time.monotonic()
 cmd=['vercel','curl','/api/generate','--deployment',URL,'--','--silent','--show-error','--form',f'font=@{ROOT / "testFonts" / font}','--form-string',f'character={char}','--form-string','model=gpt','--form-string',f'reference_count={count}','--form-string','style_emphasis=1','--output',str(file),'--write-out','%{http_code}']
 proc=subprocess.run(cmd,capture_output=True,text=True,timeout=150)
 try:
  data=json.loads(file.read_text());status=proc.stdout.strip();uri=data.get('image','')
  if uri.startswith('data:image/png;base64,'):
   (DEST/f'{name}-{method}.png').write_bytes(base64.b64decode(uri.split(',',1)[1]));result='ok'
  else:result=data.get('error','unexpected response')
 except Exception as exc:status='error';result=str(exc)
 file.unlink(missing_ok=True);print(f'{name} {method}: HTTP {status}, {result}, {time.monotonic()-start:.1f}s',flush=True)
 return {'font':name,'method':method,'status':status,'result':result}
jobs=[(n,c) for n in (0,3) for c in CASES if not (DEST/f'{c[0]}-{"sheet" if n==0 else "three"}.png').exists()]
with ThreadPoolExecutor(max_workers=3) as pool: results=[f.result() for f in as_completed([pool.submit(run,j) for j in jobs])]
old=json.loads((DEST/'results.json').read_text()) if (DEST/'results.json').exists() else []
replaced={(r['font'],r['method']) for r in results}
(DEST/'results.json').write_text(json.dumps([r for r in old if (r['font'],r['method']) not in replaced]+results,indent=2)+'\n')

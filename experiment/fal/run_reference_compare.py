import base64, json, subprocess, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
DEST=Path(__file__).resolve().parent
URL='https://font-filler-kk76eejuq-kans-projects-d62f37a9.vercel.app'
CASES=[('ostrich','ostrich-regular.ttf','&'),('kool','KoolBeans-eerm.ttf','@'),('mono','monofonto.ttf','%'),('signature','Perfectsignature.ttf','$')]
def run(job):
 count,(name,font,char)=job; model=f'ref{count}'; p=DEST/f'{name}-{model}.json'; start=time.monotonic()
 cmd=['vercel','curl','/api/generate','--deployment',URL,'--','--silent','--show-error','--form',f'font=@{ROOT / "testFonts" / font}','--form-string',f'character={char}','--form-string','model=gpt','--form-string',f'reference_count={count}','--output',str(p),'--write-out','%{http_code}']
 proc=subprocess.run(cmd,capture_output=True,text=True,timeout=150)
 try:
  data=json.loads(p.read_text()); status=proc.stdout.strip()
  if data.get('image','').startswith('data:image/png;base64,'):
   (DEST/f'{name}-{model}.png').write_bytes(base64.b64decode(data['image'].split(',',1)[1])); result='ok'
  else: result=data.get('error','unexpected response')
 except Exception as exc: status='error'; result=str(exc)
 p.unlink(missing_ok=True)
 print(f'{name} {model}: HTTP {status}, {result}, {time.monotonic()-start:.1f}s',flush=True)
 return {'font':name,'model':model,'status':status,'result':result}
jobs=[(n,c) for n in [1,3,5] for c in CASES if not (DEST/f'{c[0]}-ref{n}.png').exists()]
with ThreadPoolExecutor(max_workers=4) as pool:
 results=[f.result() for f in as_completed([pool.submit(run,j) for j in jobs])]
old=json.loads((DEST/'reference-results.json').read_text()) if (DEST/'reference-results.json').exists() else []
replaced={(r['font'],r['model']) for r in results}
(DEST/'reference-results.json').write_text(json.dumps([r for r in old if (r['font'],r['model']) not in replaced]+results,indent=2)+'\n')

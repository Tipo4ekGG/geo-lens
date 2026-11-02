from __future__ import annotations
import base64,hashlib,hmac,io,json,os,re,shutil,sqlite3,threading,time,uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import FileResponse,JSONResponse
from PIL import Image
from .engine import Agent,DockerRunner,Stopped,confined,artifacts,SCRIPTS

Image.MAX_IMAGE_PIXELS=40_000_000
class Jobs:
 def __init__(self,root):
  self.root=Path(root).resolve();self.root.mkdir(parents=True,exist_ok=True)
  self.stopping=False;self.db=self.root/'jobs.sqlite';self.lock=threading.RLock();self.pool=ThreadPoolExecutor(max_workers=1)
  with self.connect() as c:
   c.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,status TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,message TEXT NOT NULL,model TEXT NOT NULL,context TEXT NOT NULL,cancelled INTEGER NOT NULL DEFAULT 0)')
   c.execute("UPDATE jobs SET status='failed',message='Сервер перезапущен. Создайте новое задание.' WHERE status IN ('queued','running')")
 def connect(self):
  c=sqlite3.connect(self.db,timeout=10);c.row_factory=sqlite3.Row;return c
 def update(self,id,**fields):
  allowed={'status','message','cancelled'}
  if not fields or not set(fields)<=allowed:raise ValueError('Invalid job update')
  fields['updated']=time.time()
  with self.connect() as c:c.execute('UPDATE jobs SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',[*fields.values(),id])
 def get(self,id):
  if not re.fullmatch('[a-f0-9]{32}',id):raise HTTPException(404,'Задание не найдено')
  with self.connect() as c:r=c.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone()
  if not r:raise HTTPException(404,'Задание не найдено')
  return dict(r)
 def cleanup(self):
  cutoff=time.time()-int(os.getenv('RETENTION_HOURS','24'))*3600
  with self.lock,self.connect() as c:
   rows=c.execute("SELECT id FROM jobs WHERE updated<? AND status NOT IN ('queued','running')",(cutoff,)).fetchall()
   for r in rows:shutil.rmtree(self.root/r['id'],ignore_errors=True)
   c.execute("DELETE FROM jobs WHERE updated<? AND status NOT IN ('queued','running')",(cutoff,))
 def create(self,body,start=True):
  self.cleanup()
  with self.lock,self.connect() as c:
   count=c.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
   if count>=3:raise HTTPException(429,'Очередь заполнена. Дождитесь завершения задания.')
   if shutil.disk_usage(self.root).free<2*1024**3:raise HTTPException(507,'На сервере недостаточно свободного места.')
   data=body.get('image','');model=body.get('model');context=body.get('context','')
   if not isinstance(model,str) or not model.strip() or len(model)>200:raise HTTPException(400,'Не выбрана модель')
   if not isinstance(context,str) or len(context)>2000:raise HTTPException(400,'Слишком длинная подсказка')
   if not isinstance(data,str) or len(data)>28_000_000 or not re.match(r'^data:image/(jpeg|png|webp);base64,',data):raise HTTPException(400,'Нужен JPEG, PNG или WebP до 20 МБ')
   try:
    raw=base64.b64decode(data.split(',',1)[1],validate=True)
    if len(raw)>20*1024**2:raise ValueError('too large')
    with Image.open(io.BytesIO(raw)) as image:
     if image.format not in ('JPEG','PNG','WEBP') or image.width*image.height>40_000_000:raise ValueError('Image dimensions or type')
     image.verify()
   except Exception:raise HTTPException(400,'Изображение повреждено, слишком велико или не поддерживается')
   id=uuid.uuid4().hex;folder=self.root/id;folder.mkdir(mode=0o700);(folder/'photo.jpg').write_bytes(raw)
   now=time.time();c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,0)',(id,'queued',now,now,'В очереди',model,context))
  if start:self.pool.submit(self.work,id)
  return {'id':id,'status':'queued'}
 def work(self,id):
  record=self.get(id)
  if record['cancelled']:self.update(id,status='cancelled',message='Задание отменено');return
  self.update(id,status='running',message='Запуск полного geo-sleuth')
  folder=self.root/id
  notify=lambda msg:self.update(id,message=msg[:1000])
  cancelled=lambda:self.stopping or bool(self.get(id)['cancelled'])
  runner_class=DockerRunner
  if os.getenv('RUNNER_MODE')=='native_mac':
   from .macos.native import NativeRunner
   runner_class=NativeRunner
  runner=runner_class(folder,id,notify,cancelled,time.monotonic()+int(os.getenv('JOB_TIMEOUT_SECONDS','1800')))
  try:
   agent=Agent(os.environ['PHOTO_API_BASE'],os.environ['PHOTO_API_KEY'])
   agent.investigate(folder,record['model'],record['context'],runner,notify)
   self.update(id,status='completed',message='Отчёт готов')
  except Stopped as e:self.update(id,status='cancelled' if cancelled() else 'failed',message=str(e))
  except Exception as e:
   message=str(e)
   for name in ['PHOTO_API_KEY','BACKEND_TOKEN']:
    if os.environ.get(name):message=message.replace(os.environ[name],'[REDACTED]')
   self.update(id,status='failed',message=message[:1000])
 def public(self,id):
  record=self.get(id);record.pop('context',None);record.pop('cancelled',None);record['artifacts']=artifacts(self.root/id)
  if record['status']=='completed':
   try:record['result']=json.loads((self.root/id/'result.json').read_text())
   except (ValueError,OSError):record['status']='failed';record['message']='Файл результата недоступен'
  return record

@asynccontextmanager
async def lifespan(app):
 for name in ['PHOTO_API_BASE','PHOTO_API_KEY','BACKEND_TOKEN']:
  if not os.getenv(name):raise RuntimeError('Missing server setting '+name)
 if len(os.environ['BACKEND_TOKEN'])<32:raise RuntimeError('BACKEND_TOKEN must contain at least 32 characters')
 app.state.jobs=Jobs(os.getenv('JOB_ROOT','/var/lib/geo-lens/jobs'))
 yield
 app.state.jobs.stopping=True
 app.state.jobs.pool.shutdown(wait=False,cancel_futures=True)

app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
@app.middleware('http')
async def auth(request,call_next):
 if request.url.path!='/health':
  expected=os.getenv('BACKEND_TOKEN','');actual=request.headers.get('authorization','').removeprefix('Bearer ')
  if not expected or not hmac.compare_digest(hashlib.sha256(actual.encode()).digest(),hashlib.sha256(expected.encode()).digest()):return JSONResponse({'error':'Доступ запрещён'},status_code=401)
 response=await call_next(request);response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff';return response
@app.exception_handler(HTTPException)
async def handled(request,exc):return JSONResponse({'error':str(exc.detail)},status_code=exc.status_code)
@app.get('/health')
def health():return {'ok':True,'mode':'full','operators':len(SCRIPTS)}
async def body_json(request,max_bytes=29_000_000):
 data=bytearray()
 async for part in request.stream():
  data.extend(part)
  if len(data)>max_bytes:raise HTTPException(413,'Тело запроса слишком велико')
 try:r=json.loads(data)
 except (ValueError,UnicodeError):raise HTTPException(400,'Неверный JSON')
 if not isinstance(r,dict):raise HTTPException(400,'Неверный JSON')
 return r
@app.post('/api/full/jobs')
async def create(request:Request):
 body=await body_json(request)
 return request.app.state.jobs.create(body)
@app.post('/api/full/jobs/{id}')
def status(id:str,request:Request):
 request.app.state.jobs.cleanup();return request.app.state.jobs.public(id)
@app.post('/api/full/jobs/{id}/cancel')
def cancel(id:str,request:Request):
 jobs=request.app.state.jobs;r=jobs.get(id)
 if r['status'] in ('queued','running'):jobs.update(id,cancelled=1,message='Отмена запрошена')
 return {'id':id,'status':r['status']}
@app.post('/api/full/artifact')
async def artifact(request:Request):
 body=await body_json(request,10000);id=body.get('id','');jobs=request.app.state.jobs;jobs.get(id)
 try:p=confined(jobs.root/id,body.get('path',''))
 except (ValueError,TypeError):raise HTTPException(400,'Недопустимый путь')
 if not p.is_file() or p.stat().st_size>64*1024**2:raise HTTPException(404,'Файл не найден или слишком велик')
 return FileResponse(p,filename=p.name,media_type='application/octet-stream')

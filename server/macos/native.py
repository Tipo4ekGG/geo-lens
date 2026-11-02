"""Native Mac execution with Seatbelt file sandbox and aggregate RSS limit."""
from __future__ import annotations
import json,os,signal,subprocess,time
from pathlib import Path
import psutil
from server.engine import DockerRunner,ROOT,SKILL,SCRIPTS,Stopped


def quote(value):return json.dumps(str(value))

def sandbox_profile(job,cache,python,root=ROOT):
 # Do not grant access to the entire home directory or the config directory.
 # Package manager Python may reside outside the venv, so include its real installation.
 python_root=Path(python).resolve().parent.parent
 read=[Path('/System'),Path('/usr'),Path('/bin'),Path('/sbin'),Path('/Library'),Path('/private/etc'),Path('/private/var/db/timezone'),Path('/dev'),python_root,root/'.venv-tools',SKILL,root/'server',job,cache]
 write=[job,cache]
 return '\n'.join(['(version 1)','(deny default)','(allow process* mach-lookup sysctl-read ipc-posix* signal network*)','(allow file-read-metadata)',*[f'(allow file-read* (subpath {quote(p.resolve())}))' for p in read],*[f'(allow file-map-executable (subpath {quote(p.resolve())}))' for p in read if p not in [job,cache]],*[f'(allow file-write* (subpath {quote(p.resolve())}))' for p in write]])+'\n'

def tool_env(job,cache,python):
 # Only non-secret runtime settings are forwarded to skill subprocesses.
 env={k:os.environ[k] for k in ['LANG','LC_ALL','LC_CTYPE','TZ','HTTP_PROXY','HTTPS_PROXY','NO_PROXY','ALL_PROXY','GEO_PROXY','SSL_CERT_FILE','REQUESTS_CA_BUNDLE','NODE_EXTRA_CA_CERTS'] if k in os.environ}
 env.update({'PATH':str(Path(python).parent)+':/usr/bin:/bin:/usr/sbin:/sbin','HOME':str(cache/'home'),'TMPDIR':str(job/'tmp'),'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1','GEO_DEVICE':'cpu','OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2','MKL_NUM_THREADS':'2','VECLIB_MAXIMUM_THREADS':'2','TOKENIZERS_PARALLELISM':'false','PLAYWRIGHT_BROWSERS_PATH':str(cache/'browsers'),'HF_HOME':str(cache/'huggingface'),'UV_CACHE_DIR':str(cache/'uv'),'UV':str(ROOT/'server/macos/uv-native'),'GEO_TOOL_PYTHON':str(python),'GEO_TOOL_ROOT':str(SKILL),'GEO_TOOL_BOOTSTRAP':str(ROOT/'server/macos/tool_bootstrap.py')})
 return env

class NativeRunner(DockerRunner):
 paths_hint='Native Mac: skill files are read through skill/<path>; each command starts in its job directory. Use relative file paths. /work paths are mapped into the current job. Do not use shell commands.'
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs)
  self.cache=Path(os.environ['NATIVE_CACHE']).expanduser().resolve()
  self.python=Path(os.environ.get('TOOL_PYTHON',str(ROOT/'.venv-tools/bin/python')))
  for p in [self.job/'tmp',self.cache/'home',self.cache/'huggingface',self.cache/'uv']:p.mkdir(parents=True,exist_ok=True)
 def _command(self,script,args):
  if not Path('/usr/bin/sandbox-exec').exists():raise RuntimeError('macOS sandbox-exec отсутствует. Автоматический небезопасный запуск отключён.')
  profile=self.job/'tool.sb';profile.write_text(sandbox_profile(self.job,self.cache,self.python))
  return ['/usr/bin/sandbox-exec','-f',str(profile),str(self.python),str(ROOT/'server/macos/tool_bootstrap.py'),script,*args]
 def _mapped(self,value):
  if value=='/work':return str(self.job)
  if value.startswith('/work/'):return str(self.job/value[6:])
  if value=='/opt/skill':return str(SKILL)
  if value.startswith('/opt/skill/'):return str(SKILL/value[11:])
  return value
 def run(self,script,args):
  self.check()
  if script not in SCRIPTS or not isinstance(args,list) or len(args)>120 or any(not isinstance(x,str) or len(x)>5000 or '\x00' in x for x in args):raise ValueError('Недопустимый инструмент или аргументы')
  args=[self._mapped(x) for x in args]
  limit=int(os.getenv('NATIVE_RSS_LIMIT_MB','3500'))*1024**2
  if script in {'match.py','sat_scan.py'} and psutil.virtual_memory().available<1200*1024**2:
   return {'returncode':75,'output':'Недостаточно свободной памяти для ML-оператора. Закройте другие приложения или используйте меньшую область поиска. Проверка не выполнена.'}
  command=self._command(script,args)
  item={'script':script,'args':args,'started_at':time.time(),'runner':'native_mac'};self.trace.append(item)
  self.notify('Выполняется '+script+' '+ ' '.join(args)[:120])
  log=self.job/f'tool-{len(self.trace)}.log';started=time.monotonic();reason=None;p=None
  try:
   with log.open('wb') as out:
    p=subprocess.Popen(command,cwd=self.job,stdout=out,stderr=subprocess.STDOUT,env=tool_env(self.job,self.cache,self.python),start_new_session=True)
    try:
     while p.poll() is None:
      self.check()
      if time.monotonic()-started>int(os.getenv('TOOL_TIMEOUT_SECONDS','900')):reason='Оператор превысил лимит времени.';break
      try:
       process=psutil.Process(p.pid);total=sum(c.memory_info().rss for c in [process,*process.children(recursive=True)] if c.is_running())
       if total>limit:reason='Оператор остановлен: превышен лимит памяти. Эта проверка не завершена.';break
      except (psutil.NoSuchProcess,psutil.AccessDenied):pass
      time.sleep(.3)
    finally:
     if p.poll() is None:
      try:os.killpg(p.pid,signal.SIGTERM)
      except ProcessLookupError:pass
      try:p.wait(timeout=5)
      except subprocess.TimeoutExpired:
       try:os.killpg(p.pid,signal.SIGKILL)
       except ProcessLookupError:pass
       p.wait(timeout=5)
   item['returncode']=p.returncode
   text=log.read_bytes()[-32000:].decode('utf8',errors='replace')
   if reason:text+='\n'+reason;item['returncode']=75
   item['output_file']=log.name
   return {'returncode':item['returncode'],'output':text,'log':log.name}
  finally:
   item['duration_seconds']=round(time.monotonic()-started,2)
   (self.job/'commands.json').write_text(json.dumps(self.trace,ensure_ascii=False,indent=2))


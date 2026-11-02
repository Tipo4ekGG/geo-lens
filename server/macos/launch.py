import json,os,signal,subprocess,sys,threading,time
from pathlib import Path
import httpx
from server.engine import ROOT
state=Path.home()/'Library/Application Support/GeoLens';path=state/'config.json'
if not path.exists():raise SystemExit('Сначала выполните Install on Intel Mac.command.')
config=json.loads(path.read_text());cache=Path.home()/'Library/Caches/GeoLens'
env={**os.environ,'PHOTO_API_BASE':config['api_base'],'PHOTO_API_KEY':config['api_key'],'BACKEND_TOKEN':config['backend_token'],'JOB_ROOT':str(state/'jobs'),'RUNNER_MODE':'native_mac','NATIVE_CACHE':str(cache),'TOOL_PYTHON':str(ROOT/'.venv-tools/bin/python'),'NATIVE_RSS_LIMIT_MB':'3500','MAX_AGENT_STEPS':'24','JOB_TIMEOUT_SECONDS':'2400','TOOL_TIMEOUT_SECONDS':'900','RETENTION_HOURS':'24'}
try:
 import socket
 with socket.socket() as sock:
  sock.bind(('127.0.0.1',8080))
except OSError:raise SystemExit('Порт 8080 уже занят. Закройте предыдущий запуск Geo Lens.')
api=subprocess.Popen([sys.executable,'-m','uvicorn','server.app:app','--host','127.0.0.1','--port','8080','--workers','1','--no-access-log'],cwd=ROOT,env=env,start_new_session=True)
tunnel=None
try:
 ready=False
 for _ in range(40):
  if api.poll() is not None:raise RuntimeError('Локальный сервер завершился. Смотрите ошибку выше.')
  try:
   with httpx.Client(timeout=1,trust_env=False) as client:ready=client.get('http://127.0.0.1:8080/health').status_code==200
  except httpx.HTTPError:pass
  if ready:break
  time.sleep(.5)
 if not ready:raise RuntimeError('Локальный сервер не запустился')
 # No provider credentials are given to cloudflared.
 tunnel=subprocess.Popen([str(state/'bin/cloudflared'),'tunnel','--url','http://127.0.0.1:8080'],cwd=ROOT,env=os.environ.copy(),start_new_session=True)
 print('\nСервер работает. Ниже cloudflared покажет HTTPS URL *.trycloudflare.com.',flush=True)
 print('Этот адрес нужно добавить в FULL_BACKEND_URL вашего Worker. Для остановки нажмите Ctrl+C.',flush=True)
 print('Код для FULL_BACKEND_TOKEN копируется командой Copy Backend Token.command.',flush=True)
 while api.poll() is None and tunnel.poll() is None:time.sleep(1)
except KeyboardInterrupt:print('\nОстанавливаем сервер…')
finally:
 for proc in [api,tunnel]:
  if proc and proc.poll() is None:
   try:os.killpg(proc.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   try:proc.wait(timeout=10)
   except subprocess.TimeoutExpired:
    try:os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError:pass

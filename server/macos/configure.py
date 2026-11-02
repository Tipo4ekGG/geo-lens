import getpass,json,os,secrets,tempfile
from pathlib import Path
from urllib.parse import urlparse
state=Path.home()/'Library/Application Support/GeoLens';state.mkdir(parents=True,exist_ok=True);state.chmod(0o700)
path=state/'config.json';old={}
if path.exists():old=json.loads(path.read_text())
base=input('Base URL вашего API (включая /v1) ['+old.get('api_base','https://freecodex.fun/v1')+']: ').strip() or old.get('api_base','https://freecodex.fun/v1')
u=urlparse(base)
if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment:raise SystemExit('Нужен полный HTTPS Base URL API.')
key=getpass.getpass('API-ключ (скрытый ввод; Enter сохраняет прежний): ') or old.get('api_key','')
if not key:raise SystemExit('Ключ не задан')
config={**old,'api_base':base.rstrip('/'),'api_key':key,'backend_token':old.get('backend_token') or secrets.token_urlsafe(36)}
fd,tmp=tempfile.mkstemp(dir=state,prefix='.config-')
with os.fdopen(fd,'w') as f:json.dump(config,f,indent=2);f.write('\n')
os.chmod(tmp,0o600);os.replace(tmp,path)
print('Настройки сохранены только на этом Mac. Не отправляйте config.json в чат или GitHub.')

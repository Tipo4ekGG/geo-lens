import json,os,platform,tempfile,time
from pathlib import Path
from server.macos.native import NativeRunner
from server.engine import ROOT
if platform.system()!='Darwin' or platform.machine()!='x86_64':raise SystemExit('Проверку нужно запускать на Intel Mac.')
cache=Path.home()/'Library/Caches/GeoLens';os.environ['NATIVE_CACHE']=str(cache);os.environ['TOOL_PYTHON']=str(ROOT/'.venv-tools/bin/python')
state=Path.home()/'Library/Application Support/GeoLens';state.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(dir=state) as temp:
 runner=NativeRunner(Path(temp),'preflight',print,lambda:False,time.monotonic()+120)
 output=runner.run('doctor.py',['--json'])
 try:report=json.loads(output['output'])
 except ValueError:raise SystemExit('Проверка инструментов не прошла:\n'+output['output'])
 for item in report['checks']:print(item['status']+': '+item['name']+' — '+item['detail'])
 browser=next((c for c in report['checks'] if c['name']=='Reverse-search browser'),{})
 if not report.get('ok') or browser.get('status')!='PASS':raise SystemExit('Браузер или зависимости пока не работают. Сохраните текст ошибки для диагностики.')
print('Python, браузер, справочники и sandbox проверены. Реальные поиск/API и ML-веса проверяются первым исследованием.')

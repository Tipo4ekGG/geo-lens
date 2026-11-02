import json,os,platform,tempfile,time,subprocess
from server.macos.native import tool_env
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
 except ValueError:
  policy=(Path(temp)/'tool.sb').read_text()
  for name,rules in [('runtime', '(version 1)\n(allow default)\n'),('read-boundary','\n'.join(x for x in policy.splitlines() if '(deny file-write*' not in x)),('write-boundary','\n'.join(x for x in policy.splitlines() if '(deny file-read-data' not in x))]:
   diagnostic=subprocess.run(['/usr/bin/sandbox-exec','-p',rules,str(runner.python),'-c',"print('runtime-probe')"],env=tool_env(runner.job,cache,runner.python),capture_output=True,text=True,timeout=15)
   print(name+': rc='+str(diagnostic.returncode)+' stdout='+diagnostic.stdout[:200]+' stderr='+diagnostic.stderr[:2000])
  raise SystemExit('Проверка инструментов не прошла (код '+str(output.get('returncode'))+'):\n'+output['output'])
 for item in report['checks']:print(item['status']+': '+item['name']+' — '+item['detail'])
 browser=next((c for c in report['checks'] if c['name']=='Reverse-search browser'),{})
 if not report.get('ok') or browser.get('status')!='PASS':raise SystemExit('Браузер или зависимости пока не работают. Сохраните текст ошибки для диагностики.')
# Verify that the same working sandbox denies both reading and writing outside job/cache.
with tempfile.TemporaryDirectory(dir=state) as temp:
 job=Path(temp).resolve();sentinel=state/'sandbox-private-test.txt';sentinel.write_text('not-a-secret')
 runner=NativeRunner(job,'permission-test',lambda msg:None,lambda:False,time.monotonic()+60)
 from server.macos.native import sandbox_profile
 profile=job/'policy.sb';profile.write_text(sandbox_profile(job,cache,runner.python))
 try:
  for operation in ['read_text()',"write_text('denied')"]:
   code="from pathlib import Path; Path("+repr(str(sentinel))+').'+operation
   result=subprocess.run(['/usr/bin/sandbox-exec','-f',str(profile),str(runner.python),'-c',code],env=tool_env(job,cache,runner.python),capture_output=True,text=True,timeout=15)
   if result.returncode!=1 or 'PermissionError' not in result.stderr:raise SystemExit('Проверка изоляции файла не пройдена. Установка остановлена.')
 finally:sentinel.unlink(missing_ok=True)
print('Python, браузер, справочники и ограничения доступа проверены. Реальные поиск/API и ML-веса проверяются первым исследованием.')

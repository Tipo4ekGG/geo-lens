import base64,io,json,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from PIL import Image
from server.engine import Agent,DockerRunner,SKILL,SCRIPTS,confined,read_tool,validate_report,picture
from server.app import Jobs,app

TOKEN='test-backend-token-with-40-random-characters'
def photo():
 out=io.BytesIO();Image.new('RGB',(80,50),'blue').save(out,format='JPEG');return out.getvalue()
def data():return {'image':'data:image/jpeg;base64,'+base64.b64encode(photo()).decode(),'model':'vision-tools','context':'Моя фотография, тестовая головоломка'}

class PathsTests(unittest.TestCase):
 def test_confined_blocks_traversal_absolute_and_symlink(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'file.txt').write_text('ok');(root/'alias').symlink_to(root/'file.txt')
   for value in ['../outside','/etc/passwd','alias']:
    with self.assertRaises(ValueError):confined(root,value)
   self.assertEqual(confined(root,'file.txt').read_text(),'ok')
 def test_unicode_pagination(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);text='Координаты '*3000;(p/'x.txt').write_text(text)
   first=read_tool(p,'job/x.txt');second=read_tool(p,'job/x.txt',first['next_offset'])
   self.assertEqual(first['content']+second['content'],text)
 def test_bundled_skill_and_all_operators_present(self):
  self.assertEqual(len(list((SKILL/'scripts').glob('*.py'))),27)
  for name in ['match.py','sat_scan.py','terrain.py','intake.py','web_page.py']:self.assertIn(name,SCRIPTS)
 def test_original_photo_pixels_reach_model(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'photo.jpg';p.write_bytes(photo());self.assertTrue(picture(p).startswith('data:image/jpeg;base64,'))

class ReportsTests(unittest.TestCase):
 def test_unsupported_coordinates_are_removed_even_if_model_claims_success(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);r=validate_report({'summary':'Точное место найдено','confidence':'высокая','locations':[{'name':'Guess','latitude':1,'longitude':2}]},p,{'returncode':0,'output':'Result: pass'})
   self.assertFalse(r['board_check_passed']);self.assertNotIn('latitude',r['locations'][0]);self.assertIn('Низкая',r['confidence'])
 def test_evidence_file_and_board_check_both_required(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'crop.jpg').write_bytes(photo());(p/'board-report.json').write_text(json.dumps({'board':{'main':{'evidence':[{'status':'computed','file':'/work/crop.jpg'}]}}}))
   r=validate_report({'summary':'Bounded conclusion','locations':[{'name':'Candidate','latitude':1,'longitude':2}]},p,{'returncode':0,'output':'Result: pass'})
   self.assertTrue(r['board_check_passed']);self.assertEqual(r['locations'][0]['latitude'],1)
   r=validate_report({'summary':'bad'},p,{'returncode':0,'output':'Result: has FAIL, fix those first'})
   self.assertFalse(r['board_check_passed'])

class ApiTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'PHOTO_API_KEY':'fake-provider-secret','PHOTO_API_BASE':'https://provider.example/v1','BACKEND_TOKEN':TOKEN,'JOB_ROOT':self.tmp.name});self.env.start();self.client=TestClient(app);self.client.__enter__();self.auth={'Authorization':'Bearer '+TOKEN}
 def tearDown(self):self.client.__exit__(None,None,None);self.env.stop();self.tmp.cleanup()
 def test_missing_and_wrong_auth_rejected(self):
  for headers in [{},{'Authorization':'Bearer wrong'}]:self.assertEqual(self.client.post('/api/full/jobs',headers=headers,json=data()).status_code,401)
 def test_submit_status_cancel_artifact_and_traversal(self):
  jobs=self.client.app.state.jobs
  with patch.object(jobs.pool,'submit'):
   r=self.client.post('/api/full/jobs',headers=self.auth,json=data());self.assertEqual(r.status_code,200);id=r.json()['id']
  folder=Path(self.tmp.name)/id;self.assertEqual((folder/'photo.jpg').read_bytes(),photo())
  status=self.client.post('/api/full/jobs/'+id,headers=self.auth,json={});self.assertEqual(status.json()['status'],'queued');self.assertNotIn('context',status.json())
  self.assertEqual(self.client.post('/api/full/jobs/'+id+'/cancel',headers=self.auth,json={}).status_code,200);self.assertEqual(jobs.get(id)['cancelled'],1)
  r=self.client.post('/api/full/artifact',headers=self.auth,json={'id':id,'path':'photo.jpg'});self.assertEqual(r.content,photo())
  self.assertEqual(self.client.post('/api/full/artifact',headers=self.auth,json={'id':id,'path':'../../server.env'}).status_code,400)
 def test_invalid_image_and_queue_capacity(self):
  self.assertEqual(self.client.post('/api/full/jobs',headers=self.auth,json={**data(),'image':'data:image/jpeg;base64,bm90aW1hZ2U='}).status_code,400)
  with patch.object(self.client.app.state.jobs.pool,'submit'):
   for _ in range(3):self.assertEqual(self.client.post('/api/full/jobs',headers=self.auth,json=data()).status_code,200)
   self.assertEqual(self.client.post('/api/full/jobs',headers=self.auth,json=data()).status_code,429)
 def test_restart_marks_pending_jobs_interrupted(self):
  with patch.object(self.client.app.state.jobs.pool,'submit'):id=self.client.post('/api/full/jobs',headers=self.auth,json=data()).json()['id']
  other=Jobs(self.tmp.name)
  try:self.assertEqual(other.get(id)['status'],'failed')
  finally:other.pool.shutdown(wait=False)
 def test_health_does_not_expose_secrets(self):
  r=self.client.get('/health');self.assertEqual(r.status_code,200);self.assertNotIn('fake-provider-secret',r.text)

class ProviderTests(unittest.TestCase):
 def test_redirects_not_followed_and_key_not_reflected(self):
  calls=[]
  def endpoint(request):calls.append(request);return httpx.Response(302,headers={'location':'https://other.example'})
  a=Agent('https://provider.example/v1','never-reflect-me',transport=httpx.MockTransport(endpoint))
  with self.assertRaisesRegex(RuntimeError,'HTTP 302'):a.completion('vision',[])
  self.assertEqual(len(calls),1)
 def test_rejects_insecure_or_credential_bearing_provider(self):
  for url in ['http://provider.example/v1','https://user:pass@provider.example/v1']:
   with self.assertRaises(ValueError):Agent(url,'fake')
 def test_full_agent_uses_tool_calls_and_checks_board(self):
  with tempfile.TemporaryDirectory() as d:
   job=Path(d);(job/'photo.jpg').write_bytes(photo());calls=[]
   class Runner:
    deadline=time.monotonic()+100
    def check(self):pass
    def run(self,script,args):
     calls.append((script,args))
     if args and args[0]=='report':(job/'board-report.json').write_text('{"board":{"main":null}}')
     return {'returncode':0,'output':'Result: pass' if args[0]=='check' else 'fixture result'}
   reply={'choices':[{'message':{'role':'assistant','content':None,'tool_calls':[{'id':'finish-1','type':'function','function':{'name':'finish','arguments':json.dumps({'summary':'Недостаточно данных','confidence':'низкая','locations':[]})}}]}}]}
   requests=[]
   def endpoint(request):requests.append(json.loads(request.content));return httpx.Response(200,json=reply)
   output=Agent('https://provider.example/v1','fake',httpx.MockTransport(endpoint)).investigate(job,'vision','Мой снимок',Runner(),lambda msg:None)
   self.assertEqual(calls[0][0],'board.py');self.assertEqual(calls[1][0],'intake.py');self.assertIn(('board.py',['check']),calls);self.assertTrue(requests[0]['tools']);self.assertTrue((job/'result.json').exists());self.assertEqual(output['mode'],'full')

class ActualSkillTests(unittest.TestCase):
 def test_real_board_and_image_operators_on_generated_photo(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'photo.jpg').write_bytes(photo())
   for script,args in [('board.py',['init','--photo','photo.jpg']),('board.py',['check']),('exif.py',['photo.jpg']),('imgprep.py',['edges','photo.jpg','--out-dir','edges'])]:
    r=subprocess.run([sys.executable,str(SKILL/'scripts'/script),*args],cwd=p,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30)
    self.assertEqual(r.returncode,0,r.stderr)
   self.assertTrue((p/'board.json').exists());self.assertTrue(list((p/'edges').glob('*.jpg')))

if __name__=='__main__':unittest.main()

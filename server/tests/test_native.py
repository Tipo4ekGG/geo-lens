import json,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from server.macos.native import NativeRunner,sandbox_profile,tool_env
from server.engine import ROOT,SKILL

class NativeTests(unittest.TestCase):
 def test_tool_environment_has_no_provider_or_service_secrets(self):
  with patch.dict(os.environ,{'PHOTO_API_KEY':'private-provider','BACKEND_TOKEN':'private-backend','ACCESS_TOKEN':'private-browser','GH_TOKEN':'private-github'}):
   env=tool_env(Path('/tmp/job'),Path('/tmp/cache'),Path('/tools/python'))
   for name in ['PHOTO_API_KEY','BACKEND_TOKEN','ACCESS_TOKEN','GH_TOKEN']:self.assertNotIn(name,env)
   self.assertEqual(env['GEO_DEVICE'],'cpu');self.assertEqual(env['OMP_NUM_THREADS'],'2')
 def test_sandbox_does_not_grant_entire_home_or_config_directory(self):
  profile=sandbox_profile(Path('/Users/test/jobs/one'),Path('/Users/test/cache'),Path('/tools/bin/python'),Path('/Users/test/project'))
  self.assertIn('(deny file-read-data (require-not',profile);self.assertNotIn('(subpath "/Users/test")',profile);self.assertNotIn('config.json',profile)
  self.assertIn('/Users/test/jobs/one',profile);self.assertIn('/Users/test/project/.venv-tools',profile)
 def test_native_executes_original_operator_and_records_trace(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'NATIVE_CACHE':d+'/cache','TOOL_PYTHON':sys.executable}):
   job=Path(d)/'job';job.mkdir()
   runner=NativeRunner(job,'test',lambda msg:None,lambda:False,time.monotonic()+30)
   with patch.object(runner,'_command',side_effect=lambda script,args:[sys.executable,str(SKILL/'scripts'/script),*args]):
    result=runner.run('regions.py',['list'])
   self.assertEqual(result['returncode'],0,result['output']);self.assertEqual(json.loads((job/'commands.json').read_text())[0]['runner'],'native_mac')
 def test_no_arbitrary_script_or_argument_types(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'NATIVE_CACHE':d+'/cache','TOOL_PYTHON':sys.executable}):
   job=Path(d)/'job';job.mkdir();runner=NativeRunner(job,'test',lambda msg:None,lambda:False,time.monotonic()+30)
   for script,args in [('evil.py',[]),('../board.py',[]),('board.py',[None])]:
    with self.assertRaises(ValueError):runner.run(script,args)
 def test_virtual_paths_are_mapped_for_native_operator(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'NATIVE_CACHE':d+'/cache','TOOL_PYTHON':sys.executable}):
   job=Path(d)/'job';job.mkdir();runner=NativeRunner(job,'test',lambda msg:None,lambda:False,time.monotonic()+30)
   self.assertEqual(runner._mapped('/work/photo.jpg'),str(job/'photo.jpg'));self.assertEqual(runner._mapped('/opt/skill/SKILL.md'),str(SKILL/'SKILL.md'))

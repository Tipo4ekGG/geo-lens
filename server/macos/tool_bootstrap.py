"""Execute only shipped operators, using the pinned native tool environment."""
import os,runpy,sys
from pathlib import Path
root=Path(os.environ['GEO_TOOL_ROOT']).resolve()
script=sys.argv[1] if len(sys.argv)>1 else ''
if not script.endswith('.py') or Path(script).name!=script:raise SystemExit('Invalid operator name')
path=root/'scripts'/script
if script=='web_page.py':path=Path(__file__).resolve().parents[1]/'browse.py'
if not path.is_file():raise SystemExit('Bundled operator not found')
sys.path.insert(0,str(root/'scripts'));sys.argv=[str(path),*sys.argv[2:]]
runpy.run_path(str(path),run_name='__main__')

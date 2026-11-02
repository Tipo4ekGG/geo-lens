"""Additional isolated browser helper; upstream skill files are unchanged."""
import argparse,asyncio,ipaddress,json,socket
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

def public_url(url):
 u=urlparse(url)
 if u.scheme not in ('http','https') or not u.hostname or u.username or u.password:raise ValueError('Only public HTTP(S) URLs without credentials are allowed')
 for item in socket.getaddrinfo(u.hostname,u.port or (443 if u.scheme=='https' else 80),type=socket.SOCK_STREAM):
  if not ipaddress.ip_address(item[4][0]).is_global:raise ValueError('Private or non-public destination')
 return url

async def main(args):
 public_url(args.url)
 out=(Path.cwd()/args.out).resolve()
 if not out.is_relative_to(Path.cwd().resolve()):raise ValueError('Output must be in the job directory')
 out.parent.mkdir(parents=True,exist_ok=True)
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True)
  try:
   page=await browser.new_page(viewport={'width':1280,'height':900})
   async def route(r):
    try:await asyncio.to_thread(public_url,r.request.url)
    except (ValueError,OSError):await r.abort();return
    await r.continue_()
   await page.route('**/*',route)
   await page.goto(args.url,wait_until='domcontentloaded',timeout=45000)
   await page.wait_for_timeout(1500)
   text=await page.locator('body').inner_text(timeout=5000)
   await page.screenshot(path=str(out.with_suffix('.png')),full_page=False)
   result={'url':page.url,'title':await page.title(),'text':text[:30000],'screenshot':str(out.with_suffix('.png'))}
   out.with_suffix('.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
   print(json.dumps(result,ensure_ascii=False))
  finally:await browser.close()

if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('url');parser.add_argument('--out',default='web/page');asyncio.run(main(parser.parse_args()))

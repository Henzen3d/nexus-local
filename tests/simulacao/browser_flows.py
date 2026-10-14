"""Exploração Playwright real; screenshots + geometria, sem fingir LLM real."""
import asyncio,json,sys,time
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'melhorias/simulacao-2026-10-14/evidencias'
CREDS=json.loads((ROOT/'.cache/simulacao/credentials.json').read_text())['qa-admin']
async def snap(page,name):
 await page.screenshot(path=str(OUT/f'{name}.png'),full_page=True)
 data=await page.evaluate('''() => ({text:document.body.innerText,scrollWidth:document.documentElement.scrollWidth,width:innerWidth,buttons:[...document.querySelectorAll('button,input,textarea,[role="button"]')].filter(e=>e.getBoundingClientRect().width>0).map(e=>{let r=e.getBoundingClientRect();let s=getComputedStyle(e);return {tag:e.tagName,text:e.innerText,aria:e.getAttribute('aria-label'),title:e.getAttribute('title'),placeholder:e.getAttribute('placeholder'),w:r.width,h:r.height,color:s.color,bg:s.backgroundColor,font:s.fontFamily}})})''')
 (OUT/f'{name}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2));print(name,data['text'][:5000],flush=True)
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/tmp/chromium',args=['--no-sandbox','--no-zygote','--disable-dev-shm-usage'])
  page=await browser.new_page(viewport={'width':1440,'height':900},locale='pt-BR');page.set_default_timeout(6000)
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  await page.goto('http://localhost:5173');await page.locator('#username').fill(CREDS['username']);await page.locator('#password').fill(CREDS['password']);await page.get_by_role('button',name='Entrar',exact=True).click();await page.wait_for_timeout(2000)
  await snap(page,'02-primeiro-acesso-1440')
  await page.set_viewport_size({'width':390,'height':844});await snap(page,'02-primeiro-acesso-390')
  await page.get_by_role('button',name='Entendi',exact=True).click()
  await page.set_viewport_size({'width':1440,'height':900})
  await page.locator('textarea').fill('Olá! Como começo a usar? Ação, 日本語, 👩🏽‍💻')
  await page.locator('textarea').press('Enter');await page.wait_for_timeout(4000)
  await snap(page,'03-sem-chave-1440')
  await page.set_viewport_size({'width':390,'height':844});await snap(page,'03-sem-chave-390')
  (OUT/'browser-errors.json').write_text(json.dumps(errors))
  await browser.close()
if __name__ == '__main__': asyncio.run(main())

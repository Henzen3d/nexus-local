import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright
from browser_flows import snap,ROOT,OUT,CREDS
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/tmp/chromium',args=['--no-sandbox','--no-zygote','--disable-dev-shm-usage'])
  page=await browser.new_page(viewport={'width':1440,'height':900},locale='pt-BR');page.set_default_timeout(5000)
  await page.goto('http://localhost:5173');await page.locator('#username').fill(CREDS['username']);await page.locator('#password').fill(CREDS['password']);await page.get_by_role('button',name='Entrar',exact=True).click();await page.wait_for_timeout(1000)
  if await page.get_by_role('button',name='Entendi',exact=True).count():await page.get_by_role('button',name='Entendi',exact=True).click()
  await snap(page,'04-configurado-1440')
  await page.locator('textarea').fill('Teste diário: ação, 日本語, 👩🏽‍💻 e <script>alert(1)</script>');await page.locator('textarea').press('Enter');await page.wait_for_timeout(2500)
  await snap(page,'05-resposta-1440')
  await page.get_by_role('button',name='QA qa-a',exact=True).click();await snap(page,'06-modelos-1440')
  await page.get_by_role('option').filter(has_text='QA qa-b').first.click()
  await page.locator('textarea').fill('Continue depois da troca de modelo');await page.locator('textarea').press('Enter');await page.wait_for_timeout(1800)
  await snap(page,'07-troca-modelo-1440')
  await page.get_by_role('button',name='Buscar conversas',exact=True).click();await page.wait_for_timeout(400);await snap(page,'08-busca-1440')
  print('INPUTS',await page.locator('input').evaluate_all('(xs)=>xs.map(x=>({placeholder:x.placeholder,type:x.type}))'))
  await browser.close()
if __name__=='__main__':asyncio.run(main())

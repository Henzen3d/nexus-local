import asyncio,json
from playwright.async_api import async_playwright
from browser_flows import snap,ROOT,OUT,CREDS
async def main():
 async with async_playwright() as p:
  for width in [1440,390]:
   browser=await p.chromium.launch(executable_path='/tmp/chromium',args=['--no-sandbox','--no-zygote','--disable-dev-shm-usage'])
   page=await browser.new_page(viewport={'width':width,'height':900 if width==1440 else 844},locale='pt-BR');page.set_default_timeout(4000)
   session=json.loads((ROOT/'.cache/simulacao/session.json').read_text())
   await page.add_init_script('localStorage.setItem("nexuslocal_token",'+json.dumps(session['token'])+');localStorage.setItem("nexuslocal_user",'+json.dumps(json.dumps(session['user']))+');')
   await page.goto('http://localhost:5173');await page.wait_for_timeout(800)
   if await page.get_by_role('button',name='Entendi',exact=True).count():await page.get_by_role('button',name='Entendi',exact=True).click()
   async def capture(name):
    await snap(page,f'{name}-{width}')
    await page.add_script_tag(path=str(ROOT/'.cache/simulacao/node_modules/axe-core/axe.min.js'))
    violations=await page.evaluate('async()=> (await axe.run(document,{runOnly:{type:"tag",values:["wcag2a","wcag2aa","wcag21aa"]}})).violations')
    (OUT/f'axe-{name}-{width}.json').write_text(json.dumps(violations,ensure_ascii=False,indent=2))
   await capture('09-home')
   # Mobile inicia com sidebar fechada; abrir por nome acessível se necessário.
   async def nav(name):
    btn=page.get_by_role('button',name=name,exact=True).first
    if not await btn.is_visible():
     print('OPEN SIDEBAR',await page.get_by_role('button').evaluate_all('(xs)=>xs.map(x=>({text:x.innerText,aria:x.getAttribute("aria-label")}))'))
     opener=page.get_by_role('button',name='Abrir menu lateral',exact=True)
     await opener.click()
    await btn.click();await page.wait_for_timeout(500)
   try:
    await nav('Projetos');await capture('10-projetos')
    await page.get_by_text('QA RAG Unicode 日本語',exact=True).first.click();await page.wait_for_timeout(600);await capture('11-projeto-detalhe')
   except Exception as e:print('PROJECT ERROR',str(e)[:500])
   try:
    await nav('Nova conversa');await page.locator('textarea').fill('QA interface mobile '+str(width));await page.locator('textarea').press('Enter');await page.wait_for_timeout(1600);await capture('12-chat')
    await page.get_by_role('button',name='Ações e ferramentas',exact=True).click();await capture('13-ferramentas')
    print('TOOLS',await page.locator('body').inner_text())
    await page.keyboard.press('Escape')
   except Exception as e:print('CHAT ERROR',str(e)[:500])
   try:
    await nav('Biblioteca');await capture('14-biblioteca')
   except Exception as e:print('LIB ERROR',str(e)[:500])
   (OUT/f'panel-final-{width}.txt').write_text(await page.locator('body').inner_text())
   await browser.close()
if __name__=='__main__':asyncio.run(main())

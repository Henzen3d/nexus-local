import asyncio,json,io,time
from playwright.async_api import async_playwright
from PIL import Image
from browser_flows import snap,ROOT,OUT
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/tmp/chromium',args=['--no-sandbox','--no-zygote','--disable-dev-shm-usage'])
  page=await browser.new_page(viewport={'width':390,'height':844},locale='pt-BR');page.set_default_timeout(5000)
  session=json.loads((ROOT/'.cache/simulacao/session.json').read_text())
  await page.add_init_script('localStorage.setItem("nexuslocal_memory_onboarding_seen","true");localStorage.setItem("nexuslocal_token",'+json.dumps(session['token'])+');localStorage.setItem("nexuslocal_user",'+json.dumps(json.dumps(session['user']))+');')
  await page.goto('http://localhost:5173');await page.wait_for_timeout(800)
  if await page.get_by_role('button',name='Entendi',exact=True).count():await page.get_by_role('button',name='Entendi',exact=True).click()
  await page.locator('textarea').fill('QA envio por toque mobile');await page.get_by_role('button',name='Enviar',exact=True).click();await page.wait_for_timeout(1300);await snap(page,'15-mobile-enviado-390')
  png=io.BytesIO();Image.new('RGB',(50,50),'coral').save(png,format='PNG')
  await page.locator('input[type=file]').set_input_files([{'name':'nota-ação.txt','mimeType':'text/plain','buffer':'Documento de teste Unicode 日本語'.encode()},{'name':'foto.png','mimeType':'image/png','buffer':png.getvalue()}]);await page.wait_for_timeout(700);await snap(page,'16-anexos-390')
  await page.locator('textarea').fill('Compare nota e foto');await page.get_by_role('button',name='Enviar',exact=True).click();await page.wait_for_timeout(1300);await snap(page,'17-anexos-resposta-390')
  await page.locator('input[type=file]').set_input_files({'name':'corrompido.pdf','mimeType':'application/pdf','buffer':b'%PDF-1.7 invalid'});await page.wait_for_timeout(400);await snap(page,'18-upload-erro-390')
  await page.set_viewport_size({'width':1440,'height':900})
  await page.locator('.model-trigger').click();await page.get_by_role('button',name='Mais modelos',exact=False).click();await page.get_by_placeholder('Buscar modelos…').fill('qa-slow');await page.get_by_role('option').filter(has_text='qa-slow').first.click()
  await page.locator('textarea').fill('QA STOP via botão');await page.get_by_role('button',name='Enviar',exact=True).click();await page.wait_for_timeout(1600);await snap(page,'19-stream-lento-1440')
  await page.get_by_role('button',name='Parar',exact=True).click();await snap(page,'20-stop-1440')
  # O fake leva ~15s; esperar sem reenvio e verificar persistência real após reload.
  await page.wait_for_timeout(15000);await page.reload();await page.wait_for_timeout(600)
  if await page.get_by_role('button',name='Abrir menu lateral',exact=True).count():await page.get_by_role('button',name='Abrir menu lateral',exact=True).click()
  await page.get_by_role('button',name='QA envio por toque mobile',exact=True).first.click();await page.wait_for_timeout(500);await snap(page,'21-stop-reload-1440')
  # Tema escuro via controle existente (não altera código).
  theme=page.locator('[data-tooltip]').filter(has_text='__none__')
  print('THEME BUTTONS',await page.locator('button[data-tooltip]').evaluate_all('(xs)=>xs.map(x=>({tooltip:x.dataset.tooltip,aria:x.getAttribute("aria-label")}))'))
  # Offline: conexão caiu + tentativa de envio. Estado observado por screenshot.
  await page.context.set_offline(True);await page.wait_for_timeout(1000);await page.locator('textarea').fill('QA offline preservar rascunho');await page.get_by_role('button',name='Enviar',exact=True).click();await snap(page,'22-offline-1440');await page.context.set_offline(False)
  await browser.close()
if __name__=='__main__':asyncio.run(main())

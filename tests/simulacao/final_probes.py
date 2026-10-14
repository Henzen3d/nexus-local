"""Completa evidências de contexto longo, concorrência e screenshots Fusion."""
import asyncio,json,sqlite3,uuid,time,os
from pathlib import Path
import httpx
from playwright.async_api import async_playwright
from api_flows import ROOT,OUT,turn
import api_flows as qa
from browser_flows import snap
qa.results=json.loads((OUT/'api-results.json').read_text())
async def main():
 session=json.loads((ROOT/'.cache/simulacao/session.json').read_text());token=session['token']
 if not os.getenv('UI_ONLY'):
  db=sqlite3.connect(ROOT/'.cache/simulacao/qa.db');db.execute("DELETE FROM model_quota_status WHERE model_id LIKE '%qa-%'")
  cid=str(uuid.uuid4());db.execute('insert into conversations(id,user_id,title,model_id,provider_id) values(?,?,?,?,?)',(cid,session['user']['id'],'QA conversa longa 160 mensagens','ollama/qa-a','ollama'))
  for i in range(160):
   db.execute('insert into messages(id,conversation_id,role,content,created_at) values(?,?,?,?,?)',(str(uuid.uuid4()),cid,'user' if i%2==0 else 'assistant',f'MARCADOR_{i:03} '+('contexto '*150),f'2026-10-13 {i//60:02}:{i%60:02}:00'))
  db.commit()
  base={'provider_id':'ollama','model_id':'ollama/qa-a','use_memory':False,'bypass_cache':True}
  await turn(token,'historico_160_turnos',{**base,'conversation_id':cid,'message':'QA após histórico longo, preserve o último turno'})
  await asyncio.gather(*(turn(token,'concorrencia_'+str(i),{**base,'message':'QA concorrência '+str(i)}) for i in range(6)))
  qa.record('sqlite_after_concurrency',integrity=db.execute('pragma integrity_check').fetchone());db.close()
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/tmp/chromium',args=['--no-sandbox','--no-zygote','--disable-dev-shm-usage'])
  page=await browser.new_page(viewport={'width':1440,'height':900},locale='pt-BR');page.set_default_timeout(5000)
  await page.add_init_script('localStorage.setItem("nexuslocal_memory_onboarding_seen","true");localStorage.setItem("nexuslocal_token",'+json.dumps(token)+');localStorage.setItem("nexuslocal_user",'+json.dumps(json.dumps(session['user']))+');')
  await page.goto('http://localhost:5173');await page.wait_for_timeout(700)
  if await page.get_by_role('button',name='Entendi',exact=True).count():await page.get_by_role('button',name='Entendi',exact=True).click()
  await page.get_by_role('button',name='Ações e ferramentas',exact=True).click();await page.get_by_role('menuitemcheckbox').filter(has_text='Modo Fusion').click();await page.keyboard.press('Escape')
  await page.locator('textarea').fill('QA Fusion pela interface');await page.get_by_role('button',name='Enviar',exact=True).click();await page.wait_for_timeout(120);await snap(page,'23-fusion-loading-1440');await page.wait_for_timeout(1200);await snap(page,'24-fusion-done-1440');await page.set_viewport_size({'width':390,'height':844});await snap(page,'24-fusion-done-390')
  await page.set_viewport_size({'width':1440,'height':900})
  controls=await page.locator('button').evaluate_all('(xs)=>xs.map(x=>({title:x.title,tooltip:x.dataset.tooltip,cls:x.className}))');(OUT/'theme-controls.json').write_text(json.dumps(controls,ensure_ascii=False,indent=2))
  btn=page.locator('button').filter(has=page.locator('svg.lucide-moon'))
  if await btn.count():
   await btn.first.click();await snap(page,'25-dark-1440');await page.set_viewport_size({'width':390,'height':844});await snap(page,'25-dark-390')
  await browser.close()
asyncio.run(main())

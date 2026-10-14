"""Captura real, sem mock do front; usa DB descartável já iniciado."""
import asyncio, json, os
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'melhorias/simulacao-2026-10-14/evidencias'
async def main():
 async with async_playwright() as p:
  for width in [1440,390]:
   browser=await p.chromium.launch(executable_path='/tmp/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage','--no-zygote'])
   page=await browser.new_page(viewport={'width':width,'height':900 if width==1440 else 844},locale='pt-BR')
   await page.goto('http://localhost:5173'); await page.wait_for_timeout(2500)
   await page.screenshot(path=str(OUT/f'01-login-{width}.png'),full_page=True)
   print(width, (await page.locator('body').inner_text())[:3000])
   await page.close()
  await browser.close()
asyncio.run(main())

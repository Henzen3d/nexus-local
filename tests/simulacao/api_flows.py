"""Integração contra backend real + provedor HTTP sintético; DB descartável qa.db."""
import asyncio,json,time,io,sqlite3
from pathlib import Path
import httpx,websockets
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'melhorias/simulacao-2026-10-14/evidencias'
results=[]
def record(name,**data):
 results.append({'test':name,**data});(OUT/'api-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(name,str(data)[:500],flush=True)
async def turn(token,name,payload,duplicate=False,disconnect=False):
 start=time.monotonic();events=[];ttft=None
 async with websockets.connect('ws://localhost:8000/ws/chat?token='+token,max_size=4_000_000) as ws:
  await ws.recv();await ws.send(json.dumps(payload))
  if duplicate:await ws.send(json.dumps(payload))
  ends=0
  try:
   while True:
    ev=json.loads(await asyncio.wait_for(ws.recv(),20));events.append(ev)
    if ev.get('type')=='token' and ttft is None:ttft=round((time.monotonic()-start)*1000,1)
    if disconnect and ev.get('type')=='token':break
    if ev.get('type') in ('error','stream_end'):
     ends+=1
     if not duplicate or ends>=2:break
  except Exception as e:events.append({'transport_exception':type(e).__name__,'detail':str(e)[:200]})
 record(name,elapsed_ms=round((time.monotonic()-start)*1000,1),ttft_ms=ttft,events=events)
 return next((e.get('conversation_id') or e.get('id') for e in events if e.get('type')=='conversation_created'),None)
async def main():
 creds=json.loads((ROOT/'.cache/simulacao/credentials.json').read_text())
 async with httpx.AsyncClient(base_url='http://localhost:8000',timeout=35) as c:
  async def req(name,method,url,**kw):
   t=time.monotonic();r=await c.request(method,url,**kw)
   try:body=r.json()
   except:body=r.text[:300]
   record(name,status=r.status_code,ms=round((time.monotonic()-t)*1000,1),body=body);return body
  await req('cadastro_fechado','POST','/api/auth/register',json={'username':'novato','password':'qa-novato'})
  a=(await c.post('/api/auth/login',json={k:creds['qa-admin'][k] for k in ['username','password']})).json();token=a['token'];c.headers['Authorization']='Bearer '+token
  b=(await c.post('/api/auth/login',json={k:creds['qa-outro'][k] for k in ['username','password']})).json()['token']
  base={'message':'Olá QA','provider_id':'ollama','model_id':'ollama/qa-a','use_memory':False,'bypass_cache':True}
  await turn(token,'vazio',{**base,'message':'  '})
  await turn(token,'unicode',{**base,'message':'Ação 日本語 👩🏽‍💻 <script>alert(1)</script>'})
  await turn(token,'texto_gigante_100k',{**base,'message':'測'*100_000})
  await turn(token,'duplicado_sem_request_id',{**base,'message':'QA duplo envio'},duplicate=True)
  await turn(token,'aba_fechada',{**base,'model_id':'ollama/qa-slow','message':'QA fechar aba'},disconnect=True)
  for raw in ['[]','{"message":42}','null']:
   async with websockets.connect('ws://localhost:8000/ws/chat?token='+token) as ws:
    await ws.recv();await ws.send(raw)
    try:out=await asyncio.wait_for(ws.recv(),3)
    except Exception as e:out=type(e).__name__+': '+str(e)
    record('ws_shape_'+raw,result=out)
  p=await req('projeto_criado','POST','/api/projects',json={'name':'QA RAG Unicode 日本語','instructions':'REGRA_PROJETO_QA: responda citando o documento.'});pid=p['id']
  for filename,data,mime in [('manual.md',('# Manual\n\n'+('\n\n'.join(f'## Seção {i}\nDado de teste {i}. '+('contexto irrelevante '*100) for i in range(20)))+'\n\n## Política final\nO código secreto de devolução é AZUL-739.').encode(),'text/markdown'),('regras.txt','A garantia é de 37 dias. Fonte complementar QA.'.encode(),'text/plain'),('terceiro.txt','Horário de suporte: 9h até 17h.'.encode(),'text/plain'),('corrompido.pdf',b'%PDF-1.7 lixo truncado','application/pdf'),('programa.exe',b'MZQA fake executable','application/octet-stream'),('vazio.txt',b'','text/plain'),('grande.txt',b'x'*(26*1024*1024),'text/plain')]:
   await req('upload_project_'+filename,'POST',f'/api/projects/{pid}/files',files={'file':(filename,data,mime)})
  await asyncio.sleep(1)
  await req('arquivos_indexados','GET',f'/api/projects/{pid}/files')
  await turn(token,'pergunta_rag',{**base,'message':'Qual o código secreto de devolução?','project_id':pid,'project_context_debug':True})
  await req('idor_project','GET',f'/api/projects/{pid}',headers={'Authorization':'Bearer '+b})
  png=io.BytesIO();Image.new('RGB',(40,40),'red').save(png,format='PNG')
  att=await req('upload_imagem','POST','/api/attachments/upload',data={'model_id':'ollama/qa-a'},files={'file':('imagem.png',png.getvalue(),'image/png')})
  await req('upload_anexo_vazio','POST','/api/attachments/upload',data={'model_id':'ollama/qa-a'},files={'file':('vazio.txt',b'','text/plain')})
  await req('upload_pdf_corrompido','POST','/api/attachments/upload',data={'model_id':'ollama/qa-a'},files={'file':('corrupt.pdf',b'%PDF-1.7 lixo','application/pdf')})
  await req('fusion_config','POST','/api/fusion/config',json={'enabled':True,'grounding_enabled':False,'judge_provider_id':'ollama','judge_model_id':'ollama/qa-judge','models':[{'provider_id':'ollama','model_id':'ollama/'+x} for x in ['qa-a','qa-b','qa-c']]})
  await turn(token,'fusion_tres_modelos',{**base,'fusion':True,'message':'QA fusion com projeto','project_id':pid})
  if 'id' in att:await turn(token,'fusion_imagem',{**base,'fusion':True,'attachment_ids':[att['id']],'message':'Descreva a imagem QA'})
  await req('fusion_config_uma_falha','POST','/api/fusion/config',json={'models':[{'provider_id':'ollama','model_id':'ollama/'+x} for x in ['qa-a','qa-b','qa-bad']]})
  await turn(token,'fusion_uma_falha',{**base,'fusion':True,'message':'QA uma falha isolada'})
  await req('cors_hostil','OPTIONS','/api/projects',headers={'Origin':'https://evil.example','Access-Control-Request-Method':'GET'})
  await req('busca_conteudo_nao_titulo','GET','/api/conversations',params={'search':'Conteúdo determinístico'})
  await req('busca_unicode_titulo','GET','/api/conversations',params={'search':'日本語'})
  (ROOT/'.cache/simulacao/project.json').write_text(json.dumps({'id':pid}))
  schema=sqlite3.connect(ROOT/'.cache/simulacao/qa.db');record('sqlite_integrity',result=schema.execute('pragma integrity_check').fetchall());record('rag_embeddings',rows=schema.execute('select pf.filename,pf.index_status,count(fc.id),sum(fc.embedding is not null) from project_files pf left join file_chunks fc on fc.project_file_id=pf.id group by pf.id').fetchall())
if __name__=='__main__':asyncio.run(main())

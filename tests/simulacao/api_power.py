import asyncio,json,sqlite3
import httpx
import api_flows as qa
from api_flows import ROOT,OUT,turn,record
qa.results=json.loads((OUT/'api-results.json').read_text())
async def main():
 cdb=sqlite3.connect(ROOT/'.cache/simulacao/qa.db')
 for pid,model in [('qa-provider-b','qa-b'),('qa-provider-c','qa-c')]:
  cdb.execute('INSERT OR REPLACE INTO providers(id,name,base_url,enabled,is_free,is_local) VALUES(?,?,?,1,0,1)',(pid,pid,'http://127.0.0.1:8010/v1'))
  cdb.execute('INSERT OR REPLACE INTO models(id,provider_id,name,display_name,context_length,enabled,confirmed_free,supports_vision) VALUES(?,?,?,?,8192,1,1,1)',(pid+'/'+model,pid,model,'QA '+model+' sintético'))
  cdb.execute('INSERT OR REPLACE INTO user_api_keys(user_id,provider_id,api_key) SELECT id,?,? FROM users',(pid,'qa-dummy-local-only'))
 cdb.commit()
 creds=json.loads((ROOT/'.cache/simulacao/credentials.json').read_text())['qa-admin'];pid=json.loads((ROOT/'.cache/simulacao/project.json').read_text())['id']
 async with httpx.AsyncClient(base_url='http://localhost:8000',timeout=30) as c:
  token=(await c.post('/api/auth/login',json={k:creds[k] for k in ['username','password']})).json()['token'];c.headers['Authorization']='Bearer '+token
  models=[{'provider_id':'ollama','model_id':'ollama/qa-a'},{'provider_id':'qa-provider-b','model_id':'qa-provider-b/qa-b'},{'provider_id':'qa-provider-c','model_id':'qa-provider-c/qa-c'}]
  r=await c.post('/api/fusion/config',json={'enabled':True,'grounding_enabled':False,'judge_provider_id':'ollama','judge_model_id':'ollama/qa-judge','models':models});record('fusion_tres_provedores_config',status=r.status_code)
  base={'message':'QA Fusion: qual código de devolução nos arquivos?','provider_id':'ollama','model_id':'ollama/qa-a','use_memory':False,'bypass_cache':True,'project_id':pid,'fusion':True,'project_context_debug':True}
  await turn(token,'fusion_tres_provedores',base)
  cdb.execute("UPDATE models SET name='qa-bad' WHERE id='qa-provider-c/qa-c'");cdb.commit()
  await turn(token,'fusion_falha_401_um_proposer',{**base,'message':'Explique QA com uma falha','project_id':None})
  cdb.execute("UPDATE models SET name='qa-c',enabled=1 WHERE id='qa-provider-c/qa-c'");cdb.commit()
  png=qa.io.BytesIO();qa.Image.new('RGB',(40,40),'red').save(png,format='PNG')
  att=(await c.post('/api/attachments/upload',data={'model_id':'ollama/qa-a'},files={'file':('qa.png',png.getvalue(),'image/png')})).json()
  await turn(token,'fusion_multimodal_tres_provedores',{**base,'message':'Descreva imagem','project_id':None,'attachment_ids':[att['id']]})
  await turn(token,'rag_fallback_explicito',{**base,'message':'Nos arquivos do projeto, qual é o código secreto de devolução?','fusion':False})
  await turn(token,'web_search_rede_bloqueada',{**base,'message':'Pesquise na web as novidades do FastAPI','fusion':False,'web_search':True,'project_id':None})
  await turn(token,'modelo_offline',{**base,'message':'QA offline','fusion':False,'project_id':None,'model_id':'nao-existe'})
  await turn(token,'rate_limit_fixture',{**base,'message':'QA429','fusion':False,'project_id':None})
  record('final_integrity',result=cdb.execute('pragma integrity_check').fetchall());cdb.close()
asyncio.run(main())

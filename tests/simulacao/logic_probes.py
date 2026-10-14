"""Provas determinísticas em OUTRO SQLite temporário; vetores fake declarados."""
import asyncio,json,os,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
OUT=ROOT/'melhorias/simulacao-2026-10-14/evidencias'
tmp=tempfile.TemporaryDirectory(prefix='nexus-qa-logic-');os.environ['DB_PATH']=tmp.name+'/isolated.db';os.environ['JWT_SECRET']='qa-only-logic-secret-0123456789-0123456789'
from backend.database import init_db,get_db
from backend.cache.manager import CacheManager
from backend.projects.embedder import embedding_to_blob
from backend.orchestration.handle_attachments import trim_history_to_budget,estimate_message_tokens
from backend.projects.context_builder import compute_safe_input_tokens,fit_chunks_to_token_budget
from unittest.mock import patch
async def main():
 await init_db();cm=CacheManager();res={}
 await cm.update_settings({'exact_enabled':False,'semantic_enabled':False})
 db=await get_db();await db.execute("UPDATE cache_settings SET value='true' WHERE key='semantic_enabled'");await db.commit()
 blob=embedding_to_blob([1.,0.,0.]);prompt='Qual o prazo?';key=cm._semantic_prompt_key(prompt,'nomem')
 await cm._set_semantic('test-model',key,blob,'Projeto A: 37 dias',12,user_id='qa-A')
 histB=[{'role':'system','content':'Projeto B: prazo 90 dias. Documento revisado.'},{'role':'user','content':prompt}]
 hit=await cm.get('test-model',histB,context_fingerprint='nomem',user_id='qa-A');res['cross_project_same_user']={'response':hit.response if hit else None,'similarity':hit.similarity if hit else None,'expected':'MISS (sistema/projeto diferente)','synthetic_embeddings':True}
 with patch('backend.cache.manager._embed_text',return_value=blob):
  other=await cm.get('test-model',histB,context_fingerprint='nomem',user_id='qa-B');res['cross_user']={'hit':bool(other),'expected':'MISS'}
  opposite=await cm.get('test-model',[{'role':'user','content':'Qual NÃO é o prazo?'}],context_fingerprint='nomem',user_id='qa-A');res['forced_vector_collision']={'hit':bool(opposite),'note':'Vetor artificial idêntico; NÃO mede taxa real de falso positivo do MiniLM.'}
 await cm._set_exact('test-model',[{'role':'user','content':'TTL'}],'antiga',2,user_id='qa-A')
 await db.execute("UPDATE cache_exact SET created_at=datetime('now','-71 hours')");await db.commit()
 ttl=await cm._get_exact('test-model',[{'role':'user','content':'TTL'}],72,user_id='qa-A');res['ttl_71_of_72_hours']={'hit':bool(ttl),'expected':'HIT','created_at':(await (await db.execute('select created_at from cache_exact')).fetchone())[0]}
 await db.execute("UPDATE cache_exact SET created_at=datetime('now','-200 hours')");await db.commit()
 await cm._set_exact('test-model',[{'role':'user','content':'TTL'}],'nova',2,user_id='qa-A');res['expired_refresh']={'rows':await (await db.execute('select response,created_at from cache_exact')).fetchall(),'expected':'resposta nova e created_at renovado'}
 hist=[{'role':'user','content':'測'*100000}];kept,removed=trim_history_to_budget(hist,6144,1000);res['oversize']={'chars':len(kept[0]['content']),'estimated_tokens':sum(estimate_message_tokens(x) for x in kept),'budget':6144,'removed':removed}
 res['tiny_context']={'advertised':512,'safe_input':compute_safe_input_tokens(512)}
 await db.close();(OUT/'logic-results.json').write_text(json.dumps(res,indent=2,ensure_ascii=False));print(json.dumps(res,indent=2,ensure_ascii=False))
asyncio.run(main());tmp.cleanup()

"""Configura SOMENTE fixtures locais no qa.db; opção --session salva auth em .cache.
Após seed_qa.py. Credenciais fictícias não são chaves de provedores reais.
"""
import argparse,json,sqlite3
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--session',action='store_true');a=p.parse_args()
db=ROOT/'.cache/simulacao/qa.db'
assert db.exists() and db.name=='qa.db'
c=sqlite3.connect(db)
c.execute('UPDATE providers SET enabled=0')
c.execute("UPDATE providers SET enabled=1,base_url='http://127.0.0.1:8010/v1',is_local=1 WHERE id='ollama'")
c.execute("UPDATE models SET enabled=0 WHERE provider_id='ollama'")
for name in ['qa-a','qa-b','qa-c','qa-judge','qa-slow','qa-bad']:
 c.execute('INSERT OR REPLACE INTO models(id,provider_id,name,display_name,context_length,enabled,confirmed_free,supports_vision) VALUES(?,?,?,?,8192,1,1,1)',('ollama/'+name,'ollama',name,'QA '+name))
c.execute("INSERT OR REPLACE INTO user_api_keys(user_id,provider_id,api_key) SELECT id,'ollama','qa-dummy-local-only' FROM users")
c.execute("DELETE FROM model_quota_status WHERE model_id LIKE '%qa-%'")
c.commit();c.close()
if a.session:
 creds=json.loads((ROOT/'.cache/simulacao/credentials.json').read_text())['qa-admin']
 r=httpx.post('http://localhost:8000/api/auth/login',json={k:creds[k] for k in ['username','password']});r.raise_for_status()
 (ROOT/'.cache/simulacao/session.json').write_text(json.dumps(r.json()))
print('Fixture local configurada. Sem alteração de produto; auth somente em .cache.')

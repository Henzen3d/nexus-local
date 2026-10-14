"""Dados sintéticos, exclusivamente no SQLite isolado da simulação."""
import json, secrets, sqlite3, uuid
from pathlib import Path
from passlib.context import CryptContext
ROOT=Path(__file__).resolve().parents[2]; db=ROOT/'.cache/simulacao/qa.db'
assert db.exists() and db.name=='qa.db'
c=sqlite3.connect(db); pwd=CryptContext(schemes=['bcrypt'])
cred={}
for name,role in [('qa-admin','admin'),('qa-outro','user')]:
 password=secrets.token_urlsafe(18); uid=str(uuid.uuid4())
 old=c.execute('SELECT id FROM users WHERE username=?',(name,)).fetchone()
 if old: uid=old[0]; c.execute('UPDATE users SET password_hash=? WHERE id=?',(pwd.hash(password),uid))
 else: c.execute('INSERT INTO users(id,username,password_hash,role) VALUES(?,?,?,?)',(uid,name,pwd.hash(password),role))
 cred[name]={'username':name,'password':password,'id':uid}
c.commit(); (ROOT/'.cache/simulacao/credentials.json').write_text(json.dumps(cred));print('2 usuários QA criados; credenciais somente em .cache ignorado.')

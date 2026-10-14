"""Servidor OpenAI compatível determinístico. NÃO mede qualidade/latência de LLM real."""
import asyncio,json,time
from pathlib import Path
from fastapi import FastAPI,Request
from fastapi.responses import StreamingResponse,JSONResponse
app=FastAPI(); OUT=Path(__file__).resolve().parents[2]/'melhorias/simulacao-2026-10-14/evidencias/provider.jsonl'
@app.get('/v1/models')
async def models(): return {'data':[{'id':x} for x in ['qa-a','qa-b','qa-c','qa-judge','qa-slow','qa-bad']]}
@app.post('/v1/chat/completions')
async def chat(r:Request):
 body=await r.json(); model=body.get('model','');started=time.monotonic();rid=str(time.time_ns())
 def log(event,**kw):
  with OUT.open('a') as f:f.write(json.dumps({'id':rid,'event':event,'model':model,'elapsed_s':round(time.monotonic()-started,3),**kw},ensure_ascii=False)+'\n')
 log('request',messages=body.get('messages',[]))
 if model=='qa-bad':log('401');return JSONResponse({'error':{'message':'Invalid API key (fixture QA)','code':'invalid_api_key'}},401)
 messages=body.get('messages',[]);last=str(messages[-1].get('content','')) if messages else ''
 if 'QA429' in last: return JSONResponse({'error':{'message':'rate limit QA'}},429,headers={'Retry-After':'2'})
 if 'NENHUMA' in last:answer='NENHUMA'
 elif model=='qa-judge':answer='Síntese simulada de QA. Esta saída valida o transporte, não a qualidade do Judge.'
 else:answer=f'Resposta simulada {model}. Unicode: ação, 日本語, 👩🏽‍💻.\n\n'+('Passo de teste. '*60 if model=='qa-slow' else 'Conteúdo determinístico para testes de interface.')
 async def stream():
  try:
   await asyncio.sleep(.12 if model!='qa-slow' else 1)
   for i in range(0,len(answer),12):
    yield 'data: '+json.dumps({'choices':[{'delta':{'content':answer[i:i+12]}}]})+'\n\n'
    await asyncio.sleep(.025 if model!='qa-slow' else .18)
   yield 'data: [DONE]\n\n';log('complete')
  except asyncio.CancelledError:log('cancelled');raise
 return StreamingResponse(stream(),media_type='text/event-stream')

"""Same-origin live CRM API. Demo roles are explicit; production OIDC fails closed."""
import os,json,time,secrets,hashlib,io
from pathlib import Path
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from fastapi import FastAPI,Request,HTTPException,UploadFile,File,Form
from fastapi.responses import HTMLResponse,JSONResponse,RedirectResponse,StreamingResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel,Field,ConfigDict
from .engine import Engine,DEMO_PROFILES,actor_key,sanitize,CITIES
from .data import AS_OF

def truth(name,default='false'):return os.getenv(name,default).lower()=='true'
class Filters(BaseModel):
 model_config=ConfigDict(extra='forbid')
 zone:str='All';city:str='All';tier:str='All'
class ChatBody(BaseModel):
 model_config=ConfigDict(extra='forbid')
 question:str=Field(min_length=1,max_length=1800);filters:Filters=Field(default_factory=Filters)
class DemoBody(BaseModel):
 model_config=ConfigDict(extra='forbid')
 profile:str
class CaseBody(BaseModel):
 model_config=ConfigDict(extra='forbid')
 filters:Filters=Field(default_factory=Filters);summary:str=Field(default='Administrative evidence review',max_length=300)
class DecisionBody(BaseModel):
 model_config=ConfigDict(extra='forbid')
 decision:str
class PIIBody(BaseModel):
 model_config=ConfigDict(extra='forbid')
 purpose:str

def map_identity(claims,issuer,directory):
 # Identity claims must already have been validated by Authlib's OIDC callback.
 if claims.get('iss')!=issuer or not claims.get('sub'):raise PermissionError('Unverified identity context')
 key=issuer+'|'+claims['sub'];entry=directory.get(key)
 if not entry:raise PermissionError('Subject is not provisioned in the enterprise access map')
 for k in ['tenant','roles','zones','cities','purposes']:
  if not entry.get(k):raise PermissionError('Incomplete directory mapping')
 # Ignore privilege-like userinfo claims; all attributes come from the trusted mapping.
 return {'sub':key,**{k:entry[k] for k in ['tenant','roles','zones','cities','purposes']}}

def create_app(engine=None,demo=None):
 demo=truth('TELECOM_DEMO','true') if demo is None else demo;public=os.getenv('PUBLIC_BASE_URL','http://127.0.0.1:8000').rstrip('/');issuer=os.getenv('OIDC_ISSUER','').rstrip('/');client_id=os.getenv('OIDC_CLIENT_ID','');client_secret=os.getenv('OIDC_CLIENT_SECRET','');secret=os.getenv('SESSION_SECRET','');directory=json.loads(os.getenv('ACCESS_MAP_JSON','{}'));root=os.getenv('TELECOM_DATA_DIR','runtime');pii_key=os.getenv('TELECOM_PII_KEY')
 if not demo:
  if not issuer.startswith('https://') or not public.startswith('https://') or not client_id or not client_secret or len(secret)<32 or not pii_key or not directory:raise RuntimeError('Production requires HTTPS OIDC issuer/public URL, client ID/secret, session signing secret, persistent PII key and a nonempty access map')
 secret=secret or secrets.token_urlsafe(48);oauth=None
 if not demo:
  from authlib.integrations.starlette_client import OAuth
  oauth=OAuth();oauth.register(name='enterprise',client_id=client_id,client_secret=client_secret,server_metadata_url=issuer+'/.well-known/openid-configuration',client_kwargs={'scope':'openid profile email','code_challenge_method':'S256'})
 @asynccontextmanager
 async def lifespan(app):
  app.state.engine=engine or Engine(root,smoke=truth('TELECOM_SMOKE'),pii_key=pii_key,embedding_backend=os.getenv('EMBEDDING_BACKEND','sparse'),llm_backend=os.getenv('LLM_BACKEND','extractive'),demo=demo)
  yield
 app=FastAPI(title='TelecomIQ POC to Production 2',version='0.1.0',lifespan=lifespan,docs_url='/api/docs' if demo else None,redoc_url=None,openapi_url='/openapi.json' if demo else None)
 app.add_middleware(SessionMiddleware,secret_key=secret,session_cookie='telecomiq_session',max_age=3600,same_site='lax',https_only=not demo)
 allowed_origin=urlparse(public).scheme+'://'+urlparse(public).netloc
 @app.middleware('http')
 async def boundaries(request,call_next):
  if request.method in ['POST','PUT','PATCH','DELETE']:
   if request.headers.get('origin')!=allowed_origin:return JSONResponse({'detail':'Origin not permitted'},status_code=403)
   if int(request.headers.get('content-length','0') or 0)>10_500_000:return JSONResponse({'detail':'Request too large'},status_code=413)
  response=await call_next(request);response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='no-referrer';response.headers['Cache-Control']='no-store'
  if not demo:response.headers['X-Frame-Options']='SAMEORIGIN'
  return response
 def eng(request):return request.app.state.engine
 def new_session(request,identity):
  e=eng(request);sid=secrets.token_urlsafe(40);csrf=secrets.token_urlsafe(32)
  with e.connect() as con:con.execute('INSERT INTO sessions VALUES (?,?,?,?)',(hashlib.sha256(sid.encode()).hexdigest(),e.cipher.encrypt(json.dumps(identity).encode()).decode(),csrf,time.time()+3600))
  request.session.clear();request.session['sid']=sid
  return csrf
 def current(request,write=False):
  e=eng(request);sid=request.session.get('sid')
  if not sid:raise HTTPException(401,'Sign in required')
  with e.connect() as con:row=con.execute('SELECT identity_cipher,csrf,expires FROM sessions WHERE sid_hash=?',(hashlib.sha256(sid.encode()).hexdigest(),)).fetchone()
  if not row or row[2]<=time.time():raise HTTPException(401,'Session expired')
  if write and not secrets.compare_digest(request.headers.get('x-csrf-token',''),row[1]):raise HTTPException(403,'CSRF check failed')
  identity=json.loads(e.cipher.decrypt(row[0].encode()));return identity,row[1]
 @app.exception_handler(PermissionError)
 async def forbidden(request,exc):return JSONResponse({'detail':'Access denied for this role, purpose or scope'},status_code=403)
 @app.exception_handler(ValueError)
 async def invalid(request,exc):return JSONResponse({'detail':str(exc)[:180]},status_code=400)
 @app.get('/',response_class=HTMLResponse)
 def index():return (Path(__file__).parent/'static/index.html').read_text()
 @app.get('/health/live')
 def live():return {'status':'alive'}
 @app.get('/health/ready')
 def ready(request:Request):return {'status':'ready','data_mode':'synthetic','sso_mode':'demo' if demo else 'OIDC'}
 @app.get('/api/config')
 def config(request:Request):return {'llm_backend':eng(request).generator.backend,'embedding_backend':eng(request).embedder.backend,'demo':demo,'sso_configured':not demo,'data_mode':'synthetic','snapshot':str(AS_OF.date()),'demo_profiles':list(DEMO_PROFILES) if demo else [],'role':'telecom analyst'}
 @app.post('/auth/demo')
 def demo_login(request:Request,body:DemoBody):
  if not demo:raise HTTPException(403,'Demo login is disabled')
  if body.profile not in DEMO_PROFILES:raise HTTPException(400,'Unknown demo role')
  new_session(request,DEMO_PROFILES[body.profile]);return {'signed_in':True,'mode':'synthetic demo role'}
 @app.get('/auth/login')
 async def login(request:Request):
  if demo:return RedirectResponse(public+'/')
  # Authlib verifies state/nonce and PKCE callback flow. The configured issuer is trusted, not request-supplied.
  kwargs={'login_hint':os.getenv('OIDC_LOGIN_HINT')} if os.getenv('OIDC_LOGIN_HINT') else {}
  return await oauth.enterprise.authorize_redirect(request,public+'/auth/callback',**kwargs)
 @app.get('/auth/callback')
 async def oidc_callback(request:Request):
  if demo:raise HTTPException(404)
  try:
   token=await oauth.enterprise.authorize_access_token(request);claims=token.get('userinfo')
   if not claims:raise PermissionError('Validated ID-token claims missing')
   identity=map_identity(claims,issuer,directory);new_session(request,identity)
  except Exception:raise HTTPException(401,'SSO validation or enterprise provisioning failed')
  return RedirectResponse(public+'/')
 @app.get('/api/session')
 def session(request:Request):
  identity,csrf=current(request);_,allowed=eng(request).scope(identity);return {'identity':{k:identity[k] for k in ['tenant','roles','zones','cities','purposes']},'csrf':csrf,'cities':records_for_cities(allowed),'can_review':'compliance_reviewer' in identity['roles'],'can_pii':'customer_support' in identity['roles'],'sso_mode':'demo' if demo else 'OIDC'}
 @app.post('/auth/logout')
 def logout(request:Request):
  current(request,True);sid=request.session.get('sid')
  with eng(request).connect() as con:con.execute('DELETE FROM sessions WHERE sid_hash=?',(hashlib.sha256(sid.encode()).hexdigest(),))
  request.session.clear();return {'signed_out':True}
 @app.get('/api/dashboard')
 def dashboard(request:Request,zone:str='All',city:str='All',tier:str='All'):
  identity,_=current(request);return eng(request).dashboard(identity,{'zone':zone,'city':city,'tier':tier})
 @app.post('/api/chat')
 def chat(request:Request,body:ChatBody):
  identity,_=current(request,True);return eng(request).chat(body.question,identity,body.filters.model_dump())
 @app.get('/api/customers')
 def customers(request:Request,zone:str='All',city:str='All',tier:str='All',offset:int=0,limit:int=100):
  identity,_=current(request);return eng(request).customer_page(identity,{'zone':zone,'city':city,'tier':tier},offset,limit)
 @app.post('/api/customers/{customer_id}/pii')
 def pii(request:Request,customer_id:str,body:PIIBody):
  identity,_=current(request,True);return eng(request).pii(identity,customer_id,body.purpose)
 @app.get('/api/knowledge')
 def knowledge(request:Request,zone:str='All',city:str='All',tier:str='All'):
  identity,_=current(request);return eng(request).knowledge(identity,{'zone':zone,'city':city,'tier':tier})
 @app.get('/api/observability')
 def observability(request:Request,zone:str='All',city:str='All',tier:str='All'):
  identity,_=current(request);return eng(request).observability(identity,{'zone':zone,'city':city,'tier':tier})
 @app.get('/api/cases')
 def cases(request:Request):
  identity,_=current(request);return eng(request).cases(identity)
 @app.post('/api/cases')
 def create_case(request:Request,body:CaseBody):
  identity,_=current(request,True);return eng(request).create_case(identity,body.filters.model_dump(),body.summary)
 @app.post('/api/cases/{case_id}/review')
 def review_case(request:Request,case_id:str,body:DecisionBody):
  identity,_=current(request,True);return eng(request).review_case(identity,case_id,body.decision)
 @app.post('/api/knowledge/stage')
 async def stage(request:Request,file:UploadFile=File(...),zone:str=Form('All'),source_url:str=Form(''),license_note:str=Form('')):
  identity,_=current(request,True);content=await file.read(10_000_001);return eng(request).stage_upload(identity,file.filename,content,{'zone':zone,'city':'All','tier':'All'},source_url,license_note)
 @app.post('/api/knowledge/{staged_id}/approve')
 def approve(request:Request,staged_id:str):
  identity,_=current(request,True);return eng(request).approve_upload(identity,staged_id)
 @app.get('/api/exports/cities.csv')
 def export(request:Request,zone:str='All',city:str='All',tier:str='All'):
  identity,_=current(request);import pandas as pd
  text=pd.DataFrame(eng(request).city_rows(identity,{'zone':zone,'city':city,'tier':tier})).to_csv(index=False);return StreamingResponse(iter([text]),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="TelecomIQ_Scoped_City_KPIs.csv"'})
 @app.get('/api/spectrum')
 def spectrum(request:Request,zone:str='All',city:str='All',tier:str='All'):
  identity,_=current(request);e=eng(request);from .engine import records
  return records(e.frame('spectrum',identity,{'zone':zone,'city':city,'tier':tier}))
 return app

def records_for_cities(allowed):
 return json.loads(CITIES[CITIES.city.isin(allowed)].to_json(orient='records'))

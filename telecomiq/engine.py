import json,sqlite3,time,uuid,re,hashlib,threading,io
from pathlib import Path
import numpy as np,pandas as pd
from cryptography.fernet import Fernet
from .data import build_data,CITIES,AS_OF
from .models import fit_models
from .knowledge import catalog,redact,digest
from .agents import *
ZONES=sorted(CITIES.zone.unique())
DEMO_PROFILES={
 'analyst':{'sub':'demo-analyst','tenant':'telecom-demo','roles':['telecom_analyst'],'zones':ZONES,'cities':['All'],'purposes':['analytics']},
 'noc_south':{'sub':'demo-noc-south','tenant':'telecom-demo','roles':['noc_engineer'],'zones':['South'],'cities':['All'],'purposes':['network_operations']},
 'support_north':{'sub':'demo-support','tenant':'telecom-demo','roles':['customer_support'],'zones':['North'],'cities':['Delhi','Jaipur'],'purposes':['case_resolution']},
 'reviewer':{'sub':'demo-independent-reviewer','tenant':'telecom-demo','roles':['compliance_reviewer'],'zones':ZONES,'cities':['All'],'purposes':['regulatory_review']}}
class ScopeConflict(ValueError):pass

def actor_key(identity):return hashlib.sha256((identity['tenant']+'|'+identity['sub']).encode()).hexdigest()
def require(identity,permission):
 rights={'analytics.read':{'telecom_analyst','noc_engineer','customer_support','compliance_reviewer'},'pii.read':{'customer_support'},'case.review':{'compliance_reviewer'},'knowledge.review':{'compliance_reviewer'}}
 if permission in rights and not set(identity['roles'])&rights[permission]:raise PermissionError('Role not permitted')
 if not identity.get('tenant') or not identity.get('zones') or not identity.get('cities'):raise PermissionError('Empty authorization scope')

def sanitize(value):
 if isinstance(value,dict):return {k:sanitize(v) for k,v in value.items()}
 if isinstance(value,(list,tuple)):return [sanitize(v) for v in value]
 if isinstance(value,(np.integer,np.bool_)):return value.item()
 if isinstance(value,(np.floating,float)):return float(value) if np.isfinite(value) else None
 if isinstance(value,(pd.Timestamp,)):return value.isoformat()
 return value

def records(df):return json.loads(df.to_json(orient='records',date_format='iso'))

class Engine:
 def __init__(self,root='runtime',smoke=False,pii_key=None,embedding_backend='sparse',llm_backend='extractive',demo=True):
  self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.db=self.root/'telecomiq.sqlite';self.demo=demo;self.lock=threading.RLock();self.requests=[];self.audit=[];self.staged={};self.case_lock=threading.RLock()
  self.data=build_data(self.root,pii_key,smoke);self.cipher=Fernet(self.data.pop('pii_key'));self.models=fit_models(self.data);self.docs=catalog();self.initial_trace=StageTrace()
  self.parser=ParserAgent();self.redactor=RedactionAgent();self.chunker=ChunkingAgent();self.embedder=EmbeddingAgent(embedding_backend);self.vector=VectorDBAgent(self.db);self.searcher=VectorSearchAgent();self.intent=IntentAgent();self.context=ContextEnrichmentAgent();self.generator=GenerationAgent(llm_backend);self.validator=ValidationAgent();self.hitl=HITLAgent()
  self.reindex(self.initial_trace)
  with self.connect() as con:
   self.data.pop('pii').to_sql('pii_store',con,if_exists='replace',index=False)
   con.execute('CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, tenant TEXT NOT NULL, requester TEXT NOT NULL, cities TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL, reviewer TEXT, updated REAL NOT NULL)')
   con.execute('CREATE TABLE IF NOT EXISTS sessions (sid_hash TEXT PRIMARY KEY, identity_cipher TEXT NOT NULL, csrf TEXT NOT NULL, expires REAL NOT NULL)')
  self.eval_retrieval=self.evaluate_retrieval()
 def connect(self):return sqlite3.connect(self.db,timeout=20)
 def reindex(self,trace):
  with self.lock:
   chunks=[]
   for doc in SourceCatalogAgent().approved(self.docs,trace):
    pages=self.parser.parse(doc['text'].encode(),'.txt',trace);pages=self.redactor.run(pages,trace);chunks.extend(self.chunker.run(doc,pages,trace))
   if len(chunks)>1024:raise ValueError('Corpus cap 1024 chunks; shard/review before growth')
   matrix=self.embedder.fit(chunks,trace);self.vector.replace(chunks,matrix,self.embedder.model_id,trace);self.chunks=chunks
 def scope(self,identity,filters=None):
  require(identity,'analytics.read');f={'zone':'All','city':'All','tier':'All',**(filters or {})}
  if set(f)-{'zone','city','tier'}:raise ValueError('Unsupported filter field')
  cities=CITIES[CITIES.zone.isin(identity['zones'])]
  if 'All' not in identity['cities']:cities=cities[cities.city.isin(identity['cities'])]
  for key in ['zone','city','tier']:
   if f[key]=='All':continue
   universe=CITIES[key].unique()
   if f[key] not in universe:raise ValueError('Unknown '+key)
   if key=='zone' and f[key] not in identity['zones']:raise PermissionError('Zone unauthorized')
   if key=='city' and f[key] not in set(cities.city):raise PermissionError('City unauthorized')
   cities=cities[cities[key].eq(f[key])]
  return f,cities.city.tolist()
 def frame(self,name,identity,filters=None):
  f,allowed=self.scope(identity,filters);d=self.data[name]
  if identity['tenant']!='telecom-demo':return d.iloc[:0].copy()
  return d[d.city.isin(allowed)].copy()
 def resolve(self,q,identity,filters):
  f,allowed=self.scope(identity,filters);low=q.lower();named=[c for c in CITIES.city if re.search(r'\b'+re.escape(c.lower())+r'\b',low)];zones=[z for z in ZONES if re.search(r'\b'+z.lower()+r'\b',low)]
  if len(named)>1 or len(zones)>1:raise ScopeConflict('Select one named city/zone or use the all-scope summary.')
  if zones:
   if f['zone']!='All' and zones[0]!=f['zone']:raise ScopeConflict('Question conflicts with the zone filter.')
   f['zone']=zones[0]
  if named:
   if f['city']!='All' and named[0]!=f['city']:raise ScopeConflict('Question conflicts with the city filter.')
   target=CITIES[CITIES.city.eq(named[0])].iloc[0]
   if f['zone']!='All' and f['zone']!=target.zone:raise ScopeConflict('Question conflicts with the zone/city filter.')
   f['city']=named[0];f['zone']=target.zone
  self.scope(identity,f);return f
 def summary(self,identity,filters=None):
  f,allowed=self.scope(identity,filters);nw=self.frame('network',identity,f);monthly=self.frame('monthly',identity,f);dr=self.frame('daily_revenue',identity,f);tickets=self.frame('tickets',identity,f);surveys=self.frame('surveys',identity,f)
  recent=nw[nw.date>=AS_OF-pd.Timedelta(days=7)];last=monthly[monthly.month.eq(pd.Timestamp('2026-10-01'))];mtd=dr[dr.date>=pd.Timestamp('2026-11-01')]
  ratio=lambda a,b:float(a/b) if b else None
  closed=tickets[tickets.status.eq('Resolved')];opened=tickets[tickets.status.eq('Open')]
  return {'cities':len(allowed),'revenue_mtd_inr':float(mtd.billed_service_revenue_inr.sum()),'revenue_mtd_through':'2026-11-21','active_subscribers_oct':int(last.closing_subscribers.sum()),'arpu_oct_inr':ratio(last.billed_service_revenue_inr.sum(),last.average_subscribers.sum()),'churn_oct_pct':None if last.opening_subscribers.sum()==0 else 100*ratio(last.churned_subscribers.sum(),last.opening_subscribers.sum()),
   'cssr_7d_pct':None if recent.call_attempts.sum()==0 else 100*ratio(recent.call_setup_successes.sum(),recent.call_attempts.sum()),'drop_7d_pct':None if recent.connected_calls.sum()==0 else 100*ratio(recent.dropped_calls.sum(),recent.connected_calls.sum()),'availability_7d_pct':None if recent.eligible_site_minutes.sum()==0 else 100*(1-ratio(recent.unavailable_site_minutes.sum(),recent.eligible_site_minutes.sum())),
   'throughput_7d_mbps':ratio(recent.downloaded_mbit.sum(),recent.dl_active_seconds.sum()),'latency_7d_ms':ratio(recent.latency_sum_ms.sum(),recent.latency_samples.sum()),'prb_7d_pct':None if recent.prb_capacity_units.sum()==0 else 100*ratio(recent.prb_used_units.sum(),recent.prb_capacity_units.sum()),'handover_7d_pct':None if recent.handover_attempts.sum()==0 else 100*ratio(recent.handover_successes.sum(),recent.handover_attempts.sum()),'packet_loss_7d_pct':None if recent.packet_sent.sum()==0 else 100*ratio(recent.packet_lost.sum(),recent.packet_sent.sum()),'data_7d_tb':float(recent.data_gb.sum()/1000),
   'ticket_register_open':len(opened),'ticket_register_over_internal_sla':int(opened.age_hours.gt(opened.internal_sla_hours).sum()),'mttr_resolved_hours':float(closed.resolution_hours.mean()) if len(closed) else None,'first_contact_resolution_pct':float(closed.first_contact_resolution.mean()*100) if len(closed) else None,
   'survey_responses':len(surveys),'nps':float((surveys.nps_score.ge(9).mean()-surveys.nps_score.le(6).mean())*100) if len(surveys)>=30 else None,'csat_pct':float(surveys.csat_score.ge(4).mean()*100) if len(surveys)>=30 else None,'customer_sample_rows':len(self.frame('customers',identity,f)),'network_anomaly_flags_7d':int(recent.anomaly_flag.sum())}
 def city_rows(self,identity,filters=None):
  f,cities=self.scope(identity,filters);out=[]
  for city in cities:
   cf={**f,'city':city};m=self.summary(identity,cf);meta=CITIES[CITIES.city.eq(city)].iloc[0].to_dict();high=(m['drop_7d_pct'] or 0)>2 or (m['availability_7d_pct'] is not None and m['availability_7d_pct']<99) or (m['prb_7d_pct'] or 0)>90
   med=(m['drop_7d_pct'] or 0)>1 or (m['availability_7d_pct'] is not None and m['availability_7d_pct']<99.5) or (m['prb_7d_pct'] or 0)>80 or (m['churn_oct_pct'] or 0)>3 or m['network_anomaly_flags_7d']>0
   out.append({**meta,**m,'criticality':'High' if high else 'Medium' if med else 'Low'})
  return sanitize(out)
 def dashboard(self,identity,filters=None):
  f,allowed=self.scope(identity,filters);m=self.summary(identity,f);cities=self.city_rows(identity,f);r=self.frame('daily_revenue',identity,f);nw=self.frame('network',identity,f);month=self.frame('monthly',identity,f)
  revenue=records(r[r.date>=AS_OF-pd.Timedelta(days=30)].groupby('date',as_index=False).billed_service_revenue_inr.sum());trend=[]
  for day,g in nw[nw.date>=AS_OF-pd.Timedelta(days=30)].groupby('date'):
   trend.append({'date':day.isoformat(),'drop_pct':100*float(g.dropped_calls.sum()/g.connected_calls.sum()),'availability_pct':100*(1-float(g.unavailable_site_minutes.sum()/g.eligible_site_minutes.sum()))})
  mt=month.groupby('month',as_index=False).agg(revenue=('billed_service_revenue_inr','sum'),opening=('opening_subscribers','sum'),churned=('churned_subscribers','sum'),closing=('closing_subscribers','sum'));mt['churn_pct']=mt.churned/mt.opening*100
  forecast=self.models['forecasts'];forecast=forecast[forecast.city.isin(allowed)];fc=records(forecast.groupby('month',as_index=False).forecast_revenue_inr.sum())
  review_value=sum(c['revenue_mtd_inr'] for c in cities if c['criticality']!='Low')
  return sanitize({'filters':f,'metrics':m,'city_rows':cities,'review_linked_mtd_inr':review_value,'revenue_trend':revenue,'network_trend':trend,'monthly':records(mt.tail(12)),'forecast':fc,'model_metrics':self.models['model_metrics'],'model_selection':self.models['model_selection'],'subgroup_metrics':self.models['subgroup_metrics'],'forecast_evaluation':[r for r in self.models['forecast_eval'] if r['city'] in allowed], 'drift':self.models['drift'],'quality':self.data['quality'],'data_notice':'Synthetic operator aggregates; customer sample is not population. Internal alerts are not TRAI compliance findings.'})
 def retrieve(self,q,identity,filters,trace,k=4):
  with self.lock:
   policy_date=AS_OF.date() if self.demo else pd.Timestamp.now(tz='UTC').date();rows=self.vector.authorized(identity,filters,policy_date,trace);v=self.embedder.query(q,trace);return self.searcher.run(rows,v,self.embedder.model_id,trace,k)
 def analyst_answer(self,identity,f,m):
  label=' / '.join(v for v in f.values() if v!='All') or 'all authorized locations';money=lambda v:f'INR {v:,.0f}'
  text=f"For {label}, the last seven full network days show RAT-service availability of {m['availability_7d_pct']:.2f}%, dropped-call rate {m['drop_7d_pct']:.2f}%, and mean active-download throughput {m['throughput_7d_mbps']:.1f} Mbps. These are weighted demo counter definitions, not regulatory compliance findings. [GOLD-NETWORK]\n\n"
  text+=f"Billed service revenue MTD through 21 November is {money(m['revenue_mtd_inr'])}. For completed October, active subscribers total {m['active_subscribers_oct']:,}, weighted ARPU is {money(m['arpu_oct_inr'])} and observed churn is {m['churn_oct_pct']:.2f}%. MTD revenue, completed-month ARPU/churn and the historical customer sample use different cohorts. [GOLD-FINANCE]\n\n"
  steps=[]
  if m['drop_7d_pct']>1 or m['availability_7d_pct']<99.5:steps.append('Ask the NOC owner to inspect the affected city/RAT and cell-level outage, handover and counter-freshness evidence before confirming cause or proposing a change. [SOP-002:1:0] [SOP-003:1:0]')
  if m['prb_7d_pct']>80:steps.append('Have capacity engineering check busy-hour PRB, transport and cell load before proposing a capacity/RF review. No spectrum change is authorized by this analysis. [SOP-004:1:0]')
  if m['churn_oct_pct']>3:steps.append('Ask retention operations to review scoped complaint/usage factors and consent, using model scores as review support rather than an automatic offer or customer-contact decision. [SOP-007:1:0] [SOP-016:1:0]')
  if m['ticket_register_over_internal_sla']:steps.append(f"Assign the {m['ticket_register_over_internal_sla']:,} open ticket-register items exceeding their internal target to support operations. The 48-hour demo target is not a statutory deadline. [GOLD-TICKETS] [SOP-012:1:0]")
  if not steps:steps.append('No primary internal city-level trigger dominates this selection. Continue monitoring and investigate any authorized anomaly flags with event-level evidence. [SOP-013:1:0]')
  text+='Recommended review sequence:\n'+'\n'.join(f'{i+1}. {s}' for i,s in enumerate(steps[:4]))
  return text+'\n\nThese are evidence-review proposals. Confirmed RCA, actual loss, spectrum rights and realized benefit are not established; no network change or customer message is executed. [SOP-014:1:0] [SOP-030:1:0]'
 def chat(self,q,identity,filters=None):
  start=time.perf_counter();safe_q=redact(q);trace=StageTrace();outcome='answered';usage={};evidence=[];answer='';sources=[];f={'zone':'All','city':'All','tier':'All',**(filters or {})};intent='unknown'
  try:
   if not q.strip() or len(q)>1800:raise ValueError('Question must contain 1–1800 characters')
   intent=self.intent.run(q,trace)
   with trace.span('authorization_and_scope'):f=self.resolve(q,identity,f)
   _,cities=self.scope(identity,f)
   if intent=='blocked':outcome='blocked';answer='Request blocked. Prompts cannot bypass controls or expose secrets.'
   elif intent=='pii':outcome='abstained';answer='The chat pipeline cannot retrieve personal contact details. Authorized support users must use the separate purpose-bound PII workflow.'
   elif intent=='unsupported':outcome='abstained';answer='I cannot establish actual loss/profit/savings, confirmed RCA, guaranteed results, full regulatory compliance or current market share from these synthetic facts and reference digests.'
   elif not cities:outcome='abstained';answer='No authorized locations match this filter combination.'
   else:
    with trace.span('governed_kpi_tool'):m=self.summary(identity,f)
    evidence=self.retrieve(safe_q,identity,f,trace)
    if intent in ['regulatory','policy']:
     if intent=='regulatory':evidence=[e for e in evidence if e['kind'] in ['official_digest','official_full']]
     insufficient=intent=='regulatory' and re.search(r'benchmark|threshold|penalt|fully compliant|deadline|fine|numeric|exact limit',q.lower()) and not any(e['kind']=='official_full' for e in evidence)
     if not evidence or insufficient:outcome='abstained';answer=('I abstain: the approved evidence does not establish the requested applicable rule or numerical compliance benchmark. A current full primary instrument and accountable regulatory review are required; internal demo thresholds are not TRAI limits.' if intent=='regulatory' else 'I abstain: no approved current evidence supports this question. Ask about authorized telecom KPIs or provide an appropriate reviewed source.')
     else:
      packet=self.context.run(identity,f,m,evidence,trace);payload,usage=self.generator.run(safe_q,packet,trace);claims=self.validator.run(payload,evidence,trace)
      if not claims:outcome='abstained';answer='No sufficiently supported policy statement was produced; the answer is withheld.'
      else:answer='From the approved evidence for this scope:\n\n'+'\n\n'.join(c['quote']+' ['+c['source_id']+']' for c in claims)+'\n\nReference digests are not a complete legal instrument or an operator-specific compliance decision.';sources=[c['source_id'] for c in claims]
    elif intent=='forecast':
     with trace.span('forecast_tool'):
      d=self.models['forecasts'];d=d[d.city.isin(cities)];g=d.groupby('month').forecast_revenue_inr.sum();answer='For the selected authorized locations, the next model months project billed service revenue of '+ '; '.join(f'{month:%b %Y}: INR {v:,.0f}' for month,v in g.items())+'. [MODEL-FORECAST]\n\nThese are three-month scenarios after the October cutoff, selected before the six-month test holdout. No calibrated interval, guaranteed revenue or realized saving is claimed. Current November MTD is a separate partial-period observation. [SOP-009:1:0]';sources=['MODEL-FORECAST','SOP-009:1:0']
    elif intent=='action':
     self.hitl.required(intent,trace);case=self.create_case(identity,f,'Review requested through analyst workflow');outcome='hitl_required';answer=f"Created {case['id']} as an unexecuted review draft. An independent authorized reviewer must assess evidence. Approval does not execute an RF change, service block or customer notification. [SOP-030:1:0]";sources=['SOP-030:1:0']
    else:
     # Policy passages are evidence context; controlled numeric prose is computed exclusively by the tools.
     packet=self.context.run(identity,f,m,evidence,trace)
     if evidence:
      payload,usage=self.generator.run(safe_q,packet,trace);policy_claims=self.validator.run(payload,evidence,trace)
     else:policy_claims=[]
     self.hitl.required(intent,trace)
     with trace.span('analyst_tool_narrative',{'backend':'governed deterministic calculations'}):answer=self.analyst_answer(identity,f,m)
     if policy_claims:answer+='\n\nApproved playbook context: '+policy_claims[0]['quote']+' ['+policy_claims[0]['source_id']+']'
     sources=re.findall(r'\[([^\]]+)\]',answer)
   if intent!='action':self.hitl.required(intent,trace)
   with trace.span('final_source_validation'):
    rows=self.vector.authorized(identity,f,AS_OF.date() if self.demo else pd.Timestamp.now(tz='UTC').date(),trace);valid={c['chunk_id'] for c,*_ in rows}|{'GOLD-NETWORK','GOLD-FINANCE','GOLD-TICKETS','MODEL-FORECAST'}
    if not set(sources)<=valid:raise ValueError('Unresolved or unauthorized source')
  except ScopeConflict as exc:outcome='clarify';answer=str(exc)
  except PermissionError:outcome='blocked';answer='Access denied for the requested tenant, role, zone or city.'
  except Exception as exc:outcome='abstained';answer='Answer withheld: '+type(exc).__name__+'. Review scope, configuration or evidence before retrying.'
  event={'id':uuid.uuid4().hex,'timestamp':pd.Timestamp.now(tz='UTC').isoformat(),'principal':actor_key(identity),'tenant':identity['tenant'],'roles':identity['roles'],'filters':f,'intent':intent,'outcome':outcome,'latency_ms':(time.perf_counter()-start)*1000,'sources':list(dict.fromkeys(sources)),'top_similarity':evidence[0]['score'] if evidence else None,'stages':trace.events,'query_sha256':digest(q),'input_tokens':usage.get('input_tokens'),'output_tokens':usage.get('output_tokens'),'model':usage.get('model',self.generator.backend),'citation_ids_valid':outcome!='abstained' or not sources,'cost_usd':None}
  with self.lock:self.requests.append(event);self.requests=self.requests[-2000:]
  return {'answer':answer,'outcome':outcome,'sources':event['sources'],'trace_id':event['id'],'stages':trace.events}
 def create_case(self,identity,filters,summary):
  f,cities=self.scope(identity,filters)
  if not cities:raise ValueError('Empty case scope')
  case={'id':'REV-'+uuid.uuid4().hex[:10],'scope':f,'summary':redact(summary)[:300],'executed':False,'rule_basis':'Internal demo triggers; not a regulatory finding'}
  with self.connect() as con:con.execute('INSERT INTO cases VALUES (?,?,?,?,?,?,?,?)',(case['id'],identity['tenant'],actor_key(identity),json.dumps(cities),json.dumps(case),'draft',None,time.time()))
  return {**case,'status':'draft'}
 def cases(self,identity):
  _,allowed=self.scope(identity);out=[]
  with self.connect() as con:rows=con.execute('SELECT id,requester,cities,payload,status,reviewer FROM cases WHERE tenant=?',(identity['tenant'],)).fetchall()
  for cid,requester,cities,payload,status,reviewer in rows:
   if set(json.loads(cities))<=set(allowed):out.append({**json.loads(payload),'status':status,'requester':requester,'reviewer':reviewer,'can_review':'compliance_reviewer' in identity['roles'] and requester!=actor_key(identity)})
  return out
 def review_case(self,identity,case_id,decision):
  require(identity,'case.review')
  if decision not in ['approved','rejected']:raise ValueError('Invalid decision')
  with self.connect() as con:
   con.execute('BEGIN IMMEDIATE');row=con.execute('SELECT tenant,requester,cities,status FROM cases WHERE id=?',(case_id,)).fetchone()
   if not row or row[0]!=identity['tenant']:raise PermissionError('Case inaccessible')
   _,allowed=self.scope(identity)
   if not set(json.loads(row[2]))<=set(allowed) or row[1]==actor_key(identity):raise PermissionError('Independent authorized reviewer required')
   if row[3]!='draft':raise ValueError('Case already reviewed')
   con.execute('UPDATE cases SET status=?,reviewer=?,updated=? WHERE id=?',(decision,actor_key(identity),time.time(),case_id))
  self.audit.append({'event':'review_decision','case_id':case_id,'actor':actor_key(identity),'decision':decision,'executed':False});return {'id':case_id,'status':decision,'executed':False}
 def pii(self,identity,customer_id,purpose):
  require(identity,'pii.read')
  if purpose!='case_resolution' or purpose not in identity['purposes']:raise PermissionError('Purpose not permitted')
  _,allowed=self.scope(identity)
  with self.connect() as con:row=con.execute('SELECT city,ciphertext FROM pii_store WHERE customer_id=? AND tenant=?',(customer_id,identity['tenant'])).fetchone()
  if not row or row[0] not in allowed:raise PermissionError('Customer inaccessible')
  self.audit.append({'event':'purpose_bound_pii_read','actor':actor_key(identity),'record_sha256':digest(customer_id),'purpose':purpose});return json.loads(self.cipher.decrypt(row[1].encode()))
 def customer_page(self,identity,filters=None,offset=0,limit=100):
  if not 0<=offset or not 1<=limit<=200:raise ValueError('Invalid page')
  d=self.frame('customers',identity,filters);cols=['customer_id','city','zone','tier','plan','feature_date','tenure_months','complaints_90d','churn_score'];return {'total':len(d),'offset':offset,'rows':records(d.iloc[offset:offset+limit][cols]),'notice':'Historical synthetic sample; no contact data or individual automatic targeting.'}
 def knowledge(self,identity,filters=None):
  f,_=self.scope(identity,filters);trace=StageTrace();rows=self.vector.authorized(identity,f,AS_OF.date() if self.demo else pd.Timestamp.now(tz='UTC').date(),trace);return [{k:c.get(k) for k in ['chunk_id','title','authority','kind','url','version','reviewer','valid_from','valid_until','page','passage']} for c,*_ in rows]
 def observability(self,identity,filters=None):
  f,_=self.scope(identity,filters);events=[e for e in self.requests if e['principal']==actor_key(identity) and all(v=='All' or e['filters'].get(k)==v for k,v in f.items())];lat=[e['latency_ms'] for e in events];n=len(events);pct=lambda q:float(np.quantile(lat,q)) if lat else None
  stages={}
  for e in events:
   for s in e['stages']:stages.setdefault(s['agent'],[]).append(s['elapsed_ms'])
  return sanitize({'metrics':{'requests_in_scope':n,'p50_ms':pct(.5),'p95_ms':pct(.95),'p99_ms':pct(.99),'abstention_rate':sum(e['outcome']=='abstained' for e in events)/n if n else None,'block_rate':sum(e['outcome']=='blocked' for e in events)/n if n else None,'scope_clarification_rate':sum(e['outcome']=='clarify' for e in events)/n if n else None,'hitl_requests':sum(e['outcome']=='hitl_required' for e in events),'citation_id_validity':sum(e['citation_ids_valid'] for e in events)/n if n else None,'measured_llm_input_tokens':sum(e['input_tokens'] or 0 for e in events) if any(e['input_tokens'] is not None for e in events) else None,'measured_llm_output_tokens':sum(e['output_tokens'] or 0 for e in events) if any(e['output_tokens'] is not None for e in events) else None,'model_cost_usd':None,'cloud_uptime':None,'independent_answer_accuracy':None,'incident_precision_recall':None,'data_snapshot':str(AS_OF.date()),'source_review_snapshot':'2026-11-22','retrieval_fixture_hit_at_3':float(np.mean([r['hit_at_3'] for r in self.eval_retrieval])),'retrieval_fixture_mrr':float(np.mean([r['rr'] for r in self.eval_retrieval]))},'stage_timings':[{'agent':k,'calls':len(v),'p95_ms':float(np.quantile(v,.95))} for k,v in stages.items()],'traces':[{k:e[k] for k in ['id','timestamp','intent','outcome','latency_ms','sources','top_similarity','input_tokens','output_tokens','model']} for e in events[-40:]],'ingestion_stages':self.initial_trace.events,'embedding_metadata':{'backend':self.embedder.backend,'model_id':self.embedder.model_id,'dimension':self.embedder.dimension,'index_type':'SQLite vector store + authorized exact cosine search'},'pending_review_count':sum(c['status']=='draft' for c in self.cases(identity)),'retrieval_evaluation':self.eval_retrieval,'quality':self.data['quality'],'drift':self.models['drift'],'disclaimer':'Fixed retrieval fixtures are not independent production accuracy; score is not probability. Unmeasured KPIs are N/A.'})
 def evaluate_retrieval(self):
  questions=[('dropped connected calls rate','SOP-002'),('availability outage site minutes','SOP-003'),('prb congestion capacity','SOP-004'),('throughput megabits download seconds','SOP-005'),('ARPU average subscriber revenue','SOP-008'),('NPS promoters detractors','SOP-011'),('TRAI access broadband QoS regulation','TRAI-QOS-2024'),('NFAP allocation assignment WPC','DOT-NFAP-2025'),('PII email phone purpose','SOP-022'),('human approval independent reviewer','SOP-030'),('huggingface dataset licence revision','SOP-032'),('temporal model validation calibration','SOP-019')];rows=[]
  for q,expected in questions:
   trace=StageTrace();hits=self.retrieve(q,DEMO_PROFILES['analyst'],{'zone':'All','city':'All','tier':'All'},trace,3);ids=[e['id'] for e in hits];rank=ids.index(expected)+1 if expected in ids else None;rows.append({'question':q,'expected':expected,'retrieved':ids,'hit_at_3':rank is not None,'rr':1/rank if rank else 0})
  return rows
 def stage_upload(self,identity,name,content,filters,source_url='',license_note=''):
  require(identity,'knowledge.review');f,cities=self.scope(identity,filters);trace=StageTrace();pages=self.parser.parse(content,Path(name).suffix,trace);clean=self.redactor.run(pages,trace);text='\n'.join(clean);h=digest(text)
  if any(d.get('content_sha256')==h for d in self.docs) or h in self.staged:raise ValueError('Duplicate source')
  quarantined=bool(re.search(r'ignore.*instructions|reveal.*secret|system prompt',text,re.I));doc={'id':'UP-'+h[:12],'title':Path(name).name[:100],'text':text,'tags':'user-reviewed upload','authority':'Uploaded source; reviewer must verify provenance','kind':'uploaded_policy','url':source_url,'license_note':license_note,'tenant':identity['tenant'],'zones':[f['zone']] if f['zone']!='All' else list(identity['zones']),'roles':['All'],'status':'quarantined' if quarantined else 'staged','version':h[:12],'valid_from':str(AS_OF.date()),'valid_until':'2026-12-22','content_sha256':h,'requester':actor_key(identity)}
  self.chunker.run(doc,clean,trace);self.staged[h]=doc;return {'id':h,'status':doc['status'],'title':doc['title'],'agent_stages':trace.events}
 def approve_upload(self,identity,staged_id):
  require(identity,'knowledge.review');d=self.staged.get(staged_id)
  if not d or d['tenant']!=identity['tenant']:raise PermissionError('Source inaccessible')
  if d['status']!='staged':raise ValueError('Quarantined source cannot be published')
  if not set(d['zones'])<=set(identity['zones']):raise PermissionError('Reviewer outside document scope')
  # Upload publication is a local workflow, distinct from operational HITL approval.
  d={**d,'status':'approved','reviewer':actor_key(identity)};self.docs.append(d);self.reindex(StageTrace());del self.staged[staged_id];return {'id':d['id'],'status':'approved'}

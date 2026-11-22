"""Deterministic fictional asset/hourly scenarios, separate from operator population counters."""
import numpy as np
import pandas as pd
from .data import AS_OF,SEED

def enrich_data(data):
 rng=np.random.default_rng(SEED+209);assets=[];hourly=[]
 for j,c in data['cities'].iterrows():
  for k in range(12):
   code=(j*3+k)%20
   status='Offline' if code==0 else 'Telemetry missing' if code in [1,2] else 'Degraded' if code in [3,4,5] else 'Online'
   missing=status=='Telemetry missing';hours=int(rng.integers(8,72)) if missing else round(float(rng.uniform(.01,.3)),2)
   assets.append({'tenant':'telecom-demo','city':c.city,'zone':c.zone,'tier':c.tier,'state':c.state,'asset_id':f'DEMO-SITE-{j+1:02d}-{k+1:02d}','asset_type':['Macro tower','Small cell','Fiber aggregation','Edge node'][k%4],'technology':'5G' if k%3 else '4G','latitude':round(c.latitude+rng.normal(0,.035),5),'longitude':round(c.longitude+rng.normal(0,.035),5),'status':status,'sensor_status':'No heartbeat' if missing else 'Healthy heartbeat','heartbeat_age_hours':hours,'last_seen':AS_OF-pd.Timedelta(hours=hours),'criticality':'High' if status=='Offline' else 'Medium' if status in ['Degraded','Telemetry missing'] else 'Low','prb_utilization_pct':None if missing else round(float(rng.uniform(82,98) if status=='Degraded' else rng.uniform(25,76)),1),'temperature_c':None if missing else round(float(rng.uniform(24,48)),1),'battery_pct':None if missing else round(float(rng.uniform(5,25) if status=='Offline' else rng.uniform(60,100)),1),'review_hypothesis':{'Offline':'Verify power and backhaul; cause unconfirmed','Telemetry missing':'Restore heartbeat path before inferring asset health','Degraded':'Inspect congestion and RF counters; cause unconfirmed','Online':'Routine monitoring'}[status]})
  for h in range(24):
   intensity=.45+.65*np.exp(-((h-20)/4)**2)+.3*np.exp(-((h-12)/4)**2)
   subscribers=int(rng.integers(3000,16000)*intensity*(2 if c.tier=='Tier-1' else 1));probes=max(50,subscribers//4);lat=float(rng.uniform(17,27)+(12 if h in [19,20,21] and j%7==0 else 0));capacity=12000
   hourly.append({'tenant':'telecom-demo','city':c.city,'zone':c.zone,'tier':c.tier,'timestamp':AS_OF-pd.Timedelta(days=1)+pd.Timedelta(hours=h),'hour':h,'traffic_gb':round(subscribers*rng.uniform(.007,.015),2),'concurrent_sessions':subscribers,'latency_sum_ms':lat*probes,'latency_samples':probes,'prb_used_units':round(capacity*min(.98,.22+.5*intensity+rng.uniform(-.04,.04)),2),'prb_capacity_units':capacity})
 data['quality'].extend([{'check':'Unique synthetic asset IDs','passed':len({a['asset_id'] for a in assets}),'total':len(assets)},{'check':'All asset coordinates valid','passed':sum(-90<=a['latitude']<=90 and -180<=a['longitude']<=180 for a in assets),'total':len(assets)},{'check':'Hourly coverage: 24 records per city','passed':len(hourly),'total':24*len(data['cities'])}])
 return {'assets':pd.DataFrame(assets),'hourly_traffic':pd.DataFrame(hourly)}

def scoped_enrichment(engine,identity,filters):
 assets=engine.frame('assets',identity,filters);hourly=engine.frame('hourly_traffic',identity,filters);customers=engine.frame('customers',identity,filters);tickets=engine.frame('tickets',identity,filters);nw=engine.frame('network',identity,filters);recent=nw[nw.date>=AS_OF-pd.Timedelta(days=7)]
 plan=customers.groupby('plan',as_index=False).agg(sample_subscribers=('customer_id','size'),average_bill_inr=('bill_inr','mean'),average_churn_score=('churn_score','mean'),average_usage_change_pct=('usage_change_pct','mean'))
 hg=hourly.groupby('hour',as_index=False).agg(traffic_gb=('traffic_gb','sum'),concurrent_sessions=('concurrent_sessions','sum'),latency_sum_ms=('latency_sum_ms','sum'),latency_samples=('latency_samples','sum'),prb_used_units=('prb_used_units','sum'),prb_capacity_units=('prb_capacity_units','sum'));hg['latency_ms']=hg.latency_sum_ms/hg.latency_samples;hg['prb_pct']=100*hg.prb_used_units/hg.prb_capacity_units;hg['date']=hg.hour.map(lambda h:f'2026-11-21T{h:02}:00:00')
 rat=[]
 for tech,g in recent.groupby('technology'):
  rat.append({'technology':tech,'drop_pct':100*g.dropped_calls.sum()/g.connected_calls.sum(),'availability_pct':100*(1-g.unavailable_site_minutes.sum()/g.eligible_site_minutes.sum()),'throughput_mbps':g.downloaded_mbit.sum()/g.dl_active_seconds.sum(),'prb_pct':100*g.prb_used_units.sum()/g.prb_capacity_units.sum(),'traffic_tb':g.data_gb.sum()/1000})
 return {'assets':assets.to_dict('records'),'asset_summary':{'sample_assets':len(assets),'online':int(assets.status.eq('Online').sum()),'offline':int(assets.status.eq('Offline').sum()),'degraded':int(assets.status.eq('Degraded').sum()),'telemetry_missing':int(assets.status.eq('Telemetry missing').sum())},'asset_status_mix':assets.groupby('status').size().rename('assets').reset_index().to_dict('records'),'plan_mix':plan.to_dict('records'),'hourly':hg.to_dict('records'),'rat_kpis':rat,'ticket_mix':tickets.groupby('category').size().rename('tickets').reset_index().to_dict('records'),'data_inventory':{'daily_history_days':int(nw.date.nunique()),'monthly_history_months':int(engine.data['monthly'].month.nunique()),'sample_assets':len(assets),'hourly_city_records':len(hourly),'synthetic':True}}

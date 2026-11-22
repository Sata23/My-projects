import json,zipfile,gzip,base64
from pathlib import Path
import pandas as pd
from .engine import records,DEMO_PROFILES
from .data import AS_OF

def build_offline_html(engine,out):
 d=engine.data;payload={}
 for name in ['network','daily_revenue']:
  frame=d[name];payload[name]=records(frame[frame.date>=AS_OF-pd.Timedelta(days=365)])
 payload['monthly']=records(d['monthly']);payload['cities']=records(d['cities']);payload['customers']=records(d['customers'][['customer_id','city','zone','tier','plan','feature_date','tenure_months','complaints_90d','churn_score','bill_inr','usage_change_pct']])
 for name in ['tickets','surveys','spectrum','assets','hourly_traffic']:payload[name]=records(d[name])
 payload.update({'forecasts':records(engine.models['forecasts']),'model_metrics':engine.models['model_metrics'],'model_selection':engine.models['model_selection'],'subgroup_metrics':engine.models['subgroup_metrics'],'drift':engine.models['drift'],'forecast_evaluation':engine.models['forecast_eval'],'quality':d['quality'],'city_rows':engine.city_rows(DEMO_PROFILES['analyst']),'profiles':DEMO_PROFILES,'chunks':[c for c in engine.chunks if c['tenant']=='telecom-demo'],'retrieval_evaluation':engine.eval_retrieval})
 safe=json.dumps(payload,separators=(',',':'),default=str,allow_nan=False).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
 static=Path(__file__).parent/'static';template=(static/'index.html').read_text();compressed=base64.b64encode(gzip.compress(safe.encode(),compresslevel=9,mtime=0)).decode()
 adapter='<script id="offlineData" type="application/octet-stream">'+compressed+'</script><script>window.TelecomOfflineReady=(async()=>{const b=Uint8Array.from(atob(document.getElementById("offlineData").textContent),c=>c.charCodeAt(0));const t=await new Response(new Blob([b]).stream().pipeThrough(new DecompressionStream("gzip"))).text();document.getElementById("offlineData").textContent=t;'+(static/'offline.js').read_text()+'})();window.TelecomOffline={request:async(...a)=>{await window.TelecomOfflineReady;return window.TelecomOffline.request(...a);}};</script>' 
 out=Path(out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(template.replace('<!--OFFLINE_ADAPTER-->',adapter));return out

def export_public_tables(engine,folder):
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
 for name in ['cities','network','monthly','daily_revenue','tickets','surveys','spectrum','assets','hourly_traffic']:engine.data[name].to_csv(folder/(name+'.csv'),index=False)
 engine.models['forecasts'].to_csv(folder/'revenue_forecasts.csv',index=False)
 scoped=engine.dashboard(DEMO_PROFILES['analyst'])
 for name in ['plan_mix','rat_kpis','asset_status_mix','ticket_mix','hourly']:pd.DataFrame(scoped[name]).to_csv(folder/(name+'_analytics.csv'),index=False)
 (folder/'model_manifest.json').write_text(json.dumps({'metrics':engine.models['model_metrics'],'splits':engine.models['split_manifest'],'data_mode':'synthetic','pii_exported':False},indent=2))
 return folder

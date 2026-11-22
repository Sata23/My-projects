import numpy as np,pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler,OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression,LinearRegression
from sklearn.ensemble import HistGradientBoostingClassifier,IsolationForest
from sklearn.metrics import average_precision_score,roc_auc_score,brier_score_loss,mean_absolute_error
NUM=['tenure_months','bill_inr','usage_change_pct','complaints_90d','drop_rate_pct','autopay'];CAT=['plan'];FEATURES=NUM+CAT

def fit_models(data):
 c=data['customers'];days=sorted(c.feature_date.unique());d1,d2=days[int(.6*len(days))],days[int(.8*len(days))];tr=c[c.feature_date<d1];va=c[(c.feature_date>=d1)&(c.feature_date<d2)];te=c[c.feature_date>=d2]
 assert tr.feature_date.max()<va.feature_date.min() and va.feature_date.max()<te.feature_date.min()
 # Labels available to each development cutoff: purge observations whose labels had not matured.
 tr=tr[tr.label_matures_at.lt(d1)];va=va[va.label_matures_at.lt(d2)]
 assert tr.label_matures_at.max()<va.feature_date.min() and va.label_matures_at.max()<te.feature_date.min()
 def prep():return ColumnTransformer([('num',make_pipeline(SimpleImputer(),StandardScaler()),NUM),('cat',OneHotEncoder(handle_unknown='ignore',sparse_output=False),CAT)])
 options={'Logistic baseline':make_pipeline(prep(),LogisticRegression(max_iter=400)),'Boosted churn':make_pipeline(prep(),HistGradientBoostingClassifier(max_iter=70,max_leaf_nodes=12,l2_regularization=4,random_state=42))};selection=[]
 for name,m in options.items():
  m.fit(tr[FEATURES],tr.churn_next_30d);p=m.predict_proba(va[FEATURES])[:,1];selection.append({'model':name,'validation_PR_AUC':float(average_precision_score(va.churn_next_30d,p))})
 best=max(selection,key=lambda x:x['validation_PR_AUC'])['model'];model=options[best];p=model.predict_proba(te[FEATURES])[:,1];c['churn_score']=model.predict_proba(c[FEATURES])[:,1]
 metrics={'model':best,'test_n':len(te),'test_PR_AUC':float(average_precision_score(te.churn_next_30d,p)),'test_ROC_AUC':float(roc_auc_score(te.churn_next_30d,p)),'test_Brier':float(brier_score_loss(te.churn_next_30d,p)),'train_end':str(tr.feature_date.max().date()),'validation_start':str(va.feature_date.min().date()),'test_start':str(te.feature_date.min().date()),'label_purge':'30-day label availability before each split'}
 subgroup=[{'zone':z,'n':int(te.zone.eq(z).sum()),'Brier':float(brier_score_loss(te.loc[te.zone.eq(z),'churn_next_30d'],p[te.zone.eq(z).to_numpy()]))} for z in sorted(te.zone.unique())]
 drift=[]
 for k in NUM:
  bins=np.unique(np.r_[-np.inf,np.quantile(tr[k],np.arange(.1,1,.1)),np.inf]);a=np.maximum(np.histogram(tr[k],bins)[0]/len(tr),1e-6);b=np.maximum(np.histogram(te[k],bins)[0]/len(te),1e-6);drift.append({'feature':k,'PSI':float(np.sum((b-a)*np.log(b/a)))})
 forecasts=[];feval=[]
 for city,g in data['monthly'].groupby('city'):
  g=g.sort_values('month');y=g.billed_service_revenue_inr.to_numpy();i=np.arange(len(y));tf=lambda x:np.c_[x,np.sin(2*np.pi*np.asarray(x)/12),np.cos(2*np.pi*np.asarray(x)/12)]
  m=LinearRegression().fit(tf(i[:24]),y[:24]);lv=mean_absolute_error(y[24:30],m.predict(tf(i[24:30])));sv=mean_absolute_error(y[24:30],y[12:18]);chosen='Linear + seasonality' if lv<sv else 'Seasonal naive'
  m.fit(tf(i[:30]),y[:30]);pred=np.maximum(0,m.predict(tf(i[30:]))) if chosen.startswith('Linear') else y[18:24]
  feval.append({'city':city,'model':chosen,'test_MAE_inr':float(mean_absolute_error(y[30:],pred)),'test_WAPE':float(np.abs(y[30:]-pred).sum()/y[30:].sum())})
  m.fit(tf(i),y);future=np.maximum(0,m.predict(tf(np.arange(36,39)))) if chosen.startswith('Linear') else y[24:27]
  for month,val in zip(pd.date_range('2026-11-01',periods=3,freq='MS'),future):forecasts.append({'city':city,'zone':g.zone.iloc[0],'tier':g.tier.iloc[0],'month':month,'forecast_revenue_inr':float(val),'model':chosen})
 # Train-only anomaly screen, then score operational rows. These are alerts, not labelled incidents.
 nw=data['network'];f=pd.DataFrame({'drop':nw.dropped_calls/nw.connected_calls*100,'unavailability':nw.unavailable_site_minutes/nw.eligible_site_minutes*100,'prb':nw.prb_used_units/nw.prb_capacity_units*100,'latency':nw.latency_sum_ms/nw.latency_samples})
 cutoff=nw.date.sort_values().iloc[int(.6*len(nw))];screen=IsolationForest(n_estimators=55,contamination=.025,random_state=42);screen.fit(f[nw.date<cutoff]);nw['anomaly_flag']=screen.predict(f)==-1
 return {'churn_model':model,'model_metrics':metrics,'model_selection':selection,'subgroup_metrics':subgroup,'drift':drift,'forecasts':pd.DataFrame(forecasts),'forecast_eval':feval,'anomaly_model':screen,'split_manifest':{'train_max':str(tr.feature_date.max()),'train_label_max':str(tr.label_matures_at.max()),'validation_min':str(va.feature_date.min()),'validation_label_max':str(va.label_matures_at.max()),'test_min':str(te.feature_date.min()),'features':FEATURES}}

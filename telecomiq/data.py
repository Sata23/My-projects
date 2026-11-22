from pathlib import Path
import json,hashlib,os
import numpy as np
import pandas as pd
from cryptography.fernet import Fernet
AS_OF=pd.Timestamp('2026-11-22');SEED=42
# Planning zones/tiers are demo classifications, not official government city-tier or LSA boundaries.
CITY_ROWS=[
 ('Delhi','North','Delhi',28.614,77.209,1),('Mumbai','West','Maharashtra',19.076,72.878,1),('Kolkata','East','West Bengal',22.573,88.364,1),('Chennai','South','Tamil Nadu',13.083,80.271,1),('Bengaluru','South','Karnataka',12.972,77.595,1),('Hyderabad','South','Telangana',17.385,78.487,1),('Pune','West','Maharashtra',18.520,73.857,1),('Ahmedabad','West','Gujarat',23.023,72.571,1),
 ('Jaipur','North','Rajasthan',26.912,75.787,2),('Lucknow','North','Uttar Pradesh',26.847,80.946,2),('Kanpur','North','Uttar Pradesh',26.450,80.332,2),('Varanasi','North','Uttar Pradesh',25.318,82.974,2),('Prayagraj','North','Uttar Pradesh',25.435,81.846,2),('Noida','North','Uttar Pradesh',28.535,77.391,2),('Gurugram','North','Haryana',28.459,77.027,2),('Chandigarh','North','Chandigarh',30.733,76.779,2),('Ludhiana','North','Punjab',30.901,75.857,2),('Amritsar','North','Punjab',31.634,74.872,2),('Jammu','North','Jammu and Kashmir',32.727,74.857,2),('Srinagar','North','Jammu and Kashmir',34.084,74.797,2),('Dehradun','North','Uttarakhand',30.316,78.032,2),('Shimla','North','Himachal Pradesh',31.105,77.173,2),
 ('Surat','West','Gujarat',21.170,72.831,2),('Vadodara','West','Gujarat',22.307,73.181,2),('Rajkot','West','Gujarat',22.303,70.802,2),('Nashik','West','Maharashtra',19.997,73.790,2),('Nagpur','Central','Maharashtra',21.146,79.088,2),('Chhatrapati Sambhajinagar','West','Maharashtra',19.877,75.343,2),('Panaji','West','Goa',15.491,73.828,2),('Indore','Central','Madhya Pradesh',22.720,75.858,2),('Bhopal','Central','Madhya Pradesh',23.260,77.413,2),('Raipur','Central','Chhattisgarh',21.252,81.630,2),('Gwalior','Central','Madhya Pradesh',26.218,78.182,2),('Jabalpur','Central','Madhya Pradesh',23.181,79.987,2),
 ('Patna','East','Bihar',25.594,85.138,2),('Ranchi','East','Jharkhand',23.344,85.310,2),('Jamshedpur','East','Jharkhand',22.805,86.203,2),('Bhubaneswar','East','Odisha',20.296,85.825,2),('Cuttack','East','Odisha',20.463,85.883,2),('Siliguri','East','West Bengal',26.727,88.395,2),
 ('Kochi','South','Kerala',9.931,76.267,2),('Thiruvananthapuram','South','Kerala',8.524,76.936,2),('Kozhikode','South','Kerala',11.259,75.780,2),('Coimbatore','South','Tamil Nadu',11.017,76.956,2),('Madurai','South','Tamil Nadu',9.925,78.120,2),('Mysuru','South','Karnataka',12.296,76.639,2),('Mangaluru','South','Karnataka',12.915,74.856,2),('Visakhapatnam','South','Andhra Pradesh',17.687,83.219,2),('Vijayawada','South','Andhra Pradesh',16.507,80.648,2),('Tiruchirappalli','South','Tamil Nadu',10.791,78.705,2),('Puducherry','South','Puducherry',11.942,79.809,2),('Port Blair','South','Andaman and Nicobar Islands',11.623,92.726,2),
 ('Guwahati','Northeast','Assam',26.145,91.736,2),('Shillong','Northeast','Meghalaya',25.579,91.893,2),('Agartala','Northeast','Tripura',23.831,91.287,2),('Imphal','Northeast','Manipur',24.817,93.937,2),('Aizawl','Northeast','Mizoram',23.727,92.718,2),('Kohima','Northeast','Nagaland',25.675,94.108,2),('Gangtok','Northeast','Sikkim',27.339,88.607,2),('Itanagar','Northeast','Arunachal Pradesh',27.084,93.605,2)]
CITIES=pd.DataFrame(CITY_ROWS,columns=['city','zone','state','latitude','longitude','tier']);CITIES['tier']='Tier-'+CITIES.tier.astype(str)
PLANS=['Prepaid','Postpaid','Home broadband','Enterprise']

def build_data(root,pii_key=None,smoke=False):
 root=Path(root);root.mkdir(parents=True,exist_ok=True);rng=np.random.default_rng(SEED)
 n=3000 if smoke else max(3000,min(200000,int(os.getenv('TELECOM_SAMPLE_SIZE','30000'))));ci=rng.integers(0,len(CITIES),n);customers=CITIES.iloc[ci][['city','zone','tier']].reset_index(drop=True)
 customers['customer_id']=[f'SUB-{i:07d}' for i in range(n)];customers['tenant']='telecom-demo';customers['plan']=rng.choice(PLANS,n,p=[.55,.25,.15,.05])
 customers['feature_date']=pd.to_datetime(rng.choice(pd.date_range('2025-10-01','2026-09-30'),n));customers=customers.sort_values(['feature_date','customer_id']).reset_index(drop=True)
 customers['tenure_months']=rng.integers(1,120,n);customers['bill_inr']=rng.lognormal(5.9,.5,n).round(2);customers['usage_change_pct']=rng.normal(0,22,n).round(2)
 customers['complaints_90d']=rng.poisson(.7,n);customers['drop_rate_pct']=rng.uniform(.1,3.5,n).round(3);customers['autopay']=rng.integers(0,2,n)
 p=1/(1+np.exp(-(-3.7+.55*customers.complaints_90d-.027*customers.usage_change_pct+.3*customers.drop_rate_pct-.012*customers.tenure_months-.35*customers.autopay)))
 customers['churn_next_30d']=rng.binomial(1,p);customers['label_matures_at']=customers.feature_date+pd.Timedelta(days=30)
 key=pii_key or Fernet.generate_key();key=key.encode() if isinstance(key,str) else key;cipher=Fernet(key)
 # Fictional non-deliverable contacts; no real phone numbers, SIM identifiers, Aadhaar or CDRs.
 pii=pd.DataFrame({'customer_id':customers.customer_id,'city':customers.city,'tenant':'telecom-demo','ciphertext':[cipher.encrypt(json.dumps({'name':f'Demo subscriber {i:07d}','email':f'subscriber{i:07d}@example.invalid','phone':f'SIMULATED-{i:07d}'}).encode()).decode() for i in range(n)]})
 days=90 if smoke else 365;network=[];monthly=[];revenue=[];spectrum=[]
 all_days=pd.date_range(AS_OF-pd.Timedelta(days=days),AS_OF-pd.Timedelta(days=1));months=pd.date_range('2023-11-01','2026-10-01',freq='MS')
 for j,c in CITIES.iterrows():
  base=int(rng.integers(200000,1200000) if c.tier=='Tier-1' else rng.integers(35000,200000));sites=int(base/900)+20
  for k,month in enumerate(months):
   opening=int(base*(1+.004*k));lost=int(opening*rng.uniform(.009,.038));adds=int(lost*rng.uniform(.8,1.7));closing=opening+adds-lost;avg=(opening+closing)/2;arpu=260+18*np.sin(k*2*np.pi/12)+j*.7+k*1.4
   monthly.append({'tenant':'telecom-demo','city':c.city,'zone':c.zone,'tier':c.tier,'month':month,'opening_subscribers':opening,'gross_adds':adds,'churned_subscribers':lost,'closing_subscribers':closing,'average_subscribers':avg,'billed_service_revenue_inr':round(avg*arpu*rng.uniform(.97,1.03),2),'complaints_received':int(avg*rng.uniform(.001,.004))})
  latest=monthly[-1]
  for di,day in enumerate(all_days):
   season=1+.1*np.sin(di*2*np.pi/7);fault=(j%11==0 and day>=AS_OF-pd.Timedelta(days=10))
   revenue.append({'tenant':'telecom-demo','city':c.city,'zone':c.zone,'tier':c.tier,'date':day,'billed_service_revenue_inr':round(latest['billed_service_revenue_inr']/30*season*rng.uniform(.94,1.06),2)})
   for tech in ['4G','5G']:
    attempts=int(base*.07*season*rng.uniform(.85,1.15));setup=int(attempts*rng.uniform(.98,.999));drop_p=rng.uniform(.002,.011)+(.022 if fault else 0);dropped=int(setup*drop_p)
    eligible=sites*1440;unavailable=eligible*rng.uniform(.0001,.004)+ (eligible*.018 if fault else 0);handover=attempts//3;prb= min(99,float(rng.normal(62 if tech=='4G' else 48,8)+(29 if fault else 0)))
    dlsec=int(attempts*2);mbit=float(dlsec*rng.uniform(18,45)*(3 if tech=='5G' else 1));samples=attempts;lat=float(rng.uniform(12,30)*(1.8 if fault else 1))
    network.append({'tenant':'telecom-demo','city':c.city,'zone':c.zone,'tier':c.tier,'date':day,'technology':tech,'site_count':sites,'eligible_site_minutes':eligible,'unavailable_site_minutes':round(unavailable,2),'call_attempts':attempts,'call_setup_successes':setup,'connected_calls':setup,'dropped_calls':dropped,'handover_attempts':handover,'handover_successes':int(handover*rng.uniform(.965,.999)),'latency_sum_ms':lat*samples,'latency_samples':samples,'downloaded_mbit':mbit,'dl_active_seconds':dlsec,'prb_used_units':prb*sites,'prb_capacity_units':100*sites,'data_gb':mbit/8000,'packet_sent':attempts*100,'packet_lost':int(attempts*100*rng.uniform(.0001,.012))})
  for band,mhz in [('700 MHz',10),('1800 MHz',20),('3300 MHz',80)]:spectrum.append({'city':c.city,'zone':c.zone,'tier':c.tier,'band_label':band,'planning_bandwidth_mhz':mhz,'holding_status':'Synthetic planning register — not a frequency assignment','source':'SYN-SPECTRUM'})
 network=pd.DataFrame(network);monthly=pd.DataFrame(monthly);revenue=pd.DataFrame(revenue)
 ids=rng.choice(customers.customer_id,2400 if smoke else 10000);tickets=pd.DataFrame({'ticket_id':[f'TKT-{i:07d}' for i in range(len(ids))],'customer_id':ids,'opened_at':AS_OF-pd.to_timedelta(rng.integers(1,90,len(ids)),unit='D'),'status':rng.choice(['Open','Resolved'],len(ids),p=[.25,.75]),'category':rng.choice(['Network','Billing','Provisioning','Service'],len(ids)),'internal_sla_hours':48,'resolution_hours':rng.uniform(1,120,len(ids)).round(1),'first_contact_resolution':rng.integers(0,2,len(ids))})
 tickets=tickets.merge(customers[['customer_id','tenant','city','zone','tier']],on='customer_id',validate='many_to_one');tickets['age_hours']=(AS_OF-tickets.opened_at).dt.total_seconds()/3600
 surveys=pd.DataFrame({'customer_id':rng.choice(customers.customer_id,1500 if smoke else 6000),'nps_score':rng.integers(0,11,1500 if smoke else 6000),'csat_score':rng.integers(1,6,1500 if smoke else 6000)}).merge(customers[['customer_id','tenant','city','zone','tier']],on='customer_id',validate='many_to_one')
 quality=[{'check':'Unique sample subscriber IDs','passed':int(customers.customer_id.nunique()),'total':len(customers)}, {'check':'All churn labels mature by snapshot','passed':int(customers.label_matures_at.le(AS_OF).sum()),'total':len(customers)}, {'check':'Call counter validity','passed':int((network.dropped_calls.le(network.connected_calls)&network.call_setup_successes.le(network.call_attempts)).sum()),'total':len(network)}, {'check':'Subscriber reconciliation','passed':int((monthly.opening_subscribers+monthly.gross_adds-monthly.churned_subscribers).eq(monthly.closing_subscribers).sum()),'total':len(monthly)}]
 return {'cities':CITIES.copy(),'customers':customers,'pii':pii,'network':network,'monthly':monthly,'daily_revenue':revenue,'tickets':tickets,'surveys':surveys,'spectrum':pd.DataFrame(spectrum),'quality':quality,'pii_key':key}

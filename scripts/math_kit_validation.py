#!/usr/bin/env python3
"""Score every betting_math.py tool on real closing prices (tennis ML 2014-25, football 1X2 2022-26)."""
import glob, sys, json
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
import betting_math as bm

def football():
    fr=[]
    for f in glob.glob('/tmp/kg/ext/fd/*.csv'):
        d=pd.read_csv(f, encoding='latin1', on_bad_lines='skip'); d['file']=Path(f).name; fr.append(d)
    d=pd.concat(fr, ignore_index=True)
    out={}
    for book,cols in {"Pinnacle close":("PSCH","PSCD","PSCA"),"Bet365 close":("B365CH","B365CD","B365CA"),"Avg close":("AvgCH","AvgCD","AvgCA")}.items():
        if not all(c in d for c in cols): continue
        x=d.dropna(subset=list(cols)+['FTR']); x=x[(x[list(cols)]>1).all(axis=1)]
        idx=x.FTR.map({'H':0,'D':1,'A':2}).values; O=x[list(cols)].values
        res={}
        for name,fn in bm.DEVIG.items():
            P=np.array([fn(o) for o in O]); res[name]={"logloss":bm.multiclass_log_loss(P,idx),"rps":bm.rps(P,idx)}
        res["_n"]=len(x); res["_mean_overround_%"]=float(np.mean([bm.overround(o) for o in O])*100)
        out[book]=res
    return out, d

def tennis():
    d=pd.read_csv('/tmp/kg/tennis_odds/tennis_matches_2014_2025.csv', low_memory=False,
                  usecols=['tour','tournament_year','match_format','completed','bet365_odds_a','bet365_odds_b','Betfair_odds_a','Betfair_odds_b','Ladbrokes_odds_a','Ladbrokes_odds_b','Unibet_odds_a','Unibet_odds_b','best_odds_a','best_odds_b'])
    d=d[d.completed==1]; out={}
    for book,(a,b) in {"bet365":("bet365_odds_a","bet365_odds_b"),"Betfair":("Betfair_odds_a","Betfair_odds_b"),"best-of-books":("best_odds_a","best_odds_b")}.items():
        x=d.dropna(subset=[a,b]); x=x[(x[a]>1)&(x[b]>1)]; O=x[[a,b]].values   # player_a is the winner
        res={}
        for name,fn in bm.DEVIG.items():
            P=np.array([fn(o) for o in O[:60000]]); res[name]={"logloss":float(-np.mean(np.log(P[:,0])))}   # winner always idx 0
        res["_n"]=min(len(x),60000); res["_mean_overround_%"]=float(np.mean(1/O[:,0]+1/O[:,1]-1)*100); out[book]=res
    return out

def calib(d):
    x=d.dropna(subset=['PSCH','PSCD','PSCA','FTR']); x=x[(x[['PSCH','PSCD','PSCA']]>1).all(axis=1)]
    x=x.assign(dt=pd.to_datetime(x.Date,dayfirst=True,errors='coerce')).sort_values('dt')
    P=np.array([bm.devig_shin(o) for o in x[['PSCH','PSCD','PSCA']].values]); y=(x.FTR.values=='H').astype(float); ph=P[:,0]
    cut=int(len(x)*.6); tr,te=slice(0,cut),slice(cut,None); res={}
    res["raw Shin home-win"]={"logloss":bm.log_loss(ph[te],y[te]),"brier":bm.brier(ph[te],y[te])}
    for nm,cls in {"isotonic":bm.Isotonic,"beta":bm.BetaCalibration,"platt":bm.Platt}.items():
        m=cls().fit(ph[tr],y[tr]); q=m.predict(ph[te]); res[nm]={"logloss":bm.log_loss(q,y[te]),"brier":bm.brier(q,y[te])}
    res["_n_train/test"]=(cut,len(x)-cut); return res

if __name__=="__main__":
    f,d=football(); print("== FOOTBALL 1X2 closing: lower is better =="); print(json.dumps(f,indent=1))
    print("== TENNIS ML closing (winner log-loss) =="); print(json.dumps(tennis(),indent=1))
    print("== CALIBRATION of Pinnacle-Shin home-win prob, out-of-sample =="); print(json.dumps(calib(d),indent=1,default=str))

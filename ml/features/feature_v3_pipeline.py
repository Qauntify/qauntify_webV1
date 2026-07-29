"""Causal M5/M15 feature_v3 pipeline; offline only."""
from __future__ import annotations
import hashlib, json, shutil
from pathlib import Path
import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, SMAIndicator, MACD, ADXIndicator
from ta.volatility import AverageTrueRange, BollingerBands
from ml.outcomes.label_v3 import load_m5_csv, file_sha256

VERSION="feature_v3"

def _indicators(f, prefix=""):
    out=pd.DataFrame(index=f.index); c,h,l,o=f.close,f.high,f.low,f.open
    atrs={p:AverageTrueRange(h,l,c,p,fillna=False).average_true_range().replace(0,np.nan) for p in (7,14,21)}
    for p,a in atrs.items(): out[f"{prefix}atr_{p}"]=a
    for p in (9,20,21,50,100,200):
        e=EMAIndicator(c,p,fillna=False).ema_indicator();out[f"{prefix}ema_{p}"]=e;out[f"{prefix}close_ema_{p}_atr"]=(c-e)/atrs[14];out[f"{prefix}ema_{p}_slope3_atr"]=(e-e.shift(3))/atrs[14]
    ep=(9,20,21,50,100,200)
    for a,b in zip(ep,ep[1:]):out[f"{prefix}ema_{a}_{b}_gap_atr"]=(out[f"{prefix}ema_{a}"]-out[f"{prefix}ema_{b}"])/atrs[14]
    out[f"{prefix}ema_bull_order"]=(pd.concat([out[f"{prefix}ema_{p}"] for p in ep],axis=1).diff(axis=1).iloc[:,1:]<0).all(axis=1).astype('int8')
    out[f"{prefix}ema_bear_order"]=(pd.concat([out[f"{prefix}ema_{p}"] for p in ep],axis=1).diff(axis=1).iloc[:,1:]>0).all(axis=1).astype('int8')
    for p in (10,20,50,100,200): out[f"{prefix}sma_{p}"]=SMAIndicator(c,p,fillna=False).sma_indicator()
    for p in (7,14,21):
        r=RSIIndicator(c,p,fillna=False).rsi();out[f"{prefix}rsi_{p}"]=r;out[f"{prefix}rsi_{p}_chg1"]=r.diff();out[f"{prefix}rsi_{p}_chg3"]=r.diff(3)
    mac=MACD(c,26,12,9,fillna=False);out[f"{prefix}macd"]=mac.macd();out[f"{prefix}macd_signal"]=mac.macd_signal();out[f"{prefix}macd_hist"]=mac.macd_diff()
    adx=ADXIndicator(h,l,c,14,fillna=False);out[f"{prefix}adx_14"]=adx.adx();out[f"{prefix}di_plus_14"]=adx.adx_pos();out[f"{prefix}di_minus_14"]=adx.adx_neg()
    bb=BollingerBands(c,20,2,fillna=False);up,mid,lo=bb.bollinger_hband(),bb.bollinger_mavg(),bb.bollinger_lband();out[f"{prefix}bb_width"]=(up-lo)/mid;out[f"{prefix}bb_position"]=(c-lo)/(up-lo)
    out[f"{prefix}close_above_upper"]=(c>up).astype('int8');out[f"{prefix}close_below_lower"]=(c<lo).astype('int8');out[f"{prefix}close_above_middle"]=(c>mid).astype('int8');out[f"{prefix}close_below_middle"]=(c<mid).astype('int8');out[f"{prefix}ema9_above_middle"]=(out[f"{prefix}ema_9"]>mid).astype('int8');out[f"{prefix}ema9_below_middle"]=(out[f"{prefix}ema_9"]<mid).astype('int8');out[f"{prefix}bullish_reentry"]=((c.shift(1)>up.shift(1))&(c<=up)).astype('int8');out[f"{prefix}bearish_reentry"]=((c.shift(1)<lo.shift(1))&(c>=lo)).astype('int8')
    rng=(h-l).replace(0,np.nan);out[f"{prefix}range_atr"]=(h-l)/atrs[14];out[f"{prefix}body_atr"]=(c-o)/atrs[14];out[f"{prefix}body_ratio"]=(c-o).abs()/rng;out[f"{prefix}upper_wick_ratio"]=(h-pd.concat([o,c],axis=1).max(axis=1))/rng;out[f"{prefix}lower_wick_ratio"]=(pd.concat([o,c],axis=1).min(axis=1)-l)/rng;out[f"{prefix}close_position"]=(c-l)/rng
    for p in (1,3,6,12): out[f"{prefix}log_return_{p}"]=np.log(c/c.shift(p))
    lr=np.log(c/c.shift(1));out[f"{prefix}realised_vol_12"]=lr.rolling(12).std(ddof=0);out[f"{prefix}realised_vol_48"]=lr.rolling(48).std(ddof=0)
    return out.replace([np.inf,-np.inf],np.nan)

def build(m5,m15):
    x=_indicators(m5); decision=m5.timestamp+pd.Timedelta(minutes=5);x.insert(0,"decision_timestamp",decision);x.insert(0,"candidate_id",[hashlib.sha256(f"XAUUSD|M5|{v.isoformat()}|label_v3_1".encode()).hexdigest() for v in decision])
    ctx=_indicators(m15,"m15_");keep=['m15_ema_20','m15_ema_50','m15_ema_200','m15_rsi_14','m15_atr_14','m15_adx_14','m15_di_plus_14','m15_di_minus_14','m15_bb_width','m15_bb_position'];ctx=ctx[keep];ctx["m15_available_time"]=m15.timestamp+pd.Timedelta(minutes=15);ctx["m15_age_minutes"]=0.0
    x=pd.merge_asof(x.sort_values("decision_timestamp"),ctx.sort_values("m15_available_time"),left_on="decision_timestamp",right_on="m15_available_time",direction="backward",allow_exact_matches=True)
    x["m15_age_minutes"]=(x.decision_timestamp-x.m15_available_time).dt.total_seconds()/60
    feature_cols=[c for c in x if c not in {"candidate_id","decision_timestamp","m15_available_time"}];x["feature_eligible"]=x[feature_cols].notna().all(axis=1);x["decision_year"]=x.decision_timestamp.dt.year.astype("int16");return x

def export(frame,root,overwrite=False):
    if root.exists():
        if not overwrite: raise FileExistsError(root)
        shutil.rmtree(root)
    (root/"dataset").mkdir(parents=True)
    for y,g in frame.groupby("decision_year",sort=True):
        d=root/"dataset"/f"decision_year={int(y)}";d.mkdir();g.drop(columns=['decision_year']).to_parquet(d/"part-000.parquet",index=False,compression="zstd")
    files=sorted((root/"dataset").rglob("*.parquet"));checks={str(p.relative_to(root)):file_sha256(p) for p in files};manifest={"version":VERSION,"rows":len(frame),"unique_candidate_ids":int(frame.candidate_id.nunique()),"eligible_rows":int(frame.feature_eligible.sum()),"feature_columns":[c for c in frame if c not in {"candidate_id","decision_timestamp","m15_available_time","decision_year","feature_eligible"}],"file_checksums":checks};manifest["dataset_checksum"]=hashlib.sha256(json.dumps(checks,sort_keys=True).encode()).hexdigest().upper();(root/"feature_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n","utf8");return manifest

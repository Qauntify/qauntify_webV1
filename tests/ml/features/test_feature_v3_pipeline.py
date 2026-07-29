import pandas as pd
from ml.features.feature_v3_pipeline import build

def _bars(freq, n=300):
    t=pd.date_range('2024-01-01',periods=n,freq=freq);v=pd.Series(range(n),dtype=float)*.01+100
    return pd.DataFrame({'timestamp':t,'open':v,'high':v+.2,'low':v-.2,'close':v+.05,'volume':1})

def test_future_mutation_does_not_change_past_features():
    m5,m15=_bars('5min'),_bars('15min');a=build(m5,m15);m5.loc[250:,['open','high','low','close']]+=50;b=build(m5,m15)
    pd.testing.assert_frame_equal(a.iloc[:240],b.iloc[:240])

def test_m15_context_is_closed_and_age_is_bounded():
    x=build(_bars('5min'),_bars('15min'))
    valid=x.m15_available_time.notna()
    assert (x.loc[valid,'m15_available_time']<=x.loc[valid,'decision_timestamp']).all()
    assert x.m15_age_minutes.dropna().between(0,10).all()

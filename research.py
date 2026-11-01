"""Exploratory analysis helpers. Not causal inference or validated risk assessment."""
import numpy as np
import pandas as pd
from .scoring import Weights, score_records


def weight_sensitivity(df, steps=11):
    """Recompute cohort mean under every simplex-grid weighting combination."""
    rows = []
    for a in range(steps):
        for h in range(steps-a):
            c = steps-1-a-h
            w = Weights(a/(steps-1), h/(steps-1), c/(steps-1))
            result = score_records(df, w)
            rows.append({'weight_amplification':w.amplification,'weight_health':w.health_risk,
                         'weight_credibility_gap':w.credibility_gap,'mean_emnri':result.emnri.mean()})
    return pd.DataFrame(rows)


def narrative_shift(df, event_date, window_days=14):
    """Unadjusted before/after difference in political framing; descriptive only."""
    tmp=df.copy()
    tmp['date']=pd.to_datetime(tmp['date'], errors='coerce', utc=True)
    event=pd.to_datetime(event_date,utc=True)
    before=tmp.loc[(tmp.date >= event-pd.Timedelta(days=window_days)) & (tmp.date < event),'political_framing'].dropna()
    after=tmp.loc[(tmp.date >= event) & (tmp.date < event+pd.Timedelta(days=window_days)),'political_framing'].dropna()
    return {'before_n':len(before),'after_n':len(after),'before_mean':float(before.mean()) if len(before) else np.nan,
            'after_mean':float(after.mean()) if len(after) else np.nan,
            'pnsi':float(after.mean()-before.mean()) if len(before) and len(after) else np.nan}


def annotation_agreement(df):
    """Cohen's kappa for two independently supplied categorical annotations."""
    if not {'annotator_1','annotator_2'}.issubset(df):
        return None
    pair=df[['annotator_1','annotator_2']].dropna()
    if len(pair)<2:
        return None
    from sklearn.metrics import cohen_kappa_score
    return float(cohen_kappa_score(pair.annotator_1.astype(str),pair.annotator_2.astype(str)))

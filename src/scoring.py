"""Transparent exploratory communication risk scoring. Not a validated clinical index."""
from dataclasses import dataclass
import numpy as np
import pandas as pd

FIELDS = ['claim_reliability','amplification','health_risk','communication_credibility','political_framing']

@dataclass(frozen=True)
class Weights:
    amplification: float = 1/3
    health_risk: float = 1/3
    credibility_gap: float = 1/3

    def validate(self):
        vals = [self.amplification, self.health_risk, self.credibility_gap]
        if any(not np.isfinite(x) or x < 0 for x in vals) or not np.isclose(sum(vals), 1):
            raise ValueError('Weights must be nonnegative and sum to one')

def score_records(df: pd.DataFrame, weights: Weights = Weights()) -> pd.DataFrame:
    weights.validate()
    missing = set(FIELDS) - set(df.columns)
    if missing:
        raise ValueError(f'Missing required columns: {sorted(missing)}')
    result = df.copy()
    for col in FIELDS:
        result[col] = pd.to_numeric(result[col], errors='coerce')
        if result[col].isna().any() or (~result[col].between(0, 1)).any():
            raise ValueError(f'{col} must contain numeric values from 0 to 1 with no missing entries')
    result['emnri'] = 100 * (1-result['claim_reliability']) * (
        weights.amplification*result['amplification'] +
        weights.health_risk*result['health_risk'] +
        weights.credibility_gap*(1-result['communication_credibility'])
    )
    return result

def bootstrap_mean_ci(values, iterations=1000, seed=42):
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if not len(x):
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    samples = rng.choice(x, size=(iterations,len(x)), replace=True).mean(axis=1)
    return tuple(np.percentile(samples, [2.5,97.5]))

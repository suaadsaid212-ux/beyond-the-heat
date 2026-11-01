import pandas as pd
import pytest
from src.scoring import score_records, Weights

def test_score_and_political_independence():
    df=pd.DataFrame({'claim_reliability':[0.3,0.3],'amplification':[0.8,0.8],
      'health_risk':[0.7,0.7],'communication_credibility':[0.4,0.4],
      'political_framing':[0.,1.]})
    out=score_records(df)
    assert abs(out.emnri.iloc[0]-49)<1e-9
    assert out.emnri.iloc[0]==out.emnri.iloc[1]

def test_invalid_range_rejected():
    df=pd.DataFrame({k:[0.5] for k in ['claim_reliability','amplification','health_risk','communication_credibility','political_framing']})
    df.loc[0,'amplification']=1.5
    with pytest.raises(ValueError):score_records(df)

def test_weights_validation():
    with pytest.raises(ValueError):Weights(.5,.5,.5).validate()


def test_weight_sensitivity():
    import pandas as pd
    from src.research import weight_sensitivity
    frame=pd.DataFrame({'claim_reliability':[0.2], 'amplification':[0.8], 'health_risk':[0.6], 'communication_credibility':[0.5], 'political_framing':[0.9]})
    result=weight_sensitivity(frame)
    assert len(result)==66
    assert result['mean_emnri'].between(0,100).all()


def test_narrative_shift():
    import pandas as pd
    from src.research import narrative_shift
    frame=pd.DataFrame({'date':['2026-07-01','2026-07-03'], 'political_framing':[0.2,0.8]})
    result=narrative_shift(frame,'2026-07-02',3)
    assert abs(result['pnsi']-0.6)<1e-10


def test_sensitivity_accepts_already_scored_dashboard_data():
    from src.research import weight_sensitivity
    frame=pd.DataFrame({'claim_reliability':[0.2,0.4], 'amplification':[0.8,0.5],
        'health_risk':[0.6,0.3], 'communication_credibility':[0.5,0.7],
        'political_framing':[0.9,0.1]})
    scored=score_records(frame)
    rescored=score_records(scored,Weights(1,0,0))
    assert rescored.columns.is_unique
    assert list(rescored.emnri)==pytest.approx([64,30])
    result=weight_sensitivity(scored)
    assert len(result)==66
    assert pd.api.types.is_numeric_dtype(result.mean_emnri)
    assert float(result.mean_emnri.min())>=0


def test_annotation_agreement_with_supplied_ratings():
    from src.research import annotation_agreement
    frame=pd.DataFrame({'annotator_1':['true','false','true','false'],
                        'annotator_2':['true','false','true','false']})
    assert annotation_agreement(frame)==pytest.approx(1.0)

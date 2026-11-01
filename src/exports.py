"""Research exports: workbook and publication-ready PNG figures."""
from io import BytesIO
import pandas as pd


def excel_bytes(scored, weights, sensitivity=None, provenance=None):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter', engine_kwargs={
            'options': {'strings_to_formulas': False, 'strings_to_urls': False}}) as writer:
        scored.to_excel(writer, sheet_name='Scored data', index=False)
        summary = pd.DataFrame([
            ['Records', len(scored)],
            ['Mean EMNRI', float(scored['emnri'].mean())],
            ['Mean political framing', float(scored['political_framing'].mean())],
            ['Amplification weight', weights.amplification],
            ['Health risk weight', weights.health_risk],
            ['Credibility weight', weights.credibility_gap],
        ], columns=['Metric', 'Value'])
        summary.to_excel(writer, sheet_name='Summary and weights', index=False)
        method = pd.DataFrame({'Methodology and limitations': [
            'EMNRI = 100 * (1 - claim_reliability) * (wA * amplification + wH * health_risk + wC * (1 - communication_credibility))',
            'Political framing is separate and does not affect EMNRI.',
            'Input indicators require independent measurement and validation.',
            'Demo data are synthetic. These scores are not verified scientific findings.',
            'A political event coinciding with a trend does not prove causation.',
        ]})
        method.to_excel(writer, sheet_name='Methodology', index=False)
        if sensitivity is not None:
            sensitivity.to_excel(writer, sheet_name='Weight sensitivity', index=False)
        if provenance is not None:
            pd.DataFrame([provenance]).to_excel(writer, sheet_name='Provenance', index=False)
        for name in writer.sheets:
            ws=writer.sheets[name]
            ws.freeze_panes(1,0)
            ws.set_row(0, 27, writer.book.add_format({'bold':True,'bg_color':'#153B51','font_color':'#FFFFFF'}))
            ws.set_column(0,0,25)
            ws.set_column(1,18,21)
            if name == 'Scored data':
                ws.autofilter(0,0,len(scored),len(scored.columns)-1)
            if name == 'Methodology':
                ws.set_column(0,0,110)
    return output.getvalue()


def figure_png(fig, scale=2):
    """Return PNG bytes. Requires kaleido and a compatible Chrome runtime."""
    return fig.to_image(format='png', scale=scale)

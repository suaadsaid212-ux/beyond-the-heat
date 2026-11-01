"""Animated climate-inspired UI, respecting reduced-motion preferences."""
import streamlit as st


def apply_theme():
    st.markdown('''<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
    html, body, [class*="css"], [data-testid="stApp"] {font-family: 'DM Sans', sans-serif;}
    [data-testid="stAppViewContainer"] {
      background: radial-gradient(ellipse at 85% 10%, rgba(88,177,202,.24), transparent 38%),
                  radial-gradient(ellipse at 8% 55%, rgba(116,179,140,.17), transparent 42%),
                  linear-gradient(135deg,#f2fafb,#eaf3f7,#f6fbf8,#e8f4f9);
      background-size: 170% 170%; animation: climateShift 22s ease-in-out infinite alternate;
    }
    @keyframes climateShift {0%{background-position:0% 20%}100%{background-position:100% 80%}}
    [data-testid="stSidebar"] {background:rgba(231,243,247,.95);}
    [data-testid="stMetric"] {background:rgba(255,255,255,.78);border:1px solid rgba(33,110,131,.13);border-radius:16px;padding:16px;box-shadow:0 5px 22px rgba(29,83,106,.07)}
    div[data-testid="stPlotlyChart"] {background:rgba(255,255,255,.65);border:1px solid rgba(33,110,131,.10);border-radius:18px;padding:8px}
    .climate-hero {position:relative;overflow:hidden;border-radius:24px;padding:30px 32px;margin:8px 0 24px;color:white;background:linear-gradient(110deg,#0c394e,#156b80,#3e8d79);box-shadow:0 14px 36px rgba(19,77,99,.18)}
    .climate-hero h1 {color:white;font-size:2.35rem;line-height:1.2;margin:0 0 8px;font-weight:700}
    .climate-hero p {color:#e5f6f6;margin:0;max-width:720px}
    .climate-orb {position:absolute;right:-55px;top:-95px;width:330px;height:330px;border-radius:50%;background:radial-gradient(circle at 35% 35%,#f7d989,#e9a65e 42%,rgba(237,147,65,.05) 69%);opacity:.64;animation:orbFloat 12s ease-in-out infinite alternate;pointer-events:none}
    @keyframes orbFloat {from{transform:translate(0,0) scale(.94)}to{transform:translate(-28px,32px) scale(1.07)}}
    @media (prefers-reduced-motion:reduce) {[data-testid="stAppViewContainer"],.climate-orb{animation:none!important}}
    @media (max-width:700px) {.climate-hero{padding:22px}.climate-hero h1{font-size:1.7rem}.climate-orb{opacity:.24}}
    </style>''', unsafe_allow_html=True)


def hero(title, subtitle):
    import html
    st.markdown(f'<div class="climate-hero"><div class="climate-orb"></div><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>',unsafe_allow_html=True)

"""Five light themes, selected per session; semantic status colors stay stable."""
import streamlit as st

THEMES = {
    '山野青绿': ('#edf5ef','#dcece0','#14532d','#267562','radial-gradient(ellipse at 90% 0%,#cde5d8 0,transparent 48%)'),
    '晴空蓝白': ('#eef5fc','#deebf7','#153e64','#246394','radial-gradient(ellipse at 5% 5%,#c8e1f8 0,transparent 50%)'),
    '暖杏纸笺': ('#fbf4e9','#f1e5d3','#62421e','#895923','repeating-linear-gradient(0deg,transparent,transparent 31px,#bda17a15 32px)'),
    '薰衣草紫': ('#f5f0fb','#e9e0f3','#4d326c','#725091','radial-gradient(ellipse at 90% 5%,#e3d5f2 0,transparent 50%)'),
    '极简灰白': ('#f4f5f7','#e7e9ed','#273447','#48566c','linear-gradient(145deg,#ffffff80,transparent)'),
}


def theme_css(name):
    bg, side, ink, accent, pattern = THEMES.get(name, THEMES['山野青绿'])
    return f'''<style>
    :root{{--qp-ink:{ink};--qp-brand:{accent};--qp-line:{side};}}
    .stApp{{background-color:{bg};background-image:{pattern};background-attachment:fixed;}}
    [data-testid="stHeader"]{{background:transparent;}}
    [data-testid="stSidebar"]{{background:{side};}}
    .qp-hero{{background:linear-gradient(120deg,{ink},{accent});}}
    h1,h2,h3{{color:{ink};}}
    button[kind="primary"],button[data-testid="stBaseButton-primary"]{{background:{accent};border-color:{accent};color:white;}}
    [role="tab"][aria-selected="true"]{{color:{ink};background:{side};}}
    .qp-content-card,.qp-empty,[data-testid="stForm"],[data-testid="stExpander"],[data-testid="stMetric"]{{background:#ffffffed;}}
    .qp-learn-flow{{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0;}}
    .qp-learn-node{{flex:1 1 150px;padding:18px;border-radius:14px;background:white;border:1px solid {side};color:{ink};}}
    .qp-learn-node strong{{display:block;font-size:17px;margin-bottom:8px;}}
    .qp-zone{{padding:12px 0 4px;border-bottom:1px solid {side};margin:14px 0;}}
    </style>'''


def apply_background():
    st.markdown(theme_css(st.session_state.get('background_style','山野青绿')), unsafe_allow_html=True)

"""Shared visual layout, module instructions and rerun-safe navigation."""
from html import escape
import streamlit as st

MODULES = {
    '产品资料': {'number': '01', 'tag': '资料整理', 'summary': '把分散的产品资料，整理成有来源的候选信息。',
        'steps': [('准备资料', '可上传CSV，也可在公开食品资料页输入条码或名称。'), ('预览并导入', '核对商品身份与字段，点击确认导入才会保存为候选。'), ('前往核对', '选择SKU与版本，到数据核对页决定采用哪些信息。')],
        'tips': ['第一次体验先上传01_首次导入.csv；生成并审核两份内容后，再上传02调价文件。', '上传只是保存证据，不代表事实已确认。价格按元填写，例如12.00。', '新包装用新版本；同版本纠错或调价用新来源候选。']},
    '数据核对': {'number': '02', 'tag': '人工确认', 'summary': '并列核对证据，让每一项产品事实都有明确依据。',
        'steps': [('先看冲突', '先处理不同值的候选，200g与0.2kg属于等价表述。'), ('记录取舍', '排除误录后，选择要采用的候选并填写核对依据。'), ('确认后生成', '名称和净含量确认齐全后，就能去生成内容。')],
        'tips': ['拟制样例的250g是误录：先排除它，再确认200g。实际资料以你的核查为准。', '确认时需填写侧栏操作人和本次依据，不按文件上传时间自动选值。', '调价时采纳新价格即可，旧确认值会保留为历史。']},
    '内容工作台': {'number': '03', 'tag': '内容协同', 'summary': '用确认资料组织文案，经过审核后再用于对外发布。',
        'steps': [('选择生成依据', '选内容类型和价格渠道，右侧核对本次资料。'), ('生成并核对', '模板无需密钥；双模型模式需本机配置，均要人工核对。'), ('审核与下载', '在审核与导出中提交审核，通过后下载TXT。')],
        'tips': ['希望体验调价追踪，请勾选加入价格，并保持零售渠道一致。', '手动编辑会产生新修订；名称、净含量、金额明显不一致时会拦截审核与导出。', '规则无法理解全部文字含义，配料、功效等仍需逐句人工核对。']},
    '变更追踪': {'number': '04', 'tag': '更新维护', 'summary': '资料变了，找到需要复查的文案，让更新有始有终。',
        'steps': [('查看变化', '核对变化字段、原依据、新依据和关联文案。'), ('更新正文', '按当前资料生成新修订，或手动修改并重绑依据。'), ('完成重审', '回到内容工作台审核新修订，再替换外部旧内容。')],
        'tips': ['这里只追踪系统里保存的内容，提醒按整份输入依据计算。', '旧正文含12元、新资料为14元时，应先改正文，不能直接沿用旧价。', '最新修订审核通过后显示本次已处理；旧修订保留在历史，不会自动替换外部发布。']},
}


def navigate(page):
    st.session_state['pending_navigation'] = page


def next_button(label, page, key):
    st.button(label, key=key, on_click=navigate, args=(page,), icon=':material/arrow_forward:', width='stretch')


def apply_theme():
    st.markdown('''<style>
    .stApp {background: #f7f8f3;}
    .block-container {max-width: 1180px; padding-top: 1.25rem; padding-bottom: 3rem;}
    [data-testid="stSidebar"] {background: #eaf0e8; border-right: 1px solid #d6e1d4;}
    h1,h2,h3 {letter-spacing: -.035em; color: #193d30;}
    [data-testid="stMetric"] {padding: .65rem 1rem; background: #fff; border: 1px solid #dde5d9; border-radius: 12px;}
    [data-testid="stForm"] {background: #fff; border-radius: 16px;}
    [data-testid="stExpander"] {background: #fff; border-radius: 14px;}
    .qp-hero {position:relative; overflow:hidden; padding:14px 20px; border-radius:14px; background:linear-gradient(115deg,#173f31,#31664b); color:#fff; margin:4px 0 8px;}
    .qp-hero:after {content:'';position:absolute;right:-40px;top:-110px;width:290px;height:290px;border:45px solid #ffffff0b;border-radius:50%;pointer-events:none;}
    .qp-eyebrow {font-size:12px;letter-spacing:.18em;color:#dbb987;margin-bottom:8px;}
    .qp-hero h1 {font-size:26px!important;line-height:1.25;padding:0!important;margin:0 0 4px;color:#fff;letter-spacing:.03em;}
    .qp-hero p {margin:0;color:#e2eddf;font-size:15px;max-width:85%;}
    .qp-context {display:inline-block;margin-top:6px;padding:3px 9px;background:#ffffff15;border:1px solid #ffffff26;border-radius:20px;font-size:12px;}
    .qp-step-no {color:#a46b2b;font-size:12px;letter-spacing:.1em;margin-bottom:4px;}
    .qp-step-title {font-weight:650;color:#244e39;margin-bottom:6px;font-size:16px;}
    .qp-step-copy {font-size:13px;line-height:1.7;color:#627260;}
    :root {--qp-ink:#193d30;--qp-muted:#52645b;--qp-brand:#267562;--qp-line:#d6e1d4;--qp-radius:16px;--qp-space:16px;}
    button, input, textarea, [data-baseweb="select"] {font-family:inherit!important;}
    .stButton button,.stDownloadButton button,.stLinkButton a {border-radius:12px;min-height:44px;font-weight:600;}
    .stTextInput input,.stTextArea textarea,[data-baseweb="select"]>div {border-radius:10px;}
    button:focus-visible,input:focus-visible,textarea:focus-visible,a:focus-visible {outline:3px solid #1e40af!important;outline-offset:3px;}
    [data-baseweb="tab-list"] {gap:8px;border-bottom:1px solid var(--qp-line);flex-wrap:wrap;}
    [data-baseweb="tab"] {padding:12px 16px;border-radius:12px 12px 0 0;min-height:44px;}
    [aria-selected="true"][role="tab"] {background:#e1eee5;color:#174b37;font-weight:700;}
    [data-testid="stDataFrame"] {border:1px solid var(--qp-line);border-radius:12px;}
    [data-testid="stAlert"] {border-radius:12px;}
    .qp-badge {display:inline-block;padding:5px 11px;border-radius:24px;font-weight:650;font-size:13px;line-height:1.5;}
    .qp-content-card {background:white;border:1px solid var(--qp-line);border-radius:var(--qp-radius);padding:24px;margin:12px 0 20px;}
    .qp-prose {white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.85;font-family:inherit;font-size:16px;color:#24352e;}
    .qp-empty {padding:28px;text-align:center;border:1px dashed #9aafa0;border-radius:var(--qp-radius);background:#fff;}
    .qp-empty>span {font-size:36px;color:#267562;}.qp-empty p {color:var(--qp-muted);}
    .qp-timeline {border-left:3px solid #8bb5a0;margin:12px 0;padding:6px 0 6px 20px;}
    .qp-timeline p {margin:6px 0;overflow-wrap:anywhere;}.qp-timeline small {color:var(--qp-muted);}
    .qp-step-current {padding:7px 10px;border-radius:10px;background:#dcfce7;color:#14532d;font-weight:700;}
    .qp-step-idle {padding:7px 10px;color:#334155;}
    .qp-progress-nav {display:flex;gap:12px;overflow-x:auto;white-space:nowrap;padding:6px 0;}
    .qp-progress-nav span {flex:0 0 auto;font-size:14px;}
    .qp-progress-nav [aria-current="step"] {font-weight:700;color:#14532d;}
    .st-key-workspace-nav [data-testid="stHorizontalBlock"] {flex-wrap:wrap;}
    .st-key-workspace-nav [data-testid="stColumn"] {min-width:140px!important;flex:1 1 140px!important;}
    @media(max-width:1100px){[data-testid="stHorizontalBlock"]{flex-wrap:wrap}[data-testid="stColumn"]{min-width:min(100%,240px);flex:1 1 240px}.st-key-workspace-metrics [data-testid="stColumn"]{min-width:90px!important;flex:1 1 90px!important}.st-key-workspace-metrics [data-testid="stMetric"]{padding:8px}.st-key-workspace-metrics [data-testid="stMetricValue"]{font-size:24px}.st-key-workspace-metrics [data-testid="stMetricLabel"] p{font-size:12px;white-space:normal}}
    @media(max-width:700px){.qp-hero{margin:4px 0 10px!important;padding:14px 18px!important}.qp-hero h1{font-size:24px!important;padding:0!important;margin:0!important}.qp-hero p,.qp-hero .qp-context{display:none}.qp-progress-nav span{font-size:12px}}
    @media(max-width:700px){.qp-content-card{padding:16px}.qp-prose{font-size:15px}[data-testid="stHorizontalBlock"]{flex-wrap:wrap}[data-testid="stColumn"]{min-width:min(100%,240px);flex:1 1 240px}.qp-hero p{max-width:100%}}
    @media(max-width:700px){.block-container{padding-top:1.4rem}.qp-hero{padding:22px}.qp-hero h1{font-size:28px}.qp-hero p{max-width:100%}}
    @media(max-width:700px){.st-key-workspace-nav [data-testid="stColumn"]{min-width:140px!important;flex:1 1 140px!important}.st-key-workspace-metrics [data-testid="stColumn"]{min-width:90px!important;flex:1 1 90px!important}.st-key-workspace-metrics [data-testid="stMetric"]{padding:8px}.st-key-workspace-metrics [data-testid="stMetricValue"]{font-size:24px}}
    </style>''', unsafe_allow_html=True)


def workspace_header(page, product=None, progress=None):
    module = MODULES[page]
    if product:
        from services.query_service import product_label
        context = product_label(product)
    else:
        context = '从导入第一份资料开始'
    st.markdown(f'''<section class="qp-hero"><div class="qp-eyebrow">黔品智营 / {module['tag']} / {module['number']}</div>
        <h1>{page}</h1><p>{module['summary']}</p><span class="qp-context">{escape(context)}</span></section>''', unsafe_allow_html=True)
    with st.container(key='workspace-nav'):
        for col, name in zip(st.columns(4), MODULES):
            col.button(f"{MODULES[name]['number']} · {name}", key='step:'+name,
                       type='primary' if name == page else 'secondary', on_click=navigate, args=(name,), width='stretch')
    if st.session_state.get('show_module_guide', True):
        with st.expander('本模块怎么用 · 三步上手', expanded=False):
            for i, (col, (title, description)) in enumerate(zip(st.columns(3), module['steps']), 1):
                with col:
                    st.markdown(f'<div class="qp-step-no">STEP {i:02}</div><div class="qp-step-title">{title}</div><div class="qp-step-copy">{description}</div>', unsafe_allow_html=True)
            with st.expander('操作要点与常见问题'):
                for tip in module['tips']:
                    st.write('• ' + tip)
            def open_module_tutorial():
                st.session_state['next_tutorial_topic'] = page
                navigate('使用教程')
            st.button('查看本模块完整流程图与操作说明',key='module_tutorial:'+page,on_click=open_module_tutorial)


def product_overview(progress):
    from views.components import status_badge, glossary
    st.caption('当前产品概览 · 生成必需资料为名称与净含量；价格按需要核对对应渠道。')
    st.markdown('**当前业务状态：' + progress['stage'] + '**')
    cols = st.columns(4)
    cols[0].metric('必需资料已确认', f"{progress['confirmed']}/2")
    cols[1].metric('冲突字段', progress['conflicts'])
    cols[2].metric('待核对字段组', progress['pending'])
    with cols[3]:
        st.caption('最近内容状态')
        if progress['latest']:
            status_badge(progress['latest'])
        else:
            st.write('尚未生成')
    st.progress(progress['confirmed']/2, text=f"生成必需资料完成度 {progress['confirmed']*50}%")
    glossary()

"""Accessible presentation helpers: every state has text, symbol and color."""
from html import escape
import streamlit as st

STATE_LABELS = {
    'pending': ('◷', '待确认', 'warning'), 'adopted': ('✓', '已采纳', 'success'),
    'excluded': ('−', '已排除', 'neutral'), 'duplicate': ('≡', '重复证据', 'neutral'),
    'error': ('!', '格式错误', 'danger'), 'current': ('✓', '当前确认', 'success'),
    'superseded': ('↗', '已替代', 'neutral'), 'withdrawn': ('−', '已撤回', 'danger'),
    'draft': ('✎', '草稿', 'neutral'), 'review': ('◷', '待审核', 'info'),
    'ready': ('✓', '可导出', 'success'), 'stale': ('!', '待复查', 'warning'),
    'archived': ('▣', '历史归档', 'neutral'), 'running': ('◷', '处理中', 'info'),
    'succeeded': ('✓', '已完成', 'success'), 'failed': ('!', '失败', 'danger'),
}
COLORS = {'success': ('#14532d','#dcfce7'), 'warning': ('#78350f','#fef3c7'),
          'danger': ('#991b1b','#fee2e2'), 'neutral': ('#334155','#e2e8f0'),
          'info': ('#1e3a8a','#dbeafe')}


def badge_html(state):
    symbol, label, tone = STATE_LABELS.get(state, ('○', str(state), 'neutral'))
    fg, bg = COLORS[tone]
    return f'<span class="qp-badge" style="color:{fg};background:{bg}">{escape(symbol)} {escape(label)}</span>'


def status_badge(state):
    st.markdown(badge_html(state), unsafe_allow_html=True)


def content_card(title, body, state='draft'):
    st.markdown(f'<article class="qp-content-card">{badge_html(state)}<h3>{escape(title)}</h3>'
                f'<div class="qp-prose">{escape(body)}</div></article>', unsafe_allow_html=True)


def empty_state(title, description, label=None, page=None, key='empty'):
    st.markdown(f'<section class="qp-empty"><span aria-hidden="true">◇</span><h3>{escape(title)}</h3>'
                f'<p>{escape(description)}</p></section>', unsafe_allow_html=True)
    if label and page:
        from views.guidance import next_button
        next_button(label, page, key)


def state_table(rows):
    import pandas as pd
    data = pd.DataFrame(rows)
    columns = [c for c in ('state','状态') if c in data.columns]
    def style(value):
        key = next((k for k, v in STATE_LABELS.items() if value in (k,v[1])), None)
        tone = STATE_LABELS[key][2] if key else 'neutral'
        fg, bg = COLORS[tone]
        return f'color:{fg};background-color:{bg};font-weight:600'
    for column in columns:
        data[column] = data[column].map(lambda v: STATE_LABELS[v][1] if v in STATE_LABELS else v)
    st.dataframe(data.style.map(style, subset=columns) if columns else data,
                 hide_index=True, width='stretch')


def notifications():
    notice = st.session_state.pop('notice', None)
    if notice:
        tone, message = notice if isinstance(notice, tuple) else ('success', notice)
        getattr(st, tone if tone in ('success','error','warning','info') else 'info')(message)


def glossary():
    with st.popover('术语小贴士', help='了解页面里的常用词'):
        for title, description in {
            '候选': '来源提供的说法，尚未被你确认。', '确认资料': '你核对并决定采用的事实；生成内容只用这些资料。',
            '排除误录': '把不适用的来源移出待确认列表，历史仍保留。', '输入快照': '生成这份内容时使用的资料副本。',
            '重绑依据': '逐句复查正文后，让新修订使用当前资料；必须重新审核。',
        }.items():
            st.markdown(f'**{title}**：{description}')

import json
import uuid
import streamlit as st
from config import FIELDS, CONTENT_TYPES
from services.fact_service import withdraw_fact
from services.impact_service import impact_worklist
from services.content_service import generate_content, edit_content
from views.common import STATES, action, display_value, fact_table, display_context
from views.guidance import next_button, navigate


def open_review(content_id):
    st.session_state['focused_content'] = content_id
    navigate('内容工作台')


def render(repo, product_id, operator):
    if not product_id:
        st.info('请先导入产品资料，再生成可追踪的内容。')
        next_button('去准备资料', '产品资料', 'impact:import')
        return
    rows = impact_worklist(repo, product_id)
    labels = {'needs_update': '待更新正文', 'needs_review': '新修订待审核', 'resolved': '本次变更已处理'}
    for col, state in zip(st.columns(3), labels):
        col.metric(labels[state], sum(r['resolution'] == state for r in rows))
    st.caption('按每份内容的最新修订统计。旧版本保留原始依据，可展开查看历史。')
    include_resolved = st.checkbox('查看已处理记录', value=False, key='include_resolved_impacts')
    if not rows:
        st.info('还没有需要复查的变化。先生成一份内容，再修订其依据即可体验变更追踪。')
    elif all(r['resolution'] == 'resolved' for r in rows):
        st.success('当前关联内容的最新修订均已审核通过。请使用新文件替换外部已发布内容。')
    for row in rows:
        if row['resolution'] == 'resolved' and not include_resolved:
            continue
        with st.expander(f"{CONTENT_TYPES[row['content_type']]} · R{row['revision']} · {labels[row['resolution']]}", expanded=True):
            st.write(row['body'])
            st.dataframe([{'变化字段': FIELDS[t['changed_field']], '适用范围': display_context(t['changed_context']),
                '原依据': display_value(t['changed_field'], t['old_value']), '新依据': display_value(t['changed_field'], t['new_value']),
                '变更原因': t['change_reason']} for t in row['triggers']], hide_index=True, width='stretch')
            if row['resolution'] == 'needs_review':
                st.info('新修订已保存，完成审核后这项任务会显示为已处理。')
                st.button('去审核这份新修订', key=f"review-impact:{row['id']}", on_click=open_review, args=(row['id'],), type='primary')
            elif row['resolution'] == 'needs_update':
                if st.button('按当前资料生成模板新修订', key=f"regenerate:{row['id']}", type='primary'):
                    snapshot = json.loads(row['snapshot_json'])
                    ok, output = action(lambda: generate_content(repo, product_id, uuid.uuid4().hex, row['context'], row['content_type'],
                        snapshot['include_price'], logical_id=row['logical_id']), '新草稿已保存。请到内容工作台审核。')
                    if ok:
                        st.session_state['focused_content'] = output['content_id']
                        st.rerun()
                st.button('去手动修改并重新审核', key=f"edit-impact:{row['id']}", on_click=open_review, args=(row['id'],))
                with st.expander('正文确实无需修改时，沿用并重绑依据'):
                    with st.form(f"reuse:{row['id']}"):
                        reason = st.text_input('正文无需改写的复查依据')
                        checked = st.checkbox('已逐句对照新资料，确认这段正文仍然适用')
                        st.caption('旧正文中的价格或规格与新资料不符时，系统会要求先修改正文。')
                        if st.form_submit_button('正文沿用，重绑为新修订'):
                            if not checked:
                                st.error('请先完成人工复查。')
                            else:
                                ok, new_id = action(lambda: edit_content(repo, row['id'], row['title'], row['body'], operator, reason, rebind=True))
                                if ok:
                                    st.session_state['focused_content'] = new_id
                                    st.rerun()
            else:
                st.button('查看最新内容与导出', key=f"ready-impact:{row['id']}", on_click=open_review, args=(row['id'],))
            with st.expander('追溯受影响的历史修订'):
                for old in row['history']:
                    st.caption(f"内容 #{old['id']} / R{old['revision']} / {STATES[old['state']]}")
                    st.text(old['body'])
    st.subheader('当前确认资料')
    st.caption('需要调价或纠错时，先补录新来源，再到数据核对页确认。')
    next_button('去补录新的产品资料', '产品资料', 'impact:source')
    facts = fact_table(repo, product_id)
    if facts:
        with st.expander('撤回一项确认资料'):
            mapping = {r['id']: r for r in facts}
            chosen = st.selectbox('撤回目标', list(mapping), format_func=lambda i:
                f"{FIELDS[mapping[i]['field']]} · {display_context(mapping[i]['context'])} · #{i}")
            with st.form('withdraw'):
                reason = st.text_input('撤回原因')
                checked = st.checkbox('确认撤回，并将依赖此修订的内容标为待复查')
                if st.form_submit_button('撤回此修订'):
                    if not checked:
                        st.error('请先勾选撤回确认。')
                    else:
                        fact = mapping[chosen]
                        ok, _ = action(lambda: withdraw_fact(repo, product_id, fact['field'], fact['context'], chosen, operator, reason))
                        if ok:
                            st.rerun()
    with st.expander('完整字段修订与变更事件'):
        st.dataframe(repo.all('SELECT * FROM fact_revisions WHERE product_id=? ORDER BY id DESC', (product_id,)), hide_index=True, width='stretch')
        st.dataframe(repo.all('SELECT * FROM change_events WHERE product_id=? ORDER BY id DESC', (product_id,)), hide_index=True, width='stretch')

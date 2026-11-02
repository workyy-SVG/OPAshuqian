import json
import uuid
import streamlit as st
from config import FIELDS, CONTENT_TYPES
from services.fact_service import withdraw_fact
from services.impact_service import impact_worklist
from services.content_service import generate_content, edit_content
from views.common import STATES, action, display_value, fact_table, display_context
from views.guidance import next_button, navigate
from services import query_service as queries
from views.components import content_card, empty_state, state_table
from html import escape


def open_review(content_id):
    st.session_state['focused_content'] = content_id
    navigate('内容工作台')


def render(repo, product_id, operator):
    if not product_id:
        empty_state('资料变化，会在这里留下轨迹', '先导入并生成一份内容，再修订其依据即可体验。', '去准备资料', '产品资料', 'impact:import')
        return
    rows = impact_worklist(repo, product_id)
    st.caption('选择一份受影响内容，核对变化后生成新修订，再完成人工审核。')
    labels = {'needs_update': '待更新正文', 'needs_review': '新修订待审核', 'resolved': '本次变更已处理'}
    with st.container(key='workspace-metrics'):
        for col, state in zip(st.columns(3), labels):
            col.metric(labels[state], sum(r['resolution'] == state for r in rows))
    st.caption('按每份内容的最新修订统计。旧版本保留原始依据，可展开查看历史。')
    work_tab, update_tab, history_tab = st.tabs(['待办处理', '更新资料', '变更记录'], key='impact_workspace_tab', on_change='rerun')
    with work_tab:
        include_resolved = st.checkbox('查看已处理记录', value=False, key='include_resolved_impacts')
        if not rows:
            empty_state('暂时没有需要复查的内容', '先完成内容审核；之后调价或纠错时，这里会指出哪些文案需要更新。')
        elif all(r['resolution'] == 'resolved' for r in rows):
            st.success('当前关联内容的最新修订均已审核通过。请使用新文件替换外部已发布内容。')
        visible_rows = [r for r in rows if include_resolved or r['resolution'] != 'resolved']
        if visible_rows:
            mapping = {r['id']: r for r in visible_rows}
            selected = st.selectbox('选择待处理内容', list(mapping), key=f'impact_task:{product_id}',
                                    format_func=lambda i: f"#{i} · {mapping[i]['title']} · {labels[mapping[i]['resolution']]}")
            row = mapping[selected]
            with st.expander(f"{CONTENT_TYPES[row['content_type']]} · R{row['revision']} · {labels[row['resolution']]}", expanded=True):
                with st.expander('查看这份内容的完整正文', expanded=False):
                    content_card(row['title'], row['body'], row['state'])
                st.caption(f"本项涉及1份逻辑内容、{len(row['history'])}条历史修订；以下变化需要逐项复查。")
                for trigger in row['triggers']:
                    field = trigger['changed_field']
                    old = escape(str(display_value(field,trigger['old_value'])))
                    new = escape(str(display_value(field,trigger['new_value'])))
                    st.markdown(f'<div class="qp-timeline"><strong>{escape(FIELDS[field])} · {escape(display_context(trigger["changed_context"]))}</strong>'
                                f'<p>{old} → {new}</p><small>变更 #{trigger["event_id"]} · {escape(trigger["change_reason"])}</small></div>', unsafe_allow_html=True)
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
                        content_card(old['title'],old['body'],old['state'])
    with update_tab:
        st.subheader('更新资料')
        left, right = st.columns(2)
        def open_entry(field):
            st.session_state['focused_manual_field'] = field
            st.session_state['next_product'] = product_id
            st.session_state['pending_navigation'] = '产品资料'
        left.button('修改价格', key='impact_change_price', type='primary', on_click=open_entry, args=('price_cent',), width='stretch')
        right.button('纠正其他资料', key='impact_correct_fact', on_click=navigate, args=('产品资料',), width='stretch')
        with st.expander('撤回不再可靠的资料（维护操作）', expanded=False):
            render_fact_actions(repo, product_id, operator)
    with history_tab:
        state_table(queries.fact_history(repo, product_id))
        st.dataframe(queries.change_history(repo, product_id), hide_index=True, width='stretch')


def render_fact_actions(repo, product_id, operator):
    st.caption('撤回只用于资料本身不再可靠；普通调价请使用上方“修改价格”。')
    facts = fact_table(repo, product_id)
    if facts:
        with st.container(border=True):
            st.markdown('**仅在资料本身不再可靠时撤回**')
            mapping = {r['id']: r for r in facts}
            chosen = st.selectbox('撤回目标', list(mapping), format_func=lambda i:
                f"{FIELDS[mapping[i]['field']]} · {display_context(mapping[i]['context'])} · #{i}")
            affected = queries.dependent_content_count(repo, chosen)
            st.warning(f'撤回将影响 {affected} 份内容修订；这些内容需重新核对后才可导出。历史资料会保留。')
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

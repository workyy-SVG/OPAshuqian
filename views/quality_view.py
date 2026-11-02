import streamlit as st
from config import FIELDS
from services.quality_service import detect_issues, exclude_observation, reassign_observation
from services.fact_service import confirm_fact
from views.common import action, fact_table, display_value, display_context
from views.guidance import next_button
from services import query_service as queries
from views.components import empty_state, status_badge, state_table


def render(repo, product_id, operator):
    st.write('这里的任务是：对照包装或可靠来源，决定每一项资料要不要采用。导入成功不等于已经确认。')
    work_tab, history_tab, help_tab = st.tabs(['① 待处理资料','② 确认结果与记录','操作说明'])
    with help_tab:
        from views.tutorial_view import flow_diagram
        st.subheader('先弄清三个词')
        flow_diagram([('候选','资料来源提供的说法，还不能用于生成'),('冲突','同一字段出现不同值，需要你查证'),('确认资料','你核对后决定采用的事实，生成会使用它')])
        st.markdown('**照着这五步做**')
        for step in ['① 在侧栏选择SKU/版本，填写操作人。','② 切到“待处理资料”，先处理有冲突的字段。',
                     '③ 看候选卡片：原文是什么、从哪里来，与实物是否一致。',
                     '④ 点“选此项确认”或“选此项排除”，填写依据，再点“保存本次处理”。',
                     '⑤ 重复确认名称和净含量；需要价格时再确认对应渠道价格。完成后去生成内容。']:
            st.write(step)
        st.info('示例：200g与0.2kg都是200克，不属于不同重量。250g与200g不同，必须对照包装；仅拟制样例中250g已知为误录。')
        with st.expander('我该选哪种处理方式？', expanded=True):
            st.write('确认采用：来源可靠，且确实适用于当前产品。排除误录：已经查明错误或不适用。重新分配对象：这条信息其实属于另一个SKU或版本。')
            st.warning('不确定时先不处理，回产品资料页补录可靠来源。不要为了让提示消失随意采用。')
        def open_tutorial():
            st.session_state['next_tutorial_topic']='数据核对'
            st.session_state['pending_navigation']='使用教程'
        st.button('打开数据核对完整教程',on_click=open_tutorial,key='quality_full_tutorial')
    with work_tab:
        render_work(repo,product_id,operator)
    with history_tab:
        if product_id:
            st.subheader('当前已确认资料')
            fact_table(repo,product_id)
            with st.expander('查看每次处理的操作人、原因与时间'):
                state_table(queries.observation_actions(repo,product_id))
        else:
            st.info('先导入产品资料，处理后可在这里查看结果。')


def render_work(repo, product_id, operator):
    if not product_id:
        empty_state('先准备一份产品资料', 'CSV样例和公开食品查询都可以作为起点。', '去导入产品资料', '产品资料', 'quality:import')
        return
    issues = detect_issues(repo, product_id)
    dated = queries.dated_candidates(repo, product_id)
    if dated:
        future_count = sum(r['availability']=='future' for r in dated)
        with st.expander(f"适用日期提醒：{len(dated)-future_count}条可核对，{future_count}条尚未到期"):
            st.caption('到期后自动出现在可核对候选中，仍需你人工确认才会生效；未来候选不阻止当前有效资料的使用。')
            st.dataframe([{'字段': FIELDS.get(r['field'],r['field']), '原文': r['raw'], '适用日期': r['effective_from'],
                           '状态': '尚未到期' if r['availability']=='future' else '已到期，待人工确认', '来源': r['source_label']} for r in dated],
                         hide_index=True, width='stretch')
    counts = [sum(i["type"] == kind for i in issues) for kind in ("missing", "conflict", "pending")]
    for col, label, count in zip(st.columns(3), ("还需确认的必需资料", "有不同值的字段", "等待你核对的字段组"), counts):
        col.metric(label, count)
    confirmed_fields = {r['field'] for r in queries.current_facts(repo, product_id) if r['context']=='general'}
    done = sum(f in confirmed_fields for f in ('product_name','net_weight_g'))
    st.progress(done/2, text=f'生成必需资料：名称、净含量已确认 {done}/2 项')
    conflicts = [i for i in issues if i['type']=='conflict']
    if conflicts:
        with st.expander('查看冲突分布图', expanded=False):
            st.bar_chart([{'字段': FIELDS[i['field']]+' · '+display_context(i['context']),
                           '不同候选值':len({r['normalized'] for r in i['observations']})} for i in conflicts],
                         x='字段', y='不同候选值', color='#a16207', horizontal=True)
    for issue in issues:
        if issue["type"] == "missing":
            has_candidates = any(i.get('field') == issue['field'] and i.get('observations') for i in issues)
            if has_candidates:
                st.warning(f"{FIELDS[issue['field']]}已有候选，请在下方核对并确认。")
            else:
                st.warning(f"{FIELDS[issue['field']]}没有候选资料，请先补录可靠来源。")
                def open_missing(field=issue['field']):
                    st.session_state['focused_manual_field'] = field
                    st.session_state['next_product'] = product_id
                    st.session_state['pending_navigation'] = '产品资料'
                st.button('补录' + FIELDS[issue['field']], key='fill_missing:'+issue['field'],
                          on_click=open_missing)
    groups = [i for i in issues if "observations" in i]
    if not groups:
        st.success("当前没有待处理候选。")
    else:
        view_filter = st.radio('核对范围', ['全部待核对','只看冲突','只看名称与净含量'], horizontal=True)
        if view_filter == '只看冲突':
            groups = [g for g in groups if g['type']=='conflict']
        elif view_filter == '只看名称与净含量':
            groups = [g for g in groups if g['field'] in ('product_name','net_weight_g')]
        groups.sort(key=lambda i: (0 if i["type"] == "conflict" else 1 if i["field"] in ("product_name", "net_weight_g") else 2, i["field"], i["context"]))
        group_map = {i["issue_id"]: i for i in groups}
        if group_map:
            selected_group = st.selectbox("选择待核对字段", list(group_map), format_func=lambda k:
                f"{FIELDS[group_map[k]['field']]} · {display_context(group_map[k]['context'])} · {group_map[k]['message']}")
            groups = [group_map[selected_group]]
        else:
            st.info('当前筛选没有待处理字段，可切回“全部待核对”。')
    for issue in groups:
        field, scope = issue["field"], issue["context"]
        key = issue["issue_id"]
        current_id = issue["current"]["id"] if issue["current"] else None
        seen_key = "seen:" + key
        seen = st.session_state.get(seen_key, current_id)
        with st.expander(f"{'⚠' if issue['type'] == 'conflict' else '○'} {FIELDS[field]} · {display_context(scope)} · {issue['message']}", expanded=True):
            st.markdown('**第1步 · 对照来源，选择要处理的资料**')
            if issue['type']=='conflict':
                st.warning('这些来源的标准值不同。先查实物或可靠依据，排除错误项后再确认正确项。')
            else:
                st.info('这些候选没有不同标准值，也仍需你核对来源后确认。')
            if issue["current"]:
                st.caption(f"当前确认：{display_value(field, issue['current']['value'])} · 修订 #{current_id}")
            order = st.selectbox('候选排序', ['来源行顺序','原文排序'], key='order:'+key)
            records = sorted(issue['observations'], key=lambda r:r['raw'] if order=='原文排序' else r['id'])
            def choose_candidate(oid, decision):
                st.session_state['choice:'+key] = oid
                st.session_state['decision:'+key] = decision
            for record in records:
                with st.container(border=True):
                    status_badge(record['state'])
                    st.write(f"**{record['raw']}** → {display_value(field,record['normalized'])}")
                    st.caption(f"{record['source_label']} · 来源行 {record['row_no']} · 适用日期 {record['effective_from'] or '未指定'}")
                    with st.expander(f"查看该项来源 · #{record['id']}"):
                        st.write(record['source_locator'])
                    left,right = st.columns(2)
                    left.button('选此项确认', key=f"adopt-card:{record['id']}", on_click=choose_candidate, args=(record['id'],'确认采用'))
                    right.button('选此项排除', key=f"exclude-card:{record['id']}", on_click=choose_candidate, args=(record['id'],'排除误录'))
            st.caption('先在卡片选择资料，再填写下方处理依据并保存。候选尚未成为确认资料。')
            st.markdown('**第2步 · 确认处理方式，填写核对依据**')
            decision = st.radio("处理方式", ["确认采用", "排除误录", "重新分配对象"], horizontal=True, key="decision:" + key)
            with st.form("resolve:" + key):
                evidence = {r['id']: r for r in issue['observations']}
                chosen = st.selectbox("这次处理哪条资料？", list(evidence), key="choice:" + key,
                    format_func=lambda i: f"{evidence[i]['raw']} · {evidence[i]['source_label']} · #{i}")
                target = product_id
                if decision == '重新分配对象':
                    products = queries.products(repo)
                    target = st.selectbox("重新分配的目标产品", [p["id"] for p in products],
                        format_func=lambda i: next(f"{p['sku']} · {p['version']}" for p in products if p["id"] == i), key="target:" + key)
                reason = st.text_input("核对依据 / 处理原因", key="reason:" + key, placeholder="说明查阅了什么依据、为什么采纳或排除")
                st.caption('依据示例：“已查看包装标签为200g”；“查明此条250g为误录”。请填写本次实际核查结果。')
                acknowledged = st.checkbox('确认排除此项；来源和处理历史仍保留', key='exclude_ack:'+key) if decision=='排除误录' else True
                submitted = st.form_submit_button("保存本次处理", type="primary")
                if submitted:
                    if not acknowledged:
                        st.session_state['notice'] = ('warning','请先勾选排除确认；资料尚未修改。')
                        st.rerun()
                    if decision == "确认采用":
                        callback = lambda: confirm_fact(repo, product_id, chosen, seen, operator, reason)
                    elif decision == "排除误录":
                        callback = lambda: exclude_observation(repo, chosen, operator, reason)
                    else:
                        callback = lambda: reassign_observation(repo, chosen, target, operator, reason)
                    ok, _ = action(callback)
                    if ok:
                        st.session_state.pop(seen_key, None)
                        st.rerun()
        st.session_state[seen_key] = current_id
    if not counts[0] and not counts[1]:
        st.success('名称和净含量已确认。生成含价格的内容前，还需确认对应渠道价格。')
        next_button('下一步：去生成内容', '内容工作台', 'quality:generate')
    st.caption('处理后可在“确认结果与记录”查看采用了什么资料，以及处理原因。')

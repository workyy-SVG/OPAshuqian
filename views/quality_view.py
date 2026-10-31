import streamlit as st
from config import FIELDS
from services.quality_service import detect_issues, exclude_observation, reassign_observation
from services.fact_service import confirm_fact
from views.common import action, fact_table, display_value, display_context
from views.guidance import next_button
from services import query_service as queries


def render(repo, product_id, operator):
    st.write("并列查看来源，明确取舍。不同 SKU、产品版本和价格渠道分别核对。")
    if not product_id:
        st.info("请先在产品资料页导入或新增产品。")
        next_button('去导入产品资料', '产品资料', 'quality:import')
        return
    issues = detect_issues(repo, product_id)
    counts = [sum(i["type"] == kind for i in issues) for kind in ("missing", "conflict", "pending")]
    for col, label, count in zip(st.columns(3), ("必需信息未确认", "存在冲突的字段", "待确认字段组"), counts):
        col.metric(label, count)
    for issue in issues:
        if issue["type"] == "missing":
            st.warning(f"{FIELDS[issue['field']]}：{issue['message']}")
    groups = [i for i in issues if "observations" in i]
    if not groups:
        st.success("当前没有待处理候选。")
    else:
        groups.sort(key=lambda i: (0 if i["type"] == "conflict" else 1 if i["field"] in ("product_name", "net_weight_g") else 2, i["field"], i["context"]))
        group_map = {i["issue_id"]: i for i in groups}
        selected_group = st.selectbox("选择待核对字段", list(group_map), format_func=lambda k:
            f"{FIELDS[group_map[k]['field']]} · {display_context(group_map[k]['context'])} · {group_map[k]['message']}")
        groups = [group_map[selected_group]]
    for issue in groups:
        field, scope = issue["field"], issue["context"]
        key = issue["issue_id"]
        current_id = issue["current"]["id"] if issue["current"] else None
        seen_key = "seen:" + key
        seen = st.session_state.get(seen_key, current_id)
        with st.expander(f"{'⚠' if issue['type'] == 'conflict' else '○'} {FIELDS[field]} · {display_context(scope)} · {issue['message']}", expanded=True):
            if issue["current"]:
                st.caption(f"当前确认：{display_value(field, issue['current']['value'])} · 修订 #{current_id}")
            st.dataframe([{"候选编号": r["id"], "来源": r["source_label"], "原文": r["raw"],
                           "标准值": display_value(field, r["normalized"]), "源位置": r["source_locator"],
                           "CSV行号": r["row_no"], "适用日期": r["effective_from"] or "未知"} for r in issue["observations"]],
                         hide_index=True, width="stretch")
            with st.form("resolve:" + key):
                evidence = {r['id']: r for r in issue['observations']}
                chosen = st.selectbox("选择候选编号", list(evidence), key="choice:" + key,
                    format_func=lambda i: f"{evidence[i]['raw']} · {evidence[i]['source_label']} · #{i}")
                decision = st.radio("处理方式", ["确认采用", "排除误录", "重新分配对象"], horizontal=True, key="decision:" + key)
                products = queries.products(repo)
                target = st.selectbox("重新分配的目标产品（仅对应操作使用）", [p["id"] for p in products],
                    format_func=lambda i: next(f"{p['sku']} · {p['version']}" for p in products if p["id"] == i), key="target:" + key)
                reason = st.text_input("核对依据 / 处理原因", key="reason:" + key, placeholder="说明查阅了什么依据、为什么采纳或排除")
                submitted = st.form_submit_button("保存本次处理", type="primary")
                if submitted:
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
    st.subheader("确认事实与来源")
    fact_table(repo, product_id)
    if not counts[0] and not counts[1]:
        st.success('名称和净含量已确认。生成含价格的内容前，还需确认对应渠道价格。')
        next_button('下一步：去生成内容', '内容工作台', 'quality:generate')
    with st.expander("候选处理审计"):
        st.dataframe(queries.observation_actions(repo, product_id), hide_index=True, width="stretch")

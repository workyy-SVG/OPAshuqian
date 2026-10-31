import json
import uuid
import streamlit as st
from config import FIELDS, CONTENT_TYPES
from services.fact_service import withdraw_fact
from services.impact_service import list_impacts
from services.content_service import generate_content, edit_content
from views.common import STATES, action, display_value, fact_table


def render(repo, product_id, operator):
    st.write("资料修订后，根据实际输入依赖提醒内容复查。首版采用内容级追踪，可能包含人工判断后无需改写的内容。")
    if not product_id:
        st.info("请先选择一个产品对象。")
        return
    rows = list_impacts(repo, product_id)
    stale = [r for r in rows if r["state"] == "stale"]
    columns = st.columns(3)
    columns[0].metric("可能受影响的历史修订", len(rows))
    columns[1].metric("待复查的历史修订", len(stale))
    columns[2].metric("字段变更事件", repo.one("SELECT COUNT(*) n FROM change_events WHERE product_id=?", (product_id,))["n"])
    st.caption("旧修订会保留待复查标记。完成新修订并审核后，以最新修订为准；系统不会自动替换外部已发布内容。")
    if not rows:
        st.info("尚无受影响内容。先生成内容，再修订它依赖的确认资料。")
    for row in rows:
        latest = repo.one("SELECT id,revision,state FROM content_revisions WHERE logical_id=? ORDER BY revision DESC LIMIT 1", (row["logical_id"],))
        with st.expander(f"#{row['id']} · {CONTENT_TYPES[row['content_type']]} · R{row['revision']} · {STATES[row['state']]}", expanded=row["state"] == "stale"):
            st.write(row["body"])
            st.dataframe([{"变更事件": t["event_id"], "字段": FIELDS[t["changed_field"]], "渠道": t["changed_context"],
                           "原依据": display_value(t["changed_field"], t["old_value"]),
                           "新依据": display_value(t["changed_field"], t["new_value"]), "变更原因": t["change_reason"]} for t in row["triggers"]], hide_index=True, width="stretch")
            st.caption(f"此内容的最新修订为 #{latest['id']} / R{latest['revision']} / {STATES[latest['state']]}")
            if st.button("按当前资料生成模板新修订", key=f"regenerate:{row['id']}"):
                snapshot = json.loads(row["snapshot_json"])
                ok, result = action(lambda: generate_content(repo, product_id, uuid.uuid4().hex, row["context"], row["content_type"],
                    snapshot["include_price"], logical_id=row["logical_id"]), "新草稿已保存，请到内容工作台审核。")
                if ok:
                    st.session_state["focused_content"] = result["content_id"]
                    st.rerun()
            with st.form(f"reuse:{row['id']}"):
                reason = st.text_input("正文无需改写的复查依据")
                checked = st.checkbox("已逐句对照新资料，确认这段正文仍然适用")
                if st.form_submit_button("正文沿用，重绑为新修订"):
                    if not checked:
                        st.error("请先完成人工复查。")
                    else:
                        ok, new_id = action(lambda: edit_content(repo, row["id"], row["title"], row["body"], operator, reason, rebind=True), "已保存新修订，仍需到内容工作台审核。")
                        if ok:
                            st.session_state["focused_content"] = new_id
                            st.rerun()
    st.subheader("当前资料与修订操作")
    st.info("调价或纠错：在产品资料页补录新依据，再到数据核对页确认。真实商品换规格时，请先判断是否需要新增产品版本。")
    facts = fact_table(repo, product_id)
    if facts:
        with st.expander("撤回一项确认资料"):
            ids = [f["id"] for f in facts]
            facts_map = {f["id"]: f for f in facts}
            chosen = st.selectbox("撤回目标", ids, format_func=lambda i: f"#{i} · {FIELDS[facts_map[i]['field']]} · {facts_map[i]['context']}")
            with st.form("withdraw"):
                reason = st.text_input("撤回原因")
                checked = st.checkbox("确认撤回，并将依赖此修订的内容标为待复查")
                if st.form_submit_button("撤回此修订"):
                    if not checked:
                        st.error("请先勾选撤回确认。")
                    else:
                        fact = facts_map[chosen]
                        ok, _ = action(lambda: withdraw_fact(repo, product_id, fact["field"], fact["context"], chosen, operator, reason))
                        if ok:
                            st.rerun()
    with st.expander("完整字段修订与变更事件"):
        st.dataframe(repo.all("SELECT * FROM fact_revisions WHERE product_id=? ORDER BY id DESC", (product_id,)), hide_index=True, width="stretch")
        st.dataframe(repo.all("SELECT * FROM change_events WHERE product_id=? ORDER BY id DESC", (product_id,)), hide_index=True, width="stretch")

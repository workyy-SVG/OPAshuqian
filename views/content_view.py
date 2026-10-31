import json
import uuid
import streamlit as st
from config import CONTENT_TYPES, FIELDS
from repository import BusinessError
from services.fact_service import build_snapshot, current_basis
from services.content_service import (generate_content, edit_content, submit_for_review, approve_content, export_content)
from services.llm_client import DeepSeekClient, QwenClient
from views.common import STATES, action, display_value, model_configs


def render(repo, product_id, operator):
    st.write("只使用已确认资料组织内容。每份内容保留输入快照，逐句审核后才能导出。")
    if not product_id:
        st.info("请先导入产品资料并确认名称、净含量。")
        return
    create_tab, history_tab = st.tabs(["生成内容", "审核与历史"])
    with create_tab:
        left, right = st.columns([3, 2])
        with left:
            content_type = st.radio("内容类型", list(CONTENT_TYPES), format_func=CONTENT_TYPES.get, horizontal=True)
            context = st.text_input("价格渠道", value="retail", help="例如retail、wholesale，与资料的渠道名完全一致。")
            include_price = st.checkbox("加入该渠道价格", value=True)
            optional = st.multiselect("加入已确认的说明字段", ["ingredients_text", "usage_text", "storage_text"],
                                      default=["ingredients_text", "usage_text", "storage_text"], format_func=FIELDS.get)
            labels = {"template": "模板模式（不调用模型）", "deepseek": "DeepSeek 实时生成", "qwen": "通义千问实时生成"}
            mode = st.radio("生成方式", list(labels), format_func=labels.get, horizontal=True)
            configs = model_configs()
            cfg = configs.get(mode)
            if mode == "template":
                st.caption("模板按确认资料直接填充，用于验证流程；不计为真实模型调用。")
            elif not cfg.api_key:
                st.info(f"尚未配置{labels[mode].replace('实时生成', '')}密钥。按 README 在本机填写 .streamlit/secrets.toml 后即可使用。")
            else:
                st.caption(f"模型：{cfg.name} · 输出仍需人工核对，不自动视为事实正确。")
        # Include only available optional facts; absent optional fields are never invented.
        current = repo.all("SELECT field FROM fact_revisions WHERE product_id=? AND state='current'", (product_id,))
        selected = [f for f in optional if any(r["field"] == f for r in current)]
        try:
            basis = build_snapshot(repo, product_id, context, content_type, include_price,
                                    ["product_name", "net_weight_g"] + selected)
        except BusinessError as exc:
            st.error(str(exc))
            basis = None
        with right:
            st.subheader("本次生成依据")
            if basis:
                for fact in basis["snapshot"]["facts"]:
                    st.write(f"**{FIELDS[fact['field']]}**：{display_value(fact['field'], fact['value'])}")
                    st.caption(f"{fact['context']} · 字段修订 #{fact['fact_revision_id']}")
                if basis["missing"]:
                    st.warning("请先补齐或处理冲突：" + "、".join(FIELDS[f] for f in basis["missing"]))
                if basis["conflicts"]:
                    st.warning("所选字段存在未解决冲突，请到数据核对页处理。")
        disabled = not basis or bool(basis["missing"]) or (mode != "template" and not cfg.api_key)
        if st.button("生成一份草稿", type="primary", disabled=disabled, key="generate_draft"):
            request_key = uuid.uuid4().hex
            st.session_state["last_request_key"] = request_key
            with st.spinner("正在生成并核对依据…"):
                ok, result = action(lambda: generate_content(repo, product_id, request_key, context, content_type, include_price,
                    mode, DeepSeekClient(cfg) if mode == "deepseek" else QwenClient(cfg) if mode == "qwen" else None,
                    ["product_name", "net_weight_g"] + selected), "草稿已保存，请在“审核与历史”中逐句核对。")
            if ok:
                st.session_state["focused_content"] = result["content_id"]
                st.rerun()
    with history_tab:
        rows = repo.all("SELECT * FROM content_revisions WHERE product_id=? ORDER BY id DESC", (product_id,))
        if rows:
            ids = [r["id"] for r in rows]
            focused = st.session_state.pop("focused_content", None)
            if focused in ids:
                st.session_state["content_choice"] = focused
            if st.session_state.get("content_choice") not in ids:
                st.session_state["content_choice"] = ids[0]
            row_map = {r["id"]: r for r in rows}
            selected_id = st.selectbox("选择内容修订", ids, key="content_choice", format_func=lambda i:
                f"#{i} · {CONTENT_TYPES[row_map[i]['content_type']]} · R{row_map[i]['revision']} · {STATES[row_map[i]['state']]}")
            render_content(repo, row_map[selected_id], operator)
        else:
            st.info("尚无内容。确认必需资料后生成第一份草稿。")
        with st.expander("生成任务与失败记录"):
            jobs = repo.all("SELECT id,request_key,state,attempts,model,prompt_version,error_code,usage_json,created_at,finished_at FROM generation_jobs WHERE product_id=? ORDER BY id DESC", (product_id,))
            st.dataframe(jobs, hide_index=True, width="stretch")
            if any(j["state"] == "running" for j in jobs):
                st.warning("存在运行中任务，可能正在处理或因程序中断遗留。请先核查，确需重试时返回“生成内容”再次明确点击；原任务保留。")


def render_content(repo, row, operator):
    content_id = row["id"]
    st.caption(f"内容 #{content_id} · 修订 R{row['revision']} · {STATES[row['state']]} · {'模板模式' if row['mode'] == 'template' else row['mode']} · {row['context']}")
    st.subheader(row["title"])
    st.text(row["body"])
    with repo.connect() as db:
        basis = current_basis(db, json.loads(row["snapshot_json"]))
    valid = not basis["missing"] and basis["snapshot_hash"] == row["snapshot_hash"]
    if not valid or row["state"] == "stale":
        st.warning("这份内容的依据已变化或存在冲突。请到变更追踪页生成新修订或复查后重绑依据。")
    with st.expander("输入快照、来源与审核记录"):
        snapshot = json.loads(row["snapshot_json"])
        st.json(snapshot)
        st.caption("快照 SHA-256：" + row["snapshot_hash"])
        st.dataframe(repo.all("""SELECT f.id,f.field,f.context,f.value,f.state,o.source_label,o.source_locator,o.row_no,o.raw
            FROM content_dependencies d JOIN fact_revisions f ON f.id=d.fact_revision_id
            JOIN observations o ON o.id=f.source_observation_id WHERE d.content_revision_id=?""", (content_id,)), hide_index=True, width="stretch")
        st.dataframe(repo.all("SELECT * FROM review_records WHERE content_id=? ORDER BY id", (content_id,)), hide_index=True, width="stretch")
        st.dataframe(repo.all("SELECT id,operator,basis_hash,created_at FROM export_records WHERE content_id=? ORDER BY id", (content_id,)), hide_index=True, width="stretch")
    if row["state"] == "draft":
        if st.button("提交人工审核", key=f"submit:{content_id}", disabled=not valid):
            ok, _ = action(lambda: submit_for_review(repo, content_id, operator))
            if ok:
                st.rerun()
    if row["state"] == "review":
        with st.form(f"approve:{content_id}"):
            checked = st.checkbox("已逐句核对名称、规格、价格和其他陈述，未加入无依据事实")
            reason = st.text_input("审核说明")
            if st.form_submit_button("审核通过", disabled=not valid):
                if not checked:
                    st.error("请完成人工逐句核对并勾选确认。")
                else:
                    ok, _ = action(lambda: approve_content(repo, content_id, operator, row["snapshot_hash"], reason))
                    if ok:
                        st.rerun()
    if row["state"] == "ready" and valid:
        # Deferred execution checks the database at the actual download request.
        st.download_button("校验依据并下载 TXT", data=lambda: export_content(repo, content_id, operator)["text"],
                           file_name=f"qianpin-{content_id}-R{row['revision']}.txt", mime="text/plain; charset=utf-8",
                           key=f"export:{content_id}", disabled=not operator.strip())
    with st.expander("编辑为新修订"):
        with st.form(f"edit:{content_id}"):
            title = st.text_input("标题", value=row["title"])
            body = st.text_area("正文", value=row["body"], height=180)
            reason = st.text_input("修改原因")
            rebind = st.checkbox("已复查正文，使用当前确认资料重绑依据", value=False)
            st.caption("保存后创建新修订并重新审核。新事实需先在资料页补充并确认。")
            if st.form_submit_button("保存新修订"):
                ok, new_id = action(lambda: edit_content(repo, content_id, title, body, operator, reason, rebind))
                if ok:
                    st.session_state["focused_content"] = new_id
                    st.rerun()

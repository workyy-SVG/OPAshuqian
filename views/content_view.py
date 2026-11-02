import json
import uuid
import streamlit as st
from config import CONTENT_TYPES, FIELDS
from repository import BusinessError
from services.fact_service import build_snapshot, current_basis
from services.content_service import (generate_content, edit_content, submit_for_review, approve_content, export_content)
from services.llm_client import DeepSeekClient, QwenClient
from views.common import STATES, action, display_value, model_configs, display_context, available_channels
from views.guidance import next_button
from services.text_check_service import text_findings, expression_findings
from services import query_service as queries
from services.quota_service import quota_status, session_quota_status
from services.demo_service import live_models_enabled
from views.components import content_card, empty_state, state_table


def render(repo, product_id, operator, quota_repo=None, session_id=None):
    st.write("只使用已确认资料组织内容。每份内容保留输入快照，逐句审核后才能导出。")
    if not product_id:
        empty_state('准备好资料，就能生成第一份内容', '先导入来源，再确认名称与净含量。', '去准备产品资料', '产品资料', 'content:import')
        return
    current = queries.current_facts(repo, product_id)
    create_tab, history_tab = st.tabs(["① 生成内容", "② 审核与导出"])
    with create_tab:
        left, right = st.columns([3, 2])
        with left:
            st.subheader('1 · 选择要生成的内容')
            content_type = st.radio("内容类型", list(CONTENT_TYPES), format_func=CONTENT_TYPES.get, horizontal=True)
            context = st.selectbox('价格渠道', available_channels(repo, product_id), format_func=display_context, key='generate_channel')
            include_price = st.checkbox("加入该渠道价格", value=any(f['field']=='price_cent' and f['context']==context for f in current),
                                        key=f'include-price:{product_id}:{context}', help='未确认价格时可以先关闭，用名称和重量体验流程。')
            optional = st.multiselect("加入已确认的说明字段", ["ingredients_text", "usage_text", "storage_text"],
                                      default=["ingredients_text", "usage_text", "storage_text"], format_func=FIELDS.get)
            labels = {"template": "模板模式（不调用模型）", "deepseek": "DeepSeek 实时生成", "qwen": "通义千问实时生成"}
            st.markdown('**2 · 选择生成方式**')
            mode = st.radio("生成方式", list(labels), format_func=labels.get, horizontal=True)
            configs = model_configs()
            cfg = configs.get(mode)
            quota_repo = quota_repo if quota_repo is not None else repo
            quotas = quota_status(quota_repo)
            session_quota = session_quota_status(quota_repo, session_id) if session_id else None
            if session_quota:
                st.caption(f'本会话今日真实模型请求 {session_quota["used"]}/3 · 两家合计，重试也计数；模板不限。')
            with st.expander('今日模型调用额度 · 每天北京时间00:00重置'):
                for provider,label in (('deepseek','DeepSeek'),('qwen','通义千问')):
                    used = quotas[provider]['used']
                    st.progress(min(used/100,1.0), text=f'{label} · 已用 {used}/100，剩余 {quotas[provider]["remaining"]}')
            if mode == "template":
                st.caption("模板按确认资料直接填充，用于验证流程；不计为真实模型调用。")
            elif not live_models_enabled():
                st.info('管理员已关闭真实模型调用，请使用模板模式。')
            elif not cfg.api_key:
                st.info(f"尚未配置{labels[mode].replace('实时生成', '')}密钥。按 README 在本机填写 .streamlit/secrets.toml 后即可使用。")
            else:
                st.caption(f"模型：{cfg.name} · 输出仍需人工核对，不自动视为事实正确。")
        # Include only available optional facts; absent optional fields are never invented.
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
                    st.caption(f"{display_context(fact['context'])} · 字段修订 #{fact['fact_revision_id']}")
                if basis["missing"]:
                    st.warning("请先补齐或处理冲突：" + "、".join(FIELDS[f] for f in basis["missing"]))
                if basis["conflicts"]:
                    st.warning("所选字段存在未解决冲突，请到数据核对页处理。")
        quota_exhausted = mode in quotas and (quotas[mode]["remaining"] <= 0 or bool(session_quota and session_quota['remaining'] <= 0))
        if quota_exhausted:
            st.warning("本会话或所选模型今日额度已用完，请使用模板模式。")
        disabled = (not basis or bool(basis["missing"]) or
                    (mode != "template" and (not live_models_enabled() or not cfg.api_key or quota_exhausted)))
        if basis and basis['missing']:
            st.caption('有候选时去核对；完全没有候选时可直接补录。')
            for field in basis['missing']:
                pending = queries.has_pending_candidate(repo, product_id, field)
                if pending:
                    next_button('去核对' + FIELDS[field], '数据核对', 'content:quality:'+field)
                else:
                    def fill_missing(target=field):
                        st.session_state['focused_manual_field'] = target
                        st.session_state['next_product'] = product_id
                        st.session_state['pending_navigation'] = '产品资料'
                    st.button('补录' + FIELDS[field], key='content:fill:'+field, on_click=fill_missing)
        if st.button("生成一份草稿", type="primary", disabled=disabled, key="generate_draft"):
            request_key = uuid.uuid4().hex
            st.session_state["last_request_key"] = request_key
            with st.status('正在组织内容', expanded=True) as task:
                st.write('1/3 已收集本次生成参数和确认依据。')
                bar = st.progress(.2, text='2/3 正在生成；模型通常需要数十秒，网络重试可能更久。')
                ok, result = action(lambda: generate_content(repo, product_id, request_key, context, content_type, include_price,
                    mode, DeepSeekClient(cfg) if mode == "deepseek" else QwenClient(cfg) if mode == "qwen" else None,
                    ["product_name", "net_weight_g"] + selected, quota_repo=quota_repo, session_id=session_id), "草稿已保存，请在“审核与导出”中逐句核对。")
                if ok:
                    bar.progress(1.0, text='3/3 已完成输出校验并保存草稿。')
                    task.update(label='草稿已保存，等待人工审核', state='complete', expanded=False)
            if ok:
                st.session_state["focused_content"] = result["content_id"]
                st.rerun()
    with history_tab:
        st.subheader('阅读正文 → 提交审核 → 逐句核对 → 下载')
        st.caption('先选下方内容修订。审核与下载操作紧随正文，来源和历史保存在折叠详情中。')
        show_history = st.checkbox('包含历史修订', value=False, key='include_content_history')
        rows = queries.content_history(repo, product_id, show_history)
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
            empty_state('这里会保存你的第一份草稿', '切换“生成内容”，使用模板即可体验，无需模型密钥。',
                        '检查生成所需资料', '数据核对', 'history:quality')
        with st.expander("生成任务与失败记录"):
            jobs = queries.generation_jobs(repo, product_id)
            state_table(jobs)
            if any(j["state"] == "running" for j in jobs):
                st.warning("存在运行中任务，可能正在处理或因程序中断遗留。请先核查，确需重试时返回“生成内容”再次明确点击；原任务保留。")


def render_content(repo, row, operator):
    content_id = row["id"]
    modes = {'template': '模板模式', 'deepseek': 'DeepSeek', 'qwen': '通义千问', 'manual': '人工编辑'}
    st.caption(f"内容 #{content_id} · 修订 R{row['revision']} · {STATES[row['state']]} · {modes.get(row['mode'],row['mode'])} · {display_context(row['context'])}")
    content_card(row['title'], row['body'], row['state'])
    if row['state'] in ('draft', 'review'):
        st.warning('待人工审核草稿 · 请核对全部陈述，通过审核前不可对外使用。')
    for issue in expression_findings(row['title'], row['body'], json.loads(row['snapshot_json'])):
        from html import escape
        st.warning(issue['message'])
        st.markdown(f"**待核对表达：** <mark>{escape(issue['sentence'])}</mark>", unsafe_allow_html=True)
    basis = queries.content_basis(repo, row)
    valid = not basis["missing"] and basis["snapshot_hash"] == row["snapshot_hash"]
    body_issues = text_findings(row['title'], row['body'], basis['snapshot']) if not basis['missing'] else []
    for issue in body_issues:
        st.error(issue['message'])
        if issue['sentence']:
            from html import escape
            section = '标题' if issue['section'] == 'title' else '正文'
            st.markdown(f"**定位到{section}：** <mark>{escape(issue['sentence'])}</mark>", unsafe_allow_html=True)
    if body_issues:
        valid = False
        st.caption('请在下方“编辑为新修订”中修正正文后重新审核。')
    if basis['missing'] or basis['snapshot_hash'] != row['snapshot_hash'] or row["state"] == "stale":
        st.warning("这份内容的依据已变化或存在冲突。请到变更追踪页生成新修订或复查后重绑依据。")
        next_button('去查看变化与处理建议', '变更追踪', f'content:impact:{content_id}')
    with st.expander("输入快照、来源与审核记录"):
        snapshot = json.loads(row["snapshot_json"])
        st.json(snapshot)
        st.caption("快照 SHA-256：" + row["snapshot_hash"])
        state_table(queries.content_evidence(repo, content_id))
        st.dataframe(queries.content_reviews(repo, content_id), hide_index=True, width="stretch")
        st.dataframe(queries.content_exports(repo, content_id), hide_index=True, width="stretch")
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
        st.caption(f"本次下载仅包含当前内容 #{content_id} / R{row['revision']}，会保留一条导出记录；不会自动发布到外部平台。")
        from views.access_view import download_guard
        guard = download_guard()
        def checked_export():
            guard()
            return export_content(repo, content_id, operator)['text']
        # Deferred execution checks the database at the actual download request.
        st.download_button("校验依据并下载 TXT", data=checked_export,
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

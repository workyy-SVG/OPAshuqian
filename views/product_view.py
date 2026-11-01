import csv
import io
import streamlit as st
from config import ROOT, FIELDS
from services.import_service import preview_import, commit_import, add_manual
from views.common import action, fact_table, STATES, display_context
from views.guidance import next_button
from services import query_service as queries


def render(repo, product_id, operator):
    st.write("先选择一种收集方式；保存后进入待确认候选，人工核对后才用于生成。")
    from views.tutorial_view import flow_diagram
    flow_diagram([('选择来源','按分类选商品、上传CSV，或手动补录'),('预览并保存','确认SKU、版本和原文，保存为候选'),('去数据核对','对照可靠来源，逐项确认资料')])
    st.subheader('① 收集与保存资料')
    tabs = st.tabs(["公开食品资料", "CSV 导入", "手动补录", "来源与历史"])
    with tabs[1]:
        st.subheader('上传你已有的产品资料')
        st.caption('适合已有商品清单：下载模板 → 按行填写 → 上传预览 → 确认导入。')
        col1, col2 = st.columns([3, 1])
        with col1:
            upload = st.file_uploader("上传长表 CSV", type=["csv"], help="最大5MB、最多20000条；每行一条来源陈述，SKU按字符串处理。")
            encoding = st.selectbox("文件编码", ["utf-8-sig", "gb18030"], format_func=lambda v: "UTF-8（推荐）" if v == "utf-8-sig" else "GB18030（手动选择）")
        with col2:
            st.download_button("下载空白模板", (ROOT / "samples/template.csv").read_bytes(), "黔品智营资料模板.csv", "text/csv")
            st.download_button("下载拟制样例", (ROOT / "samples/products.csv").read_bytes(), "拟制样例.csv", "text/csv")
            import zipfile
            pack = io.BytesIO()
            with zipfile.ZipFile(pack, 'w', zipfile.ZIP_DEFLATED) as bundle:
                for path in (ROOT / 'samples/walkthrough').glob('*.csv'):
                    bundle.writestr(path.name, path.read_bytes())
                bundle.writestr('详细使用说明.md', (ROOT / 'docs/USER_GUIDE.md').read_bytes())
            st.download_button('下载分步体验资料包', pack.getvalue(), '黔品智营分步体验.zip', 'application/zip')
            if st.button("导入拟制演示样例", key="import_sample"):
                preview = preview_import((ROOT / "samples/products.csv").read_bytes())
                ok, result = action(lambda: commit_import(repo, preview, "拟制演示样例.csv"), "拟制样例已导入，请到数据核对页处理净含量冲突。")
                if ok:
                    st.rerun()
        if upload:
            ok, preview = action_preview(upload.getvalue(), encoding)
            if ok:
                if preview["errors"]:
                    for error in preview["errors"]:
                        st.error(error)
                else:
                    rows = preview["rows"]
                    st.caption(f"共 {len(rows)} 条来源记录 · {sum(bool(r['error']) for r in rows)} 条格式问题 · 仅预览，尚未写入")
                    st.dataframe([{k: v for k, v in r.items() if k not in ("fingerprint",)} for r in rows[:100]], hide_index=True, width="stretch")
                    if st.button("确认导入", type="primary"):
                        ok, result = action(lambda: commit_import(repo, preview, upload.name))
                        if ok:
                            st.session_state["notice"] = (f"{'已有相同批次，未重复导入。' if result['reused'] else '导入完成。'}"
                                f"批次 {result['source_id']}：候选 {result['candidates']}，重复 {result['duplicates']}，错误 {result['errors']}。")
                            st.rerun()
        st.caption("固定字段：product_name、net_weight_g、price_cent、ingredients_text、usage_text、storage_text。价格原文按元填写。")
    with tabs[2]:
        st.subheader('逐项补充包装或价目表信息')
        with st.expander("新增 SKU / 产品版本", expanded=not product_id):
            with st.form("new_product"):
                sku = st.text_input("SKU", placeholder="如 P001，保留前导零")
                version = st.text_input("产品版本", value="V1")
                if st.form_submit_button("保存产品对象"):
                    ok, new_id = action(lambda: repo.add_product(sku, version), "产品对象已保存。")
                    if ok:
                        st.session_state["next_product"] = new_id
                        st.rerun()
        if product_id:
            with st.form("manual_observation"):
                st.markdown('**1 · 填写包装或价目表上的信息**')
                field = st.selectbox("字段", list(FIELDS), format_func=FIELDS.get, help='选择你要补充的一项产品信息，每次保存一项。')
                raw = st.text_area("来源原文", placeholder='例如：200g、12.00，或包装上的配料说明', help="重量可填200g或0.2kg；金额填写元，例如12.00。")
                scope = st.selectbox('适用范围', ['general', 'retail', 'wholesale'], format_func=display_context,
                                     help='名称、净含量和说明选通用资料；价格选零售或批发。')
                custom_scope = st.text_input('其他价格渠道（可留空）', help='仅当价格属于其他渠道时填写，例如门店A。')
                context = custom_scope.strip() if field == 'price_cent' and custom_scope.strip() else scope
                st.markdown('**2 · 标明来源与补录原因**')
                source = st.text_input("来源说明", placeholder="例如包装标签、已核对价目表", help='帮助之后的审核人追溯这项说法从哪里来。')
                effective = st.text_input("适用日期（可留空）", placeholder="YYYY-MM-DD")
                reason = st.text_input("补录原因")
                if st.form_submit_button("保存为待确认候选", type="primary"):
                    ok, _ = action(lambda: add_manual(repo, product_id, field, raw, context, source, reason, operator, effective), "候选已保存，请到数据核对页确认。")
                    if ok:
                        st.rerun()
    with tabs[3]:
        st.subheader('查看资料来自哪里')
        sources = queries.sources(repo)
        if sources:
            st.dataframe(sources, hide_index=True, width="stretch")
            source_id = st.selectbox("查看批次", [s["id"] for s in sources], format_func=lambda i: f"批次 {i}")
            observations = queries.source_observations(repo, source_id)
            from views.components import state_table
            status_filter = st.selectbox('来源记录状态', ['全部']+list(dict.fromkeys(r['state'] for r in observations)),
                                         format_func=lambda v:STATES.get(v,v))
            filtered = [r for r in observations if status_filter=='全部' or r['state']==status_filter]
            with st.expander(f'记录明细 · {len(filtered)} 条', expanded=False):
                state_table(filtered)
            source = queries.source_record(repo, source_id)
            from pathlib import Path
            path = Path(source["stored_path"])
            if not path.is_absolute():
                path = repo.settings.runtime_dir / path
            if path.is_file():
                from views.access_view import download_guard
                guard = download_guard()
                def read_source():
                    guard()
                    return path.read_bytes()
                st.download_button("下载本批原始资料", read_source, f"source-{source_id}.csv", "text/csv")
            import re
            snapshots = {match[1] for row in observations
                         if (match := re.fullmatch(r'https://world\.openfoodfacts\.org/product/[0-9]{8,14}#snapshot=([a-f0-9]{64})', row['source_locator']))}
            for digest in sorted(snapshots):
                snapshot_path = repo.settings.runtime_dir / 'sources' / f'off-{digest}.json'
                if snapshot_path.is_file():
                    from views.access_view import download_guard
                    snapshot_guard = download_guard()
                    def read_snapshot(path=snapshot_path, expected=digest, guard=snapshot_guard):
                        import hashlib
                        from repository import BusinessError
                        guard()
                        payload = path.read_bytes()
                        if hashlib.sha256(payload).hexdigest() != expected:
                            raise BusinessError('来源快照校验失败。')
                        return payload
                    st.download_button('下载食品来源JSON快照', read_snapshot,
                                       f'OpenFoodFacts-{digest[:12]}.json', 'application/json', key=f'off-snapshot:{digest}')
            errors = [r for r in observations if r["state"] == "error"]
            if errors:
                buffer = io.StringIO(newline="")
                writer = csv.DictWriter(buffer, ["row_no", "field", "raw", "error"])
                writer.writeheader()
                writer.writerows({k: r[k] for k in writer.fieldnames} for r in errors)
                from views.access_view import download_guard
                error_guard = download_guard()
                payload = buffer.getvalue().encode('utf-8-sig')
                def read_errors():
                    error_guard()
                    return payload
                st.download_button("下载错误行清单", read_errors, f"errors-{source_id}.csv", "text/csv")
        else:
            st.info("尚无导入记录。可先导入拟制演示样例。")
    with tabs[0]:
        from views.food_facts_view import render as render_food_facts
        render_food_facts(repo)
    if product_id:
        st.subheader('② 检查结果并进入核对')
        next_button('下一步：去核对并确认资料', '数据核对', 'product:quality')
        with st.expander('当前已确认资料（生成使用这些信息）', expanded=False):
            fact_table(repo, product_id)


def action_preview(data, encoding):
    from repository import BusinessError
    try:
        return True, preview_import(data, encoding)
    except BusinessError as exc:
        st.error(str(exc))
        return False, None

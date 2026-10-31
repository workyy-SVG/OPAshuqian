import csv
import io
import streamlit as st
from config import ROOT, FIELDS
from services.import_service import preview_import, commit_import, add_manual
from views.common import action, fact_table, STATES


def render(repo, product_id, operator):
    st.write("先保留来源，再核对事实。上传成功的资料会进入候选区，确认后才用于内容。")
    tabs = st.tabs(["CSV 导入", "手动补录", "来源与历史"])
    with tabs[0]:
        col1, col2 = st.columns([3, 1])
        with col1:
            upload = st.file_uploader("上传长表 CSV", type=["csv"], help="最大5MB；每行一条来源陈述，SKU按字符串处理。")
            encoding = st.selectbox("文件编码", ["utf-8-sig", "gb18030"], format_func=lambda v: "UTF-8（推荐）" if v == "utf-8-sig" else "GB18030（手动选择）")
        with col2:
            st.download_button("下载空白模板", (ROOT / "samples/template.csv").read_bytes(), "黔品智营资料模板.csv", "text/csv")
            st.download_button("下载拟制样例", (ROOT / "samples/products.csv").read_bytes(), "拟制样例.csv", "text/csv")
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
    with tabs[1]:
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
                field = st.selectbox("字段", list(FIELDS), format_func=FIELDS.get)
                raw = st.text_area("来源原文", help="重量可填200g或0.2kg；金额填写元，例如12.00。")
                context = st.text_input("适用范围", value="general", help="价格填retail等明确渠道，其余字段填general。")
                source = st.text_input("来源说明", placeholder="例如包装标签、已核对价目表")
                effective = st.text_input("适用日期（可留空）", placeholder="YYYY-MM-DD")
                reason = st.text_input("补录原因")
                if st.form_submit_button("保存为待确认候选", type="primary"):
                    ok, _ = action(lambda: add_manual(repo, product_id, field, raw, context, source, reason, operator, effective), "候选已保存，请到数据核对页确认。")
                    if ok:
                        st.rerun()
    with tabs[2]:
        sources = repo.all("""SELECT s.id,s.original_name,s.sha256,s.created_at,COUNT(o.id) AS total,
            SUM(o.state='error') AS errors FROM sources s LEFT JOIN observations o ON o.source_id=s.id GROUP BY s.id ORDER BY s.id DESC""")
        if sources:
            st.dataframe(sources, hide_index=True, width="stretch")
            source_id = st.selectbox("查看批次", [s["id"] for s in sources], format_func=lambda i: f"批次 {i}")
            observations = repo.all("SELECT * FROM observations WHERE source_id=? ORDER BY row_no", (source_id,))
            st.dataframe([{**r, "state": STATES.get(r["state"], r["state"])} for r in observations], hide_index=True, width="stretch")
            source = repo.one("SELECT * FROM sources WHERE id=?", (source_id,))
            from pathlib import Path
            path = Path(source["stored_path"])
            if not path.is_absolute():
                path = repo.settings.runtime_dir / path
            if path.is_file():
                st.download_button("下载本批原始资料", path.read_bytes(), f"source-{source_id}.csv", "text/csv")
            errors = [r for r in observations if r["state"] == "error"]
            if errors:
                buffer = io.StringIO(newline="")
                writer = csv.DictWriter(buffer, ["row_no", "field", "raw", "error"])
                writer.writeheader()
                writer.writerows({k: r[k] for k in writer.fieldnames} for r in errors)
                st.download_button("下载错误行清单", buffer.getvalue().encode("utf-8-sig"), f"errors-{source_id}.csv", "text/csv")
        else:
            st.info("尚无导入记录。可先导入拟制演示样例。")
    if product_id:
        st.subheader("当前已确认资料")
        fact_table(repo, product_id)


def action_preview(data, encoding):
    from repository import BusinessError
    try:
        return True, preview_import(data, encoding)
    except BusinessError as exc:
        st.error(str(exc))
        return False, None

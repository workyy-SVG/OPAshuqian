import csv
import io
import streamlit as st
from config import ROOT, FIELDS
from services.import_service import preview_import, commit_import, add_manual, create_basic_product, add_manual_batch
from views.common import action, fact_table, STATES, display_context
from views.guidance import next_button
from services import query_service as queries


def render(repo, product_id, operator):
    st.caption('选择录入方式，保存为待确认候选后进入数据核对。')
    if st.session_state.get('focused_new_product', False):
        render_new_product(repo)
        return
    focused_field = st.session_state.get('focused_manual_field')
    if focused_field and product_id:
        render_focused_manual(repo, product_id, operator, focused_field)
        return
    manual_tab, csv_tab, public_tab, source_tab = st.tabs(
        ["手动补录", "CSV 导入", "公开食品资料", "来源与历史"], key='product_workspace_tab', on_change='rerun')
    tabs = [public_tab, csv_tab, manual_tab, source_tab]
    with tabs[1]:
        st.subheader('上传你已有的产品资料')
        st.caption('适合已有商品清单：下载模板 → 按行填写 → 上传预览 → 确认导入。')
        col1, col2 = st.columns([2, 1], gap='large')
        with col1:
            upload = st.file_uploader("上传 CSV", type=["csv"], help="支持中文一行一商品模板和字段长表；最大5MB、最多20000条，SKU按字符串处理。")
            with st.expander('文件编码与字段说明'):
                encoding = st.selectbox("文件编码", ["utf-8-sig", "gb18030"], format_func=lambda v: "UTF-8（推荐）" if v == "utf-8-sig" else "GB18030（手动选择）")
                st.caption('重量填写200g或0.2kg；价格按元填写，例如12.00。')
        with col2:
            st.download_button("下载空白模板", (ROOT / "samples/template.csv").read_bytes(), "黔品智营资料模板.csv", "text/csv")
            wide = 'SKU,产品版本,商品名称,净含量,零售价格,配料,使用方法,储存说明,来源说明,来源位置,适用日期\n001,V1,示例商品,200g,12.00,,,,包装标签,包装正面,\n'
            st.download_button('下载中文一行一商品模板', wide.encode('utf-8-sig'), '黔品智营中文模板.csv', 'text/csv')
            st.download_button("下载拟制样例", (ROOT / "samples/products.csv").read_bytes(), "拟制样例.csv", "text/csv")
            import zipfile
            pack = io.BytesIO()
            with zipfile.ZipFile(pack, 'w', zipfile.ZIP_DEFLATED) as bundle:
                for path in (ROOT / 'samples/walkthrough').glob('*.csv'):
                    bundle.writestr(path.name, path.read_bytes())
                bundle.writestr('详细使用说明.md', (ROOT / 'docs/USER_GUIDE.md').read_bytes())
            st.download_button('下载分步体验资料包', pack.getvalue(), '黔品智营分步体验.zip', 'application/zip')
            if st.button("加载可选测试资料", key="import_sample", help='这些资料为拟制测试数据，不会自动确认任何事实。'):
                preview = preview_import((ROOT / "samples/products.csv").read_bytes())
                ok, result = action(lambda: commit_import(repo, preview, "拟制演示样例.csv"), "拟制样例已导入，请到数据核对页处理净含量冲突。")
                if ok:
                    target = next((p['id'] for p in result['products'] if p['sku']=='P001' and p['version']=='V1'), None)
                    st.session_state['next_product'] = target or result['product_ids'][0]
                    st.session_state['pending_navigation'] = '数据核对'
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
                            st.session_state['last_import_products'] = result['products']
                            st.session_state["notice"] = (f"{'已有相同批次，未重复导入。' if result['reused'] else '导入完成。'}"
                                f"批次 {result['source_id']}：候选 {result['candidates']}，重复 {result['duplicates']}，错误 {result['errors']}。")
                            st.rerun()
        imported = st.session_state.get('last_import_products', [])
        if imported:
            st.markdown('**本批商品 · 选择一个继续核对**')
            mapping = {p['id']: p for p in imported}
            chosen = st.selectbox('本批导入商品', list(mapping), format_func=lambda i:
                                  f"{mapping[i]['sku']} · {mapping[i]['version']} · {mapping[i]['candidate_count']}条候选")
            if st.button('进入所选商品核对', key='open_imported_product', type='primary'):
                st.session_state['next_product'] = chosen
                st.session_state['pending_navigation'] = '数据核对'
                st.session_state.pop('last_import_products', None)
                st.rerun()
        st.caption("固定字段：product_name、net_weight_g、price_cent、ingredients_text、usage_text、storage_text。价格原文按元填写。")
    with tabs[2]:
        st.subheader('录入当前商品的包装或价目表资料')
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
            with st.container(border=True):
                st.markdown('**基础资料 · 可一次保存多项**')
                with st.form(f'basic_product_observations:{product_id}'):
                    left, right = st.columns(2)
                    name = left.text_input('产品名称')
                    weight = right.text_input('净含量', placeholder='例如：200g')
                    ingredients = st.text_area('配料原文（可留空）')
                    left, right = st.columns(2)
                    price = left.text_input('零售价格（可留空，按元填写）', placeholder='例如：12.00')
                    source = right.text_input('共同来源说明', placeholder='例如：产品包装标签')
                    reason = st.text_input('补录原因', value='首次录入产品基础资料')
                    if st.form_submit_button('保存以上资料为待确认候选', type='primary'):
                        ok, _ = action(lambda: add_manual_batch(repo, product_id,
                            {'product_name':name,'net_weight_g':weight,'ingredients_text':ingredients,'price_cent':price},
                            source, reason, operator))
                        if ok:
                            st.session_state['pending_navigation'] = '数据核对'
                            st.rerun()
            with st.expander('单项补录 / 其他渠道 / 适用日期', expanded=False):
                render_single_manual(repo, product_id, operator)
        else:
            st.info('点击侧栏“＋ 新建商品”，先录入商品名称、净含量和来源。')
    with tabs[3]:
        render_sources(repo)
    with tabs[0]:
        from views.food_facts_view import render as render_food_facts
        render_food_facts(repo)
    if product_id:
        next_button('下一步：去核对并确认资料', '数据核对', 'product:quality')
        with st.expander('当前产品的完成情况', expanded=False):
            from services.experience_service import overview
            from views.guidance import product_overview
            product_overview(overview(repo, product_id))
        with st.expander('当前已确认资料（生成使用这些信息）', expanded=False):
            fact_table(repo, product_id)


def render_single_manual(repo, product_id, operator):
    # A form batches changes; keep the controlling field outside so channels update immediately.
    field = st.selectbox("字段", list(FIELDS), format_func=FIELDS.get, key='manual_field', help='选择你要补充的一项产品信息，每次保存一项。')
    with st.form(f'manual_observation:{product_id}:{field}'):
        raw = st.text_area("来源原文", placeholder='例如：200g、12.00，或包装上的配料说明', help="重量可填200g或0.2kg；金额填写元，例如12.00。")
        if field == 'price_cent':
            scope = st.selectbox('价格渠道', ['retail', 'wholesale'], format_func=display_context)
            custom_scope = st.text_input('其他价格渠道（可留空）', help='例如门店A。')
            context = custom_scope.strip() or scope
        else:
            context = 'general'
        st.markdown('**2 · 标明来源与补录原因**')
        source = st.text_input("来源说明", placeholder="例如包装标签、已核对价目表", help='帮助之后的审核人追溯这项说法从哪里来。')
        effective = st.text_input("适用日期（可留空）", placeholder="YYYY-MM-DD")
        reason = st.text_input("补录原因")
        if st.form_submit_button("保存为待确认候选", type="primary"):
            ok, _ = action(lambda: add_manual(repo, product_id, field, raw, context, source, reason, operator, effective), "候选已保存，请到数据核对页确认。")
            if ok:
                st.rerun()


def render_sources(repo):
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


def action_preview(data, encoding):
    from repository import BusinessError
    try:
        return True, preview_import(data, encoding)
    except BusinessError as exc:
        st.error(str(exc))
        return False, None


def render_new_product(repo):
    st.subheader('新建商品')
    st.caption('先录入名称、净含量和来源；保存为待确认候选，不会自动成为事实。')
    with st.form('guided_new_product'):
        name = st.text_input('商品名称', placeholder='例如：贵州刺梨汁')
        weight = st.text_input('净含量', placeholder='例如：200g')
        source = st.text_input('资料来源', placeholder='例如：产品包装标签')
        with st.expander('高级编号设置（可选）'):
            sku = st.text_input('SKU（留空自动生成）')
            version = st.text_input('产品版本', value='V1')
        submitted = st.form_submit_button('保存并进入数据核对', type='primary')
    if submitted:
        ok, result = action(lambda: create_basic_product(repo, name, weight, source, sku, version),
                            '商品已创建，名称和净含量等待核对。')
        if ok:
            st.session_state.pop('focused_new_product', None)
            st.session_state['next_product'] = result['product_id']
            st.session_state['pending_navigation'] = '数据核对'
            st.rerun()
    if st.button('返回产品资料', key='cancel_new_product'):
        st.session_state.pop('focused_new_product', None)
        st.rerun()


def render_focused_manual(repo, product_id, operator, field):
    st.subheader('补录' + FIELDS.get(field, field))
    st.caption('保存后返回同一商品的数据核对页。')
    with st.form(f'focused_manual_entry:{product_id}:{field}'):
        raw = st.text_area('来源原文')
        context = st.selectbox('价格渠道', ['retail','wholesale'], format_func=display_context) if field=='price_cent' else 'general'
        source = st.text_input('来源说明', placeholder='例如：产品包装标签')
        reason = st.text_input('补录原因', value='补齐生成所需资料')
        submitted = st.form_submit_button('保存并返回核对', type='primary')
    if submitted:
        ok, _ = action(lambda: add_manual(repo, product_id, field, raw, context, source, reason, operator))
        if ok:
            st.session_state.pop('focused_manual_field', None)
            st.session_state['next_product'] = product_id
            st.session_state['pending_navigation'] = '数据核对'
            st.rerun()
    if st.button('取消补录', key='cancel_focused_manual'):
        st.session_state.pop('focused_manual_field', None)
        st.rerun()

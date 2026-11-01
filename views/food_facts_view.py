"""Explicit search and preview; no network calls merely from opening a tab."""
import streamlit as st

from repository import BusinessError
from services.food_facts_service import lookup, candidate_preview, import_product, ATTRIBUTION
from views.common import action


@st.cache_data(ttl=3600, max_entries=256, show_spinner=False)
def cached_lookup(query, kind):
    return lookup(query, kind)


def render(repo):
    st.subheader('从公开食品资料开始体验')
    st.write('① 输入条码或商品名 → ② 选择结果并核对预览 → ③ 导入候选 → ④ 到「数据核对」人工确认。')
    st.info('只补充数据库实际提供的名称、明确重量和配料。价格请按自己的销售渠道补录；营养数据仅作来源参考。')
    with st.form('food_search'):
        kind = st.radio('查询方式', ['barcode', 'name'], horizontal=True,
                        format_func=lambda k: '商品条码' if k == 'barcode' else '商品名称')
        query = st.text_input('条码或名称', placeholder='例如包装上的13位条码，或输入 Nutella', max_chars=100)
        submitted = st.form_submit_button('查询公开商品资料', type='primary')
    if submitted:
        st.session_state.pop('food_results', None)
        st.session_state.pop('food_selected', None)
        try:
            with st.spinner('正在查询 Open Food Facts…'):
                st.session_state['food_results'] = cached_lookup(query.strip(), kind)
        except BusinessError as exc:
            st.error(str(exc))
    results = st.session_state.get('food_results', [])
    if submitted and not results:
        st.info('没有可展示的结果。可以换条码/名称，或回到CSV页使用拟制演示样例。')
    if results:
        selected = st.selectbox('选择查询结果', range(len(results)), key='food_selected',
                                format_func=lambda i: f"{results[i].get('product_name_zh') or results[i].get('product_name') or '未命名商品'} · {results[i]['code']}")
        product = results[selected]
        st.caption(f"品牌参考：{product.get('brands') or '来源未提供'} · 包装规格：{product.get('quantity') or '来源未提供'}")
        st.link_button('在 Open Food Facts 查看来源', f"https://world.openfoodfacts.org/product/{product['code']}")
        with st.expander('查看本次来源原始字段（含营养信息）'):
            st.json(product)
        code = product['code']
        with st.form(f'food_candidate:{code}'):
            sku = st.text_input('导入到SKU', value=f'OFF-{code}', max_chars=80,
                                help='默认创建独立演示SKU。只有核实为同一商品后，才填写已有SKU。')
            version = st.text_input('产品版本', value='V1', max_chars=80)
            try:
                preview = candidate_preview(product, sku, version)
                st.dataframe([{'字段': row['field_key'], '来源原文': row['raw_value'],
                               '格式问题': row['error']} for row in preview['rows']], hide_index=True, width='stretch')
                invalid = any(row['error'] for row in preview['rows'])
            except BusinessError as exc:
                st.warning(str(exc))
                invalid = True
            acknowledged = st.checkbox('已核对商品身份，理解这些资料将作为待确认候选')
            save = st.form_submit_button('导入为待确认候选', disabled=invalid)
        if save:
            if not acknowledged:
                st.warning('请先核对商品身份并勾选确认。')
            else:
                ok, result = action(lambda: import_product(repo, product, sku, version))
                if ok:
                    st.session_state['notice'] = (f"{'已有相同批次，未重复导入。' if result['reused'] else '候选已导入。'}"
                                                   f"批次 {result['source_id']}，请到数据核对页选择SKU {sku} 处理。")
                    st.rerun()
    st.caption(f'数据来源：{ATTRIBUTION}。缓存1小时，每次最多显示5个结果；公开数据需与实物包装核对。')
    st.markdown('[数据许可与使用条款](https://world.openfoodfacts.org/terms-of-use)')

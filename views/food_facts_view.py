"""Explicit search and preview; no network calls merely from opening a tab."""
import streamlit as st
from config import FIELDS

from repository import BusinessError
from services.food_facts_service import lookup, browse, CATEGORIES, candidate_preview, import_product, ATTRIBUTION
from views.common import action


@st.cache_data(ttl=3600, max_entries=256, show_spinner=False)
def cached_lookup(query, kind):
    return lookup(query, kind)


@st.cache_data(ttl=3600, max_entries=128, show_spinner=False)
def cached_catalog(category, subcategory, page):
    return browse(category, subcategory, page)


def select_catalog_product(product):
    st.session_state['food_results'] = [product]
    st.session_state.pop('food_selected', None)
    st.session_state['food_origin'] = '目录选择'


def catalog():
    st.markdown('**1 · 先选分类，再浏览商品**')
    left,right = st.columns(2)
    category = left.selectbox('商品大类', list(CATEGORIES), key='catalog_category')
    subcategory = right.selectbox('细分类', list(CATEGORIES[category]), key='catalog_subcategory:'+category)
    identity = (category,subcategory)
    if st.session_state.get('catalog_identity') != identity:
        st.session_state['catalog_identity'] = identity
        st.session_state['catalog_page'] = 1
        st.session_state.pop('catalog_result', None)
    page = st.session_state.get('catalog_page',1)
    if st.button('浏览这个分类', key='catalog_load', type='primary'):
        load_catalog(category,subcategory,page)
    result = st.session_state.get('catalog_result')
    if not result:
        st.info('不需要条码：选好分类后点“浏览这个分类”，即可挑选商品。')
        return
    total = result['total']
    st.caption(f"{category} / {subcategory} · 第{page}页 · "+(f'数据源报告约{total}条' if total is not None else '总数由数据源提供')+'；每页最多12项')
    products = result['products']
    if not products:
        st.info('本页没有可展示的商品。可换分类或返回上一页。')
    columns = st.columns(2)
    for index, product in enumerate(products):
        with columns[index%2]:
            with st.container(border=True):
                st.markdown('**'+str(product.get('product_name_zh') or product.get('product_name') or '未命名商品')+'**')
                st.caption(f"条码 {product['code']} · {product.get('brands') or '品牌未提供'}")
                st.write('包装：'+str(product.get('quantity') or '未提供'))
                st.button('选择此商品，查看候选预览', key=f"catalog_pick:{index}:{product['code']}",
                          on_click=select_catalog_product, args=(product,))
    prev,next_col = st.columns(2)
    if prev.button('上一页', disabled=page<=1, key='catalog_prev'):
        if load_catalog(category,subcategory,page-1):
            st.rerun()
    if next_col.button('下一页', disabled=not result['has_next'] or page>=1000, key='catalog_next'):
        if load_catalog(category,subcategory,page+1):
            st.rerun()
    st.caption('目录是公开数据库的分类分页视图，尚未导入你的产品。只在你选择并确认后保存候选，不会把全库直接灌入工作区。')


def load_catalog(category, subcategory, page):
    try:
        with st.spinner('正在加载分类目录…'):
            result = cached_catalog(category,subcategory,page)
        st.session_state['catalog_result'] = result
        st.session_state['catalog_page'] = page
        return True
    except BusinessError as exc:
        st.error(str(exc))
        return False


def render(repo):
    st.subheader('选商品 → 看资料 → 导入候选')
    st.write('不清楚条码时，直接按分类浏览。知道具体商品时，也可以精确查询。')
    st.info('只补充数据库实际提供的名称、明确重量和配料。价格请按自己的销售渠道补录；营养数据仅作来源参考。')
    catalog_tab, search_tab = st.tabs(['按分类挑选商品','条码 / 名称查询'])
    with catalog_tab:
        catalog()
    with search_tab, st.form('food_search'):
        kind = st.radio('查询方式', ['barcode', 'name'], horizontal=True,
                        format_func=lambda k: '商品条码' if k == 'barcode' else '商品名称')
        query = st.text_input('条码或名称', placeholder='例如包装上的13位条码，或输入 Nutella', max_chars=100)
        submitted = st.form_submit_button('查询公开商品资料', type='primary')
    if submitted:
        st.session_state.pop('food_results', None)
        st.session_state.pop('food_selected', None)
        st.session_state['food_origin'] = '精确查询'
        try:
            with st.spinner('正在查询 Open Food Facts…'):
                st.session_state['food_results'] = cached_lookup(query.strip(), kind)
        except BusinessError as exc:
            st.error(str(exc))
    results = st.session_state.get('food_results', [])
    if submitted and not results:
        st.info('没有可展示的结果。可以换条码/名称，或回到CSV页使用拟制演示样例。')
    if results:
        st.divider()
        st.subheader('2 · 当前选中商品：预览后再保存')
        st.caption('以下商品来自'+st.session_state.get('food_origin','精确查询')+'；切换分类不会悄悄更换它，请以这里的商品名称和条码为准。')
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
                st.dataframe([{'字段': FIELDS[row['field_key']], '来源原文': row['raw_value'],
                               '格式问题': row['error']} for row in preview['rows']], hide_index=True, width='stretch')
                invalid = any(row['error'] for row in preview['rows'])
                provided = {row['field_key'] for row in preview['rows'] if row['raw_value'] and not row['error']}
                missing = [FIELDS[key] for key in ('product_name', 'net_weight_g', 'ingredients_text') if key not in provided]
                if missing:
                    st.warning('来源缺失或无法解析：' + '、'.join(missing) + '。请通过CSV或手工补录，核对后再确认。')
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
                    product_row = next((p for p in repo.products() if p['sku']==sku.strip() and p['version']==version.strip()), None)
                    if product_row:
                        st.session_state['next_product'] = product_row['id']
                    st.session_state['notice'] = (f"{'已有相同批次，未重复导入。' if result['reused'] else '候选已导入。'}"
                                                   f"批次 {result['source_id']}，请到数据核对页选择SKU {sku} 处理。")
                    st.rerun()
    st.caption(f'数据来源：{ATTRIBUTION}。缓存1小时；名称查询最多5项，分类目录每页最多12项；公开数据需与实物包装核对。')
    st.markdown('[数据许可与使用条款](https://world.openfoodfacts.org/terms-of-use)')

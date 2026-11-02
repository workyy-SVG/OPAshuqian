"""Explicit remote discovery and immediate, isolated candidate previews."""
import streamlit as st
import requests
from io import BytesIO
from PIL import Image, ImageOps, UnidentifiedImageError
from datetime import datetime
from zoneinfo import ZoneInfo
from config import FIELDS, Settings
from repository import BusinessError
from services.food_facts_service import lookup, browse, CATEGORIES, candidate_preview, import_product, ATTRIBUTION
from services.food_facts_service import product_image_url, USER_AGENT
from views.common import action


@st.cache_data(ttl=900, max_entries=128, show_spinner=False)
def cached_product_photo(url):
    """Bound downloads and normalize packaging to an uncropped white display area."""
    try:
        with requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=(3, 5),
                          stream=True, allow_redirects=False) as response:
            if response.status_code != 200:
                return None
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > 4 * 1024 * 1024:
                    return None
        with Image.open(BytesIO(content)) as original:
            if original.width * original.height > 12_000_000:
                return None
            photo = ImageOps.exif_transpose(original).convert('RGBA')
            photo.thumbnail((340, 400))
            canvas = Image.new('RGB', (380, 440), 'white')
            canvas.paste(photo, ((380-photo.width)//2, (440-photo.height)//2), photo)
            output = BytesIO()
            canvas.save(output, format='PNG')
            return output.getvalue()
    except (requests.RequestException, OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        return None


def product_photo(product):
    url = product_image_url(product)
    photo = cached_product_photo(url) if url else None
    if photo:
        st.image(photo, width='stretch')
        st.caption('商品包装图 · Open Food Facts')
        st.link_button('查看原图 ↗', url)
    else:
        st.markdown('''<div style="min-height:180px;border-radius:16px;background:#f4f7f5;
            border:1px dashed #a5bdb3;display:flex;flex-direction:column;align-items:center;
            justify-content:center;color:#496458;padding:16px;text-align:center">
            <span style="font-size:44px" aria-hidden="true">▧</span>
            <strong>替代图</strong><span style="font-size:13px;margin-top:8px">
            暂无可用实物图<br>此处为占位示意，非商品包装</span></div>''', unsafe_allow_html=True)


@st.cache_data(ttl=3600, max_entries=256, show_spinner=False)
def cached_lookup(query, kind):
    return lookup(query, kind)


def cached_catalog(category, subcategory, page):
    return browse(category, subcategory, page, cache_dir=Settings.from_env().runtime_dir / 'food-catalog-cache')


def product_label(product):
    name = product.get('product_name_zh') or product.get('product_name') or '未命名商品'
    return f"{name} · {product.get('brands') or '品牌未提供'} · {product.get('quantity') or '规格未提供'} · {product['code']}"


def close_preview():
    st.session_state['food_preview_open'] = False


def open_preview():
    st.session_state['food_preview_open'] = True


def select_catalog_product(product, origin='分类目录'):
    st.session_state['food_preview_product'] = product
    st.session_state['food_origin'] = origin
    open_preview()


def load_catalog(category, subcategory, page, prefix='catalog'):
    try:
        with st.spinner('正在加载 Open Food Facts 商品列表…'):
            result = cached_catalog(category, subcategory, page)
        st.session_state[prefix + '_result'] = result
        st.session_state[prefix + '_page'] = page
        st.session_state.pop(prefix + '_error', None)
        return True
    except BusinessError as exc:
        st.session_state[prefix + '_error'] = str(exc)
        return False


def catalog(prefix='catalog', show_cards=True):
    st.markdown('**选择分类 → 加载商品列表 → 选择商品预览**')
    left, right = st.columns(2)
    category = left.selectbox('商品大类', list(CATEGORIES), key=prefix + '_category')
    subcategory = right.selectbox('细分类', list(CATEGORIES[category]), key=prefix + '_subcategory:' + category)
    if category == '水饮':
        st.caption('建议先选饮用水、果汁或茶饮料等细分类；“饮料与饮用水”覆盖全库，加载可能较慢。')
    identity = (category, subcategory)
    if st.session_state.get(prefix + '_identity') != identity:
        st.session_state[prefix + '_identity'] = identity
        st.session_state[prefix + '_page'] = 1
        st.session_state.pop(prefix + '_result', None)
        st.session_state.pop(prefix + '_error', None)
    page = st.session_state.get(prefix + '_page', 1)
    if st.button('浏览这个分类' if show_cards else '加载可选商品', key=prefix + '_load', type='primary'):
        load_catalog(category, subcategory, page, prefix)
    error = st.session_state.get(prefix + '_error')
    if error:
        st.warning(error)
        st.info('可以点击加载按钮重试，或换一个分类；已有商品列表仍可选择。也可使用CSV或手工补录。')
    result = st.session_state.get(prefix + '_result')
    if not result:
        if not error:
            st.info('无需输入条码或商品全名，加载分类后直接在列表中选择。')
        return
    # A failed page request retains the last successful page and its actual label.
    page = result['page']
    total = result['total']
    st.caption(f"{category} / {subcategory} · 第{page}页 · " +
               (f'数据源报告约{total}条' if total is not None else '为加快加载，不统计全库总数') + '；每页最多12项')
    if result.get('saved_at'):
        saved = datetime.fromtimestamp(result['saved_at'], ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
        if result.get('stale'):
            st.warning('上游暂时不可用，正在展示同一分类、同一页最近成功获取的真实缓存。')
        st.caption(f'资料获取时间：{saved}（北京时间）' + (' · 缓存资料，请按实物复核' if result.get('cached') else ' · 本次接口返回'))
    products = result['products']
    if products:
        selected = st.selectbox('从本页商品列表选择', range(len(products)), index=None,
                                placeholder='展开列表直接选，也可输入列表中的名称筛选',
                                format_func=lambda i: product_label(products[i]),
                                key=f'{prefix}_choice:{category}:{subcategory}:{page}')
        chosen = products[selected] if selected is not None else None
        st.button('查看所选商品的候选预览', key=prefix + '_preview', disabled=chosen is None,
                  on_click=select_catalog_product, args=(chosen, '分类商品列表'))
        st.caption('只筛选本页已加载商品；找不到时可翻页、换细分类，或使用名称搜索。')
    else:
        st.info('本页没有可展示的商品。可换分类或返回上一页。')
    if show_cards:
        columns = st.columns(2)
        for index, product in enumerate(products):
            with columns[index % 2], st.container(border=True):
                details, picture = st.columns([3, 2], vertical_alignment='center')
                with details:
                    st.write('**' + str(product.get('product_name_zh') or product.get('product_name') or '未命名商品') + '**')
                    st.caption(f"条码 {product['code']} · {product.get('brands') or '品牌未提供'}")
                    st.write('包装：' + str(product.get('quantity') or '未提供'))
                with picture:
                    product_photo(product)
                st.button('选择此商品，查看候选预览', key=f"catalog_pick:{index}:{product['code']}",
                          on_click=select_catalog_product, args=(product,))
    prev, next_col = st.columns(2)
    if prev.button('上一页', disabled=page <= 1, key=prefix + '_prev'):
        load_catalog(category, subcategory, page - 1, prefix)
        st.rerun()
    if next_col.button('下一页', disabled=not result['has_next'] or page >= 1000, key=prefix + '_next'):
        load_catalog(category, subcategory, page + 1, prefix)
        st.rerun()
    st.caption('分类和商品资料由公开数据库提供，可能分类不准或字段不完整；选择仅预览，核对后才导入。')


def search():
    kind = st.radio('查询方式', ['list', 'barcode', 'name'], key='food_search_kind', horizontal=True,
                    format_func=lambda k: {'list': '从商品列表选择（无需输入）', 'barcode': '商品条码', 'name': '商品名称'}[k])
    if kind == 'list':
        catalog('quick_catalog', show_cards=False)
        return
    with st.form('food_search'):
        query = st.text_input('条码或名称', placeholder='包装上的数字条码' if kind == 'barcode' else '输入两个字以上关键词，无需完整商品名称',
                              max_chars=100, key='food_query:' + kind)
        submitted = st.form_submit_button('查询公开商品资料', type='primary')
    if submitted:
        st.session_state.pop('food_results', None)
        st.session_state.pop('food_search_error', None)
        st.session_state.pop('food_selected', None)
        try:
            with st.spinner('正在查询 Open Food Facts…'):
                st.session_state['food_results'] = cached_lookup(query.strip(), kind)
            st.session_state['food_result_kind'] = kind
        except BusinessError as exc:
            st.session_state['food_search_error'] = str(exc)
    if st.session_state.get('food_search_error'):
        st.warning(st.session_state['food_search_error'])
        st.info('这次查询未成功，不代表没有该商品。可重试，或切换“从商品列表选择（无需输入）”按分类挑选。')
    results = st.session_state.get('food_results', []) if st.session_state.get('food_result_kind') == kind else []
    if submitted and not results and not st.session_state.get('food_search_error'):
        st.info('没有找到匹配商品。可换关键词、按分类选商品，或使用CSV与手工补录。')
    if results:
        selected = st.selectbox('选择查询结果', range(len(results)), key='food_selected',
                                format_func=lambda i: product_label(results[i]))
        with st.columns([1, 2])[0]:
            product_photo(results[selected])
        st.button('查看查询商品的候选预览', key='search_preview', on_click=select_catalog_product,
                  args=(results[selected], '条码 / 名称查询'))


@st.dialog('商品候选预览 · 核对后再导入', width='large', on_dismiss=close_preview)
def preview_dialog(repo, product):
    st.subheader(str(product.get('product_name_zh') or product.get('product_name') or '未命名商品'))
    st.caption('来源：' + st.session_state.get('food_origin', '公开食品资料') + ' · 条码 ' + str(product['code']))
    with st.columns([1, 2])[0]:
        product_photo(product)
    st.info('这里只是预览，尚未导入。请核对商品身份，勾选确认后再保存为候选。')
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
            quantity = str(product.get('quantity') or '')
            if 'net_weight_g' not in provided and any(unit in quantity.lower() for unit in ('ml', 'cl', '毫升', '升')):
                st.info(f'包装“{quantity}”标的是体积，不能直接当作克重。可先导入已有名称和配料，再按实物补充重量资料。')
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
                close_preview()
                st.rerun()
    if st.button('关闭预览，继续选商品', key='close_food_preview'):
        close_preview()
        st.rerun()


def render(repo):
    st.subheader('选商品 → 看资料 → 导入候选')
    st.write('不知道条码或完整名称也能选：选择分类，加载商品列表，直接挑选并预览。')
    st.info('只补充来源实际提供的名称、明确重量和配料。价格请自行补录；公开资料仍需人工核对。')
    catalog_tab, search_tab = st.tabs(['按分类挑选商品', '条码 / 名称查询'])
    with catalog_tab:
        catalog()
    with search_tab:
        search()
    product = st.session_state.get('food_preview_product')
    if product:
        st.success('已选择：' + product_label(product))
        st.button('重新打开候选预览', key='reopen_food_preview', on_click=open_preview)
        if st.session_state.get('food_preview_open'):
            preview_dialog(repo, product)
    st.caption(f'数据来源：{ATTRIBUTION}。成功结果缓存1小时；名称查询最多5项，分类每页最多12项。')
    st.markdown('[数据许可与使用条款](https://world.openfoodfacts.org/terms-of-use)')

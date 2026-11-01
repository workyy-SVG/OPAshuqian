import streamlit as st
from config import BRAND_NAME
from repository import Repository, BusinessError
from config import Settings
from services.bootstrap_service import get_repository, cached_products, database_token
from views.access_view import authorize
from views import product_view, quality_view, content_view, impact_view
from views.guidance import apply_theme, workspace_header, product_overview
from services.experience_service import overview
from views.components import notifications
from views.themes import THEMES, apply_background

st.set_page_config(page_title="黔品智营 · 产品与内容协同", page_icon="🌿", layout="wide")
authenticated_user = authorize()
settings = Settings.from_env()
try:
    repo = get_repository(str(settings.runtime_dir), str(settings.db_path))
except BusinessError as error:
    st.error(str(error))
    st.stop()
apply_theme()
if 'pending_navigation' in st.session_state:
    st.session_state['navigation'] = st.session_state.pop('pending_navigation')

with st.sidebar:
    st.title("🌿 黔品智营")
    st.caption("产品资料有据 · 内容更新可追溯")
    st.divider()
    page = st.radio("工作空间", ["使用教程", "产品资料", "数据核对", "内容工作台", "变更追踪"], index=1, key="navigation")
    st.divider()
    st.caption(BRAND_NAME)
    st.subheader('当前产品')
    products = cached_products(str(settings.db_path), database_token(repo), repo)
    product_map = {p["id"]: p for p in products}
    if products:
        next_product = st.session_state.pop("next_product", None)
        if next_product in product_map:
            st.session_state["selected_product"] = next_product
        if st.session_state.get("selected_product") not in product_map:
            st.session_state["selected_product"] = products[0]["id"]
        product_id = st.selectbox("当前产品对象", list(product_map),
            format_func=lambda i: f"{product_map[i]['sku']} · {product_map[i]['version']}", key="selected_product")
    else:
        product_id = None
        st.info("导入样例或新增一个产品开始。")
    st.divider()
    st.subheader('本次操作')
    if authenticated_user:
        operator = authenticated_user
        st.caption('本次操作人 / 审核人：' + operator)
    else:
        operator = st.text_input("操作人 / 审核人", value="", key="operator", placeholder="填写实际操作人")
    st.checkbox('显示模块使用说明', value=True, key='show_module_guide')
    if not operator.strip():
        st.caption('开始确认或审核前，记得填写操作人。')
    if st.button('打开体验向导', key='open_guide'):
        st.session_state['open_welcome'] = True
    with st.expander('背景风格', expanded=False):
        st.selectbox('选择界面风格', list(THEMES), key='background_style')
        st.caption('五种风格可随时切换，本次会话内保留；不影响产品资料。')
    st.caption("教学演示 · 公开资料需核对，样例为拟制")

notifications()
apply_background()

progress = overview(repo, product_id)
if page != '使用教程':
    workspace_header(page, product_map.get(product_id), progress)
if product_id and page == '产品资料':
    with st.expander('当前产品的完成情况', expanded=False):
        product_overview(progress)
from views import tutorial_view
{
    "使用教程": tutorial_view.render,
    "产品资料": product_view.render,
    "数据核对": quality_view.render,
    "内容工作台": content_view.render,
    "变更追踪": impact_view.render,
}[page](repo, product_id, operator)
from views.onboarding import show
show(repo, progress, not products and page != '使用教程')

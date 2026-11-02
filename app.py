import streamlit as st
import uuid
from config import BRAND_NAME
from repository import Repository, BusinessError
from config import Settings
from services.bootstrap_service import get_repository, cached_products, database_token
from views.access_view import authorize
from views import product_view, quality_view, content_view, impact_view
from views.guidance import apply_theme, workspace_header
from services.experience_service import overview
from services import query_service as queries
from views.components import notifications
from views.themes import THEMES, apply_background
from services.demo_service import public_demo, demo_settings, quota_settings, seed_demo

st.set_page_config(page_title="黔品智营 · 产品与内容协同", page_icon="🌿", layout="wide")
authenticated_user = authorize()
settings = Settings.from_env()
quota_repo = None
session_id = st.session_state.setdefault('model_session_id', uuid.uuid4().hex)
if public_demo():
    quota_base = quota_settings(settings)
    quota_repo = get_repository(str(quota_base.runtime_dir), str(quota_base.db_path))
    workspace_id = st.session_state.setdefault('demo_workspace_id', uuid.uuid4().hex)
    settings = demo_settings(settings, session_id, workspace_id)
try:
    with st.spinner('正在准备工作区与产品资料…'):
        repo = get_repository(str(settings.runtime_dir), str(settings.db_path))
        if public_demo() and not st.session_state.get('demo_seeded'):
            seed_demo(repo)
            st.session_state['demo_seeded'] = True
except BusinessError as error:
    st.error(str(error))
    st.stop()
apply_theme()
if public_demo():
    st.info('公开拟制演示 · 本会话资料独立，请勿存放真实客户资料。')
    with st.sidebar.expander('重置本次演示'):
        st.caption('重连可能创建新工作区；演示资料不作持久保存承诺。')
        confirmed_reset = st.checkbox('确认放弃本工作区，恢复统一拟制样例', key='confirm_demo_reset')
        if st.button('恢复演示样例', disabled=not confirmed_reset, key='reset_demo'):
            # Rotate the sandbox, preserving both the session quota and old files.
            token = st.session_state.get('access_token')
            st.session_state.clear()
            st.session_state['model_session_id'] = session_id
            if token:
                st.session_state['access_token'] = token
            st.rerun()
if 'pending_navigation' in st.session_state:
    st.session_state['navigation'] = st.session_state.pop('pending_navigation')

with st.sidebar:
    st.title("🌿 黔品智营")
    st.caption("产品资料有据 · 内容更新可追溯")
    st.divider()
    routes = {'产品资料':'01 · 产品资料','数据核对':'02 · 数据核对','内容工作台':'03 · 内容工作台','变更追踪':'04 · 变更追踪','使用教程':'帮助 · 使用教程'}
    st.caption('按01—04顺序处理业务；需要说明时打开使用教程。')
    page = st.radio("工作流程", list(routes), format_func=routes.get, key="navigation")
    st.divider()
    st.caption(BRAND_NAME)
    st.subheader('当前产品')
    products = queries.products(repo)
    product_map = {p["id"]: p for p in products}
    if products:
        next_product = st.session_state.pop("next_product", None)
        if next_product in product_map:
            st.session_state["selected_product"] = next_product
        if st.session_state.get("selected_product") not in product_map:
            st.session_state["selected_product"] = products[0]["id"]
        product_id = st.selectbox("当前产品对象", list(product_map),
            format_func=lambda i: queries.product_label(product_map[i]), key="selected_product")
    else:
        product_id = None
        st.info("导入样例或新增一个产品开始。")
    def open_new_product():
        st.session_state.pop('focused_manual_field', None)
        st.session_state['focused_new_product'] = True
        st.session_state['pending_navigation'] = '产品资料'
    st.button('＋ 新建商品', key='sidebar_new_product', on_click=open_new_product, width='stretch')
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
    with st.expander('背景风格', expanded=False):
        st.selectbox('选择界面风格', list(THEMES), key='background_style')
        st.caption('五种风格可随时切换，本次会话内保留；不影响产品资料。')
    st.caption("公开资料需核对 · 只有人工确认后才用于生成")

notifications()
apply_background()

progress = overview(repo, product_id)
if page != '使用教程':
    workspace_header(page, product_map.get(product_id), progress)
from views import tutorial_view
{
    "使用教程": tutorial_view.render,
    "产品资料": product_view.render,
    "数据核对": quality_view.render,
    "内容工作台": lambda r, p, o: content_view.render(r, p, o, quota_repo, session_id),
    "变更追踪": impact_view.render,
}[page](repo, product_id, operator)

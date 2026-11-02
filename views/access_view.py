import os
import streamlit as st
from repository import BusinessError
from services.access_service import AccessConfig, AccessRegistry
from services.demo_service import public_demo


@st.cache_resource
def access_registry() -> AccessRegistry:
    return AccessRegistry()


def access_config() -> AccessConfig:
    values = {}
    try:
        values = dict(st.secrets.get('access', {}))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        pass
    address = st.get_option('server.address')
    required = (not public_demo() and address not in ('127.0.0.1', 'localhost', '::1')) or str(os.environ.get('QIANPIN_AUTH_REQUIRED', values.get('required', False))).lower() == 'true'
    return AccessConfig(required, os.environ.get('QIANPIN_AUTH_USER', values.get('username', '')),
                        os.environ.get('QIANPIN_AUTH_PASSWORD_HASH', values.get('password_hash', '')),
                        int(values.get('session_seconds', 1800)))


def logout() -> None:
    access_registry().revoke(st.session_state.get('access_token', ''))
    st.session_state.clear()


def authorize() -> str | None:
    config = access_config()
    if not config.required:
        return None
    if not config.configured:
        st.error('受保护模式尚未配置登录账号。请按部署说明在本机配置用户名与口令哈希，业务资料暂不可访问。')
        st.stop()
    user = access_registry().validate(st.session_state.get('access_token', ''), config)
    if user:
        with st.sidebar:
            st.caption('已登录：' + user)
            st.button('退出登录', on_click=logout)
        return user
    st.title('黔品智营 · 登录')
    st.caption('请输入部署管理员提供的账号。登录后才能查看、修改或导出资料。')
    with st.form('login'):
        username = st.text_input('用户名', max_chars=80)
        password = st.text_input('口令', type='password', max_chars=1024)
        if st.form_submit_button('登录', type='primary'):
            token = access_registry().login(username, password, config)
            if token:
                st.session_state['access_token'] = token
                st.session_state.pop('operator', None)
                st.rerun()
            st.error('账号或口令不正确，或尝试过于频繁。连续失败后请等待5分钟。')
    st.stop()


def download_guard():
    config = access_config()
    token = st.session_state.get('access_token', '')
    registry = access_registry()
    def check():
        if config.required and not registry.validate(token, config):
            raise BusinessError('登录已退出或过期，请重新登录后下载。', 'authentication_required')
    return check

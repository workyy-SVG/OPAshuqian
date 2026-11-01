"""Guided navigation without automatically adopting evidence or approving text."""
import streamlit as st
from config import ROOT
from services.import_service import preview_import, commit_import
from views.common import action
from views.guidance import navigate


def show(repo, progress, empty):
    automatic = empty and not st.session_state.get('welcome_seen', False)
    requested = st.session_state.pop('open_welcome', False)
    st.session_state['welcome_seen'] = True
    if automatic or requested:
        st.session_state['welcome_open'] = True
    if not st.session_state.get('welcome_open', False):
        return

    def dismissed():
        st.session_state['welcome_open'] = False

    @st.dialog('欢迎使用黔品智营 · 四步体验', width='large', on_dismiss=dismissed)
    def guide():
        st.write('保留来源 → 核对资料 → 生成草稿 → 人工审核并下载。每一步均由你决定，向导不会替你确认事实。')
        step = st.radio('选择体验步骤', range(4), horizontal=True,
                        format_func=lambda i: ['1 导入','2 核对','3 生成','4 审核导出'][i], key='welcome_step')
        st.progress(sum(progress['steps'][:3])/3, text='准备与内容进度（变更追踪可稍后体验）')
        descriptions = [
            '第一次可一键加载拟制样例，也可关闭向导，用CSV或公开食品资料开始。',
            '选择净含量，排除样例中误录的250g，再确认200g；确认名称。填写操作人和核对依据。',
            '模板方式无需密钥；已确认名称和重量后可取消加入价格，先生成第一份草稿。',
            '切换“审核与历史”，提交审核，逐句核对后通过审核，再下载TXT。',
        ]
        st.info(descriptions[step])
        if step == 0:
            if st.button('一键加载拟制样例并去核对', type='primary', key='welcome_import'):
                ok, _ = action(lambda: commit_import(repo, preview_import((ROOT/'samples/products.csv').read_bytes()), '拟制演示样例.csv'),
                               '样例已加载。先排除250g误录，再确认名称与200g净含量。')
                if ok:
                    st.session_state['welcome_open'] = False
                    navigate('数据核对')
                    st.rerun()
        elif st.button(['','去核对资料','去生成第一份草稿','去审核与下载'][step], type='primary', key='welcome_next'):
            st.session_state['welcome_open'] = False
            navigate('数据核对' if step==1 else '内容工作台')
            st.rerun()
        if st.button('关闭向导，开始操作', key='welcome_close'):
            st.session_state['welcome_open'] = False
            st.rerun()
        st.caption('随时从侧栏重新打开体验向导；已有数据不会被清空。')
    guide()

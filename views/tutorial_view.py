"""In-app operating manual and sandbox diagrams; no business data mutations."""
from html import escape
import streamlit as st
from views.guidance import next_button

LESSONS = {
 '产品资料': {
  'purpose':'收集资料并保留来源，让后续核对有依据。导入只产生待确认候选。',
  'input':'CSV、包装标签/价目表，或公开食品目录中的商品。',
  'output':'独立的SKU与产品版本、待确认候选、可追溯的来源记录。',
  'steps':[
   ('选择资料入口','公开食品资料：按分类浏览商品目录，选商品后预览；CSV导入：上传长表CSV或加载拟制样例；手动补录：逐项填写包装或价目表上的内容。'),
   ('核对商品身份','SKU是你给商品的编号，前导零会保留；版本表示不同包装/规格。公开食品默认用OFF-条码作为独立SKU，只有确认为同一商品时才合并到已有SKU。'),
   ('预览后保存','检查名称、重量、配料等字段，确认导入。公开数据中的毫升不会被猜成克，未提供的价格不会自动编造。'),
   ('选择产品去核对','侧栏选择当前产品，再进入“数据核对”。“来源与历史”用于下载原CSV和JSON快照。')],
  'example':'同一SKU的名称、净含量、零售价格各是一项资料；200g和0.2kg是同一个重量。',
  'done':'已看到目标SKU和待确认资料，下一步是人工核对。'},
 '数据核对': {
  'purpose':'判断哪份来源适用于当前产品，把可靠的候选变成生成可用的确认资料。',
  'input':'产品资料页保存的候选、包装实物和可靠价目表。',
  'output':'当前确认资料、采纳/排除原因以及可追溯的处理历史。',
  'steps':[
   ('先选产品并填操作人','在侧栏确认SKU和版本，再填写操作人。不同SKU、包装版本、零售/批发渠道分别核对，不能混用。'),
   ('选一个待核对字段','先看冲突，再看名称、净含量。冲突表示同一字段有不同标准值；200g与0.2kg等价，250g与200g不同。'),
   ('对照来源作判断','查看每张卡片的原文、标准值和来源。对的点“选此项确认”，明确错误的点“选此项排除”；不确定时先不确认，回资料页补充依据。'),
   ('写依据并保存','下方核对选中的原文、处理方式，填写核对依据，例如“已对照包装标签为200g”。排除要再勾选确认，然后点击“保存本次处理”。'),
   ('重复核对并前往生成','逐项确认名称、净含量；需要价格时再确认对应渠道价格。看到2/2项已确认且没有阻塞冲突后，可进入内容工作台。')],
  'example':'仅针对拟制样例：包装依据为200g，250g是故意放入的误录。先排除250g，再采用200g；真实商品必须以实际核查为准。',
  'done':'“当前确认资料”出现已采纳的名称和净含量；导入成功本身不表示核对完成。'},
 '内容工作台': {
  'purpose':'用已确认资料组织文案，人工逐句审核后下载TXT。',
  'input':'已确认的名称、重量，以及可选的渠道价格和说明。',
  'output':'可追溯的草稿、审核记录及通过校验的TXT文件。',
  'steps':[
   ('选择内容类型和依据','选择商品介绍或朋友圈文案；只在已有明确渠道价格时加入价格。没有价格可取消勾选。右侧检查本次生成依据。'),
   ('选择生成方式','第一次推荐模板，不需要密钥；DeepSeek或通义千问需配置密钥并受每日额度限制。'),
   ('生成并提交审核','点击“生成一份草稿”，到“审核与历史”选中该修订，阅读标题和正文，再点“提交人工审核”。'),
   ('逐句核对后下载','检查名称、规格、价格、配料及其他陈述，勾选已核对并写审核说明，审核通过后点击“校验依据并下载TXT”。')],
  'example':'模板也需要审核。改过正文会产生新修订，新修订不能沿用旧审核直接下载。',
  'done':'状态显示“可导出”，TXT下载成功；系统不会替你发布到外部平台。'},
 '变更追踪': {
  'purpose':'资料调价或纠错后，定位哪些文案需要更新，防止旧内容继续使用过期信息。',
  'input':'已经生成的内容，以及你新确认或撤回的资料。',
  'output':'变化对比、受影响内容清单、新修订及重审结果。',
  'steps':[
   ('先更新资料','回到产品资料补录新价格或纠错依据，在数据核对页人工确认；不能只在正文里改价代替资料更新。'),
   ('看旧值到新值','变更追踪页会显示旧值→新值和受影响文案；不相关的内容不会因为这次变化自动变成待复查。'),
   ('修改或生成新修订','可按当前资料生成模板新修订，或手动修改。只有逐句确认旧正文仍适用时，才使用“沿用并重绑依据”。'),
   ('重新审核和替换','回内容工作台审核新修订并下载，自己替换外部已发布的旧内容。历史仍保留。')],
  'example':'零售价从12元改为14元：含旧价的文案需要修改并重审；不含价格且未依赖该价格的内容不会被这项调价影响。',
  'done':'最新修订审核通过，本次变化显示已处理；外部旧文件仍需你替换。'},
}


def flow_diagram(nodes):
    st.markdown('<div class="qp-learn-flow">'+''.join(
        f'<div class="qp-learn-node"><strong>{i+1} · {escape(title)}</strong>{escape(copy)}</div>'
        for i,(title,copy) in enumerate(nodes))+'</div>', unsafe_allow_html=True)


def render(repo=None, product_id=None, operator=None):
    st.title('使用教程')
    st.write('选择模块，看带标注的界面示意，再亲手点按钮观察结果。练习不修改业务资料。')
    topic = st.session_state.pop('next_tutorial_topic', None)
    if topic in LESSONS:
        st.session_state['tutorial_topic'] = topic
    topic = st.selectbox('想学习哪个模块？', list(LESSONS), key='tutorial_topic')
    lesson = LESSONS[topic]
    st.caption('这个模块的作用：'+lesson['purpose'])
    from views.visual_tutorial import render as render_visual
    render_visual(topic)
    st.success('完成标志：'+lesson['done'])
    next_button('去'+topic+'实际操作', topic, 'tutorial:practice:'+topic)
    with st.expander('需要文字说明？查看完整步骤',expanded=False):
        st.markdown('**准备：** '+lesson['input'])
        st.markdown('**结果：** '+lesson['output'])
        for i,(title,copy) in enumerate(lesson['steps'],1):
            st.markdown(f'**第{i}步 · {title}**')
            st.write(copy)
        st.caption('举例：'+lesson['example'])
    with st.expander('常见疑问：为什么导入了还不能生成？', expanded=False):
        st.write('导入只保存来源说法，人工确认后才能用于生成。名称与净含量必须确认；勾选加入价格时，还需确认对应渠道价格。')
        st.write('有不同候选时先核对来源并处理冲突；没有证据时先补录。不要为了消除提示随意选择一个值。')
    st.download_button('下载完整使用说明', _manual().encode('utf-8'), '黔品智营使用教程.md','text/markdown')


def _manual():
    chunks = ['# 黔品智营使用教程\n\n流程：收集来源 → 核对资料 → 生成审核 → 变更重审。']
    for title,lesson in LESSONS.items():
        chunks.append('## '+title+'\n\n'+lesson['purpose'])
        chunks.extend(f'{i}. {head}：{copy}' for i,(head,copy) in enumerate(lesson['steps'],1))
        chunks.append('完成标志：'+lesson['done'])
    return '\n\n'.join(chunks)

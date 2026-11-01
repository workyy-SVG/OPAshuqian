"""Illustrated, clickable lessons. All state is scoped to the tutorial session."""
from html import escape
import streamlit as st

SCENES = {
 '产品资料': [
  ('先选一份资料','选择示例CSV','file','点击选择文件，右侧会出现示例资料。'),
  ('先预览，暂不确认事实','预览这份资料','preview','查看名称、重量和价格分别是哪一行。'),
  ('保存为候选','确认导入（演示）','import','导入后变成黄色“待确认”，还不能直接用来生成。'),
  ('来源已保留，等待核对',None,'done','接下来进入数据核对，逐项确认名称和净含量。')],
 '数据核对': [
  ('先选对产品','选择 TRY001 · V1（演示）','product','核对的是当前SKU和版本，不是把不同包装混在一起。'),
  ('先看包装，再处理冲突','选此项排除：250g（演示）','conflict','本练习给出的包装标签是200g，所以250g是误录；真实商品必须自己查证。'),
  ('写清为什么排除','保存排除（演示）','exclude','依据和二次确认齐全后，250g卡片才变灰。'),
  ('现在选择正确资料','选此项确认：200g（演示）','choose','200g与0.2kg是同值。先选可靠来源，再填写确认依据。'),
  ('记录你的核对依据','保存确认（演示）','confirm','保存后，200g才进入绿色的“当前确认资料”。'),
  ('黄色候选变为绿色确认',None,'done','这一步只完成了净含量。真实操作还需确认名称，按需确认渠道价格。')],
 '内容工作台': [
  ('先看本次生成依据','选择模板模式（演示）','basis','只使用绿色的确认资料。模板不需要模型密钥。'),
  ('用确认资料组织草稿','生成一份草稿（演示）','generate','草稿仍需人工逐句审核，不能生成后就直接发布。'),
  ('草稿进入待审核','提交人工审核（演示）','draft','核对名称、规格、价格和其他陈述。'),
  ('逐句核对后通过','审核通过（演示）','review','勾选已核对并填写说明后，状态才变为“可导出”。'),
  ('绿色可导出',None,'done','真实页面此时出现“校验依据并下载TXT”。本练习不生成业务内容，也不冒充实际审核。')],
 '变更追踪': [
  ('先看调价前的两份内容','确认新价格14元（演示）','before','A含价格并依赖旧价，B未依赖价格。观察只有A会受到影响。'),
  ('只有关联文案需要复查','生成14元的新修订（演示）','stale','含旧价的A转为待复查；没有依赖该价格的B保持可用。'),
  ('正文和依据一起更新','提交并复核新修订（演示）','revise','新正文写14元，旧版本仍保留。新修订还要审核。'),
  ('审核后才算处理完成','确认重审通过（演示）','review','不自动替换外部发布内容，下载后仍需自己替换。'),
  ('新修订已审核',None,'done','外部旧文案仍需你替换。系统里的历史版本不会被删除。')],
}


def _text(x,y,value,size=15,color='#243c32',weight=400):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}">{escape(str(value))}</text>'


def _box(x,y,w,h,color='#ffffff',stroke='#d8e3dc',radius=14):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{color}" stroke="{stroke}"/>'


def _callout(x,y,w,label):
    return (_box(x,y,w,36,'#fff4d6','#b77412',10)+_text(x+12,y+24,'↓ '+label,14,'#794707',650))


def screen_svg(topic, step):
    """A labeled interface illustration, not a screenshot of real product data."""
    if topic not in SCENES or not 0 <= step < len(SCENES[topic]):
        raise ValueError('Unknown tutorial scene')
    done = step == len(SCENES[topic])-1
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 940 470" role="img" aria-label="{escape(topic)}第{step+1}步操作示意">',
             '<title>教学示意界面，所有数值均为拟制演示</title>',
             '<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif}</style>',
             _box(2,2,936,466,'#f2f7f4'), _box(2,2,936,46,'#173f31','#173f31'),
             _text(22,32,'黔品智营  /  '+topic+'  /  教学示意',17,'#ffffff',650),
             _box(16,62,166,390,'#e3eee7'),_text(30,91,'当前产品',14),
             _box(26,108,146,46,'#ffffff'),_text(36,137,'TRY001 · V1',15,weight=650),
             _text(30,194,'来源 → 确认 → 内容',12),
             _text(210,91,SCENES[topic][step][0],22,weight=650)]
    if topic == '产品资料':
        parts += [_box(210,114,298,268),_text(230,146,'资料收集区',16,weight=650),
                  _box(235,166,248,110,'#f3f6f4'),_text(257,204,'▤  示例产品资料.csv',17),
                  _text(258,237,'名称 / 重量 / 零售价',14),
                  _box(245,298,230,46,'#267562'),_text(265,328,'选择文件 → 预览 → 导入',14,'#ffffff'),
                  _text(542,142,'预览与导入结果',16,weight=650)]
        for i,(name,value) in enumerate([('名称','拟制辣椒酱'),('净含量','200g'),('零售价','12.00元')]):
            y = 165+i*68
            parts += [_box(540,y,365,54,'#dcfce7' if done else '#fff7df' if step>=2 else '#ffffff'),
                      _text(553,y+33,name,14),_text(630,y+33,value if step>=1 else '—',15,weight=650),
                      _text(804,y+33,'待确认' if done else '待导入' if step>=1 else '未预览',13)]
        parts += [_callout(225,392,650,'黄色表示候选；保存来源之后，还需要去数据核对确认。' if done else '点下方同名按钮，观察资料从文件变为待确认候选。')]
    elif topic == '数据核对':
        parts += [_box(210,112,695,59,'#e5f0fc'),_text(230,149,'本练习的可靠包装标签：净含量 200g',19,'#234f79',650)]
        for i,(value,source) in enumerate([('200g','包装标签'),('250g','拟制误录记录')]):
            x = 210+i*355
            excluded = i==1 and step>=3
            adopted = i==0 and done
            color = '#e5e7eb' if excluded else '#dcfce7' if adopted else '#fff7df'
            parts += [_box(x,193,340,137,color),_text(x+20,225,'来源A' if i==0 else '来源B',14),
                      _text(x+20,266,value,32,weight=700),_text(x+135,266,source,15),
                      _text(x+20,306,'− 已排除' if excluded else '✓ 当前确认' if adopted else '◷ 待确认',15)]
        parts += [_box(210,346,695,37),_text(226,371,'处理依据：'+('已对照包装标签，净含量为200g' if step>=3 else '在下方填写本次查阅的依据'),14),
                  _callout(210,400,695,'250g已移出候选，200g成为确认资料。' if done else '① 选资料  →  ② 填依据  →  ③ 保存；只点击选择不会自动确认。')]
        if step==0:
            parts += [_box(25,106,148,50,'none','#b77412'),_text(30,181,'↑ 先选SKU和版本',12,'#794707')]
    elif topic == '内容工作台':
        parts += [_box(210,116,253,256),_text(230,148,'已确认的生成依据',17,weight=650)]
        for i,label in enumerate(['✓ 拟制辣椒酱','✓ 净含量200g','✓ 零售价12元']):
            parts += [_box(225,169+i*57,220,43,'#dcfce7'),_text(238,197+i*57,label,15,'#14532d')]
        parts += [_text(480,253,'→',32),_box(526,116,379,256),
                  _text(548,149,'文案预览',17,weight=650),_text(548,192,'拟制辣椒酱',23,weight=650),
                  _text(548,229,'净含量200g，零售价12元。',16),_text(548,262,'内容由确认资料组织，仍需审核。',14),
                  _box(548,296,329,45,'#dcfce7' if done else '#dbeafe' if step==3 else '#e5e7eb'),
                  _text(565,325,'✓ 可导出 TXT' if done else '◷ 待审核' if step==3 else '✎ 草稿' if step>=2 else '准备生成',17),
                  _callout(210,400,695,'生成 → 草稿 → 提交审核 → 逐句核对 → 审核通过 → TXT')]
    else:
        parts += [_box(210,115,695,67,'#e5f0fc'),_text(232,155,'原价 12元',23),_text(438,155,'→',28),_text(540,155,'新价 14元' if step>=1 else '准备调为14元',23,weight=650)]
        for i,title in enumerate(['文案A · 使用了价格','文案B · 没有依赖价格']):
            x = 210+i*355
            state = '✓ 保持可用' if i else '✓ 可用' if step==0 else '！待复查' if step==1 else '✎ 新修订待审核' if not done else '✓ 新修订可导出'
            parts += [_box(x,207,340,143,'#dcfce7' if i or done else '#fff7df'),
                      _text(x+18,240,title,17,weight=650),_text(x+18,278,'零售价'+('14元' if step>=2 else '12元') if i==0 else '净含量200g',19),
                      _text(x+18,320,state,16)]
        parts += [_callout(210,400,695,'只有依赖发生变化的资料，关联文案才需要复查。历史版本保留。')]
    parts.append('</svg>')
    return ''.join(parts)


def render(topic):
    key = 'visual_step:'+topic
    step = st.session_state.setdefault(key,0)
    title, button, _, explanation = SCENES[topic][step]
    st.subheader('跟着图，点一次，看一次变化')
    st.caption('教学示意界面 · 数据均为拟制 · 练习不修改你的产品、资料或内容')
    st.progress(step/(len(SCENES[topic])-1), text=f'第{step+1}/{len(SCENES[topic])}幕 · {title}')
    st.image(screen_svg(topic,step), width='stretch')
    st.info(explanation)
    st.markdown('**动手区：点击下方与图中流程对应的按钮**')
    reason = ''
    checked = False
    if (topic=='数据核对' and step in (2,4)) or (topic=='内容工作台' and step==3):
        reason = st.text_input('练习：填写这次核对的依据',key=f'visual_reason:{topic}:{step}',
                               placeholder='例如：已查看示例包装标签，净含量为200g')
        if step==2 or topic=='内容工作台':
            checked = st.checkbox('练习：我已核对并确认本次处理',key=f'visual_ack:{topic}:{step}')
    if button and st.button(button,type='primary',key='visual_action:'+topic):
        needs_reason = (topic=='数据核对' and step in (2,4)) or (topic=='内容工作台' and step==3)
        needs_ack = (topic=='数据核对' and step==2) or (topic=='内容工作台' and step==3)
        if needs_reason and not reason.strip():
            st.warning('先填写依据再保存；真实操作同样需要记录处理原因。')
        elif needs_ack and not checked:
            st.warning('请先勾选核对确认，界面才会进入下一状态。')
        else:
            st.session_state[key] = step+1
            st.rerun()
    if not button:
        st.success('演示完成！上图展示了操作后的结果。可以重新演示，或去真实模块操作。')
    left,right = st.columns(2)
    if left.button('上一幕',key='visual_back:'+topic,disabled=step==0):
        st.session_state[key] = step-1
        st.rerun()
    if right.button('重新演示',key='visual_reset:'+topic):
        st.session_state[key] = 0
        for stored in list(st.session_state):
            if stored.startswith(('visual_reason:'+topic+':','visual_ack:'+topic+':')):
                del st.session_state[stored]
        st.rerun()

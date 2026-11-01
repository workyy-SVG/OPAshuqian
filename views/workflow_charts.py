"""Static operating flowcharts with explicit decision branches and return paths."""
from html import escape
import streamlit as st

FLOWS = {
 '产品资料': [
  ('进入产品资料','选择当前SKU / 版本',None),
  ('选择收集入口','公开目录 / CSV / 手动补录',None),
  ('填写资料并查看预览','核对商品身份、原文与来源',None),
  ('身份与格式都正确？','检查必填项及适用范围',('否：先修改','纠正SKU、格式或来源','回到预览重新检查',2)),
  ('点击对应的保存按钮','确认导入 / 保存为待确认候选',None),
  ('结果：产生待确认候选','来源保留；尚不能用于生成',None),
  ('前往数据核对','选择同一SKU / 版本',None)],
 '数据核对': [
  ('选产品，填写操作人','侧栏核对SKU / 版本',None),
  ('进入待处理资料','筛选范围并选择待核对字段',None),
  ('查看每条候选的原文与来源','对照包装 / 可靠价目表',None),
  ('是否已取得查证依据？','不能只按上传时间或编号判断',('否：暂停处理','回产品资料补充可靠依据','不确定时不要随意确认',2)),
  ('选择本次处理方式','可靠→确认；查明错误→排除',None),
  ('填写依据并保存处理','排除还需勾选二次确认',None),
  ('名称与净含量已确认？','需要价格时另核对对应渠道',('否：继续核对','选择下一项待核对字段','重复查证和保存',1)),
  ('结果：确认资料可用于生成','进入内容工作台',None)],
 '内容工作台': [
  ('进入生成内容','选类型、渠道和是否加入价格',None),
  ('检查本次生成依据','只使用已确认资料',None),
  ('必需信息齐全且无冲突？','名称 / 净含量 / 所选渠道价格',('否：回数据核对','补齐缺项或查明冲突','也可取消不需要的价格',0)),
  ('选择方式，生成一份草稿','模板 / 已配置密钥的模型',None),
  ('进入审核与导出','选中修订，提交人工审核',None),
  ('逐句核对并填写审核说明','勾选确认，点击审核通过',None),
  ('正文与当前依据仍一致？','导出时再次校验',('否：修改并重审','修正正文或处理资料变化','新修订不能沿用旧审核',4)),
  ('结果：校验依据并下载TXT','下载不等于向外部平台发布',None)],
 '变更追踪': [
  ('在产品资料补录新来源','价格 / 包装 / 配料等变更',None),
  ('到数据核对确认新资料','记录实际查证依据',None),
  ('进入变更追踪查看关联内容','对照旧值→新值及影响范围',None),
  ('这份正文还适用吗？','必须逐句对照新资料',('否：修改正文','生成新修订或手动改写','然后重新审核',4)),
  ('保存使用当前依据的新修订','仍适用才允许沿用并重绑',None),
  ('回内容工作台重新审核','填写说明并通过审核',None),
  ('结果：下载最新修订','自己替换外部旧文件，历史保留',None)],
}


def _label(cx,cy,lines,color='#233c31',size=18):
    return ''.join(f'<text x="{cx}" y="{cy-8+i*25}" text-anchor="middle" font-size="{size}" fill="{color}">{escape(line)}</text>'
                   for i,line in enumerate(lines))


def flow_svg(topic):
    nodes=FLOWS[topic]
    height=90+len(nodes)*118
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 820 {height}" role="img" aria-label="{escape(topic)}操作流程图">',
         '<title>矩形为操作，菱形为判断，实线为下一步，虚线为处理后返回主流程</title>',
         '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 Z" fill="#526c60"/></marker></defs>',
         '<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif}</style>',
         f'<rect width="820" height="{height}" rx="18" fill="#f6f9f7"/>',
         _label(410,35,[topic+' · 从入口到完成结果'],'#173f31',22)]
    for i,(title,copy,branch) in enumerate(nodes):
        cy=105+i*118
        if i:
            svg.append(f'<path d="M220 {cy-76} V{cy-39}" fill="none" stroke="#526c60" stroke-width="2" marker-end="url(#arrow)"/>')
        if branch:
            svg.append(f'<polygon points="220,{cy-40} 392,{cy} 220,{cy+40} 48,{cy}" fill="#fff3d5" stroke="#a36c16" stroke-width="2"/>')
            svg.append(_label(220,cy,[f'{i+1}. '+title,copy],size=16))
            label,head,body,target=branch
            svg.extend([f'<path d="M392 {cy} H471" fill="none" stroke="#526c60" stroke-width="2" marker-end="url(#arrow)"/>',
                        f'<text x="417" y="{cy-10}" font-size="14" fill="#744a16">{escape(label.split("：")[0])}</text>',
                        f'<rect x="478" y="{cy-37}" width="288" height="74" rx="10" fill="#fff8e9" stroke="#a36c16"/>',
                        _label(622,cy,[head,body],size=16),
                        f'<path d="M766 {cy} H790 V{105+target*118} H393" fill="none" stroke="#526c60" stroke-dasharray="6 5" stroke-width="1.6" marker-end="url(#arrow)"/>',
                        f'<text x="231" y="{cy+61}" font-size="14" fill="#245b38">是 / 已完成</text>'])
        else:
            done=i==len(nodes)-1
            svg.extend([f'<rect x="48" y="{cy-37}" width="344" height="74" rx="{30 if done or i==0 else 10}" fill="{"#dcfce7" if done else "#e3eee8" if i==0 else "#ffffff"}" stroke="#739684"/>',
                        _label(220,cy,[f'{i+1}. '+title,copy],size=17)])
    svg.append('</svg>')
    return ''.join(svg)


def render_chart(topic):
    st.image(flow_svg(topic),width='stretch')
    st.caption('读图：沿箭头向下操作；遇到菱形先判断；右侧为未满足条件时的处理，沿虚线回到主流程。可放大查看。')

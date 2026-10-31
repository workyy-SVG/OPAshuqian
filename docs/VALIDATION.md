# 本地首版验收记录

验证日期：2026-10-31（北京时间）。环境：Windows、Python 3.13.16、Streamlit 1.66.1、SQLite 内置驱动；实际依赖见 requirements-lock.txt。

## 已执行

`python -m pytest tests -q`：30 项通过。全部测试使用临时数据库，不请求真实模型 API。另验证了候选重新分配审计、未来资料保留待确认、生成请求范围校验和运行包敏感文件排除。

| 手册用例 | 对应证据 |
| --- | --- |
| T01 单位等价 | test_import.py，200g 与 0.2kg 均为200，原文保留 |
| T02 同对象冲突 | test_quality.py，不同值候选未排除时不能确认 |
| T03 SKU 隔离 | test_facts.py、test_impact.py |
| T04 产品版本隔离 | test_facts.py、test_impact.py |
| T05 渠道隔离 | test_facts.py，retail 与 wholesale 独立 |
| T06 重复导入 | test_import.py，相同哈希不增加批次或候选 |
| T07 错误行 | test_import.py，缺失SKU和中文金额隔离、错误可查看 |
| T08 撤回必需字段 | test_impact.py，内容过期、不能生成或重绑 |
| T09 价格变更提醒 | test_impact.py，两类内容关联并去重 |
| T10 未输入字段 | test_impact.py，新说明字段不阻止旧内容导出，无价格内容不受调价影响 |
| T11 生成期间变更 | test_impact.py，保留旧快照并标stale |
| T12 内容编辑 | test_content.py，新revision必须重审 |
| T13 模型失败 | test_llm.py，空白、非法JSON、截断、401/402、超时和429重试；均为模拟响应 |
| T14 事务回滚 | test_impact.py，SQLite触发器故意中断，事实、候选、事件和内容状态整体回滚 |
| T15 重启与恢复 | test_content.py、test_backup.py，重新连接、在线备份恢复及有效审核导出 |
| 页面操作 | test_app.py，四页导航、拟制样例导入、生成、提交审核、人工确认通过 |

浏览器实际检查：产品导入与核对页面可正常显示，中文与表格可读，拟制样例导入按钮写入后展示结果。小窗口使用折叠侧栏，核对页按单字段处理，优先展示冲突。

## 拟制闭环实测

执行 `python -m scripts.demo_flow --out-dir runtime/acceptance-demo` 成功。创建3个产品对象；来源样例有15条有效候选、1条重复证据、2条错误行。脚本按预设假设确认200g，生成并审核两类模板内容；retail价格12元改14元后，旧内容#1、#2进入影响列表，另一SKU内容#3保持ready；新修订#4、#5重新审核导出。

备份恢复完整性返回ok；恢复库有3个产品对象、19条来源观察、14条事实修订、5条内容修订、27条依赖、10条审核与流程记录。脚本报告保留在本机隔离演示目录，不将运行数据上传GitHub。

## 尚未验证或完成

- 真实 DeepSeek 调用、耗时、用量和内容可用性：待在本机配置密钥后单独执行。
- 真实经营者试用、问题识别精确率召回率、效率提升、1000至10万条性能测试：尚未执行，不报告效果数字。
- Docker 构建、Linux/Windows GitHub CI 状态、在线 HTTPS 部署：以实际运行结果为准，不能用配置文件替代成功记录。
- 赛事创新说明、评审视频、报名材料与正式提交：尚未制作或提交。当前交付为可运行软件首版、源代码、测试与运行说明。

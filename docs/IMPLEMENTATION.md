# 实施范围与阶段记录

依据用户提供的《黔品智营详细开发与实施操作手册》，实现一个本地 Python 单体应用。

## 验收边界

- 固定一个演示品牌；以品牌、SKU、产品版本唯一识别商品。
- 六类字段，价格按渠道区分；原文、候选、确认修订、内容及审核均持久保存。
- 模板与 DeepSeek 模式明确区分；商品介绍与朋友圈文案两类输出。
- 内容保存全部输入依赖；修订时保守提醒，审核与导出重新检查依据。
- 首版不含自动电商发布、开放客服、多品牌入驻和句子级定位。

## 阶段记录

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| 01 | 读取手册、检查仓库、准备 Python 3.13 | 已完成 |
| 02 | 数据库、来源导入与质量核对 | 已完成，6 项自动化测试通过 |
| 03 | 事实修订、快照、内容审核与变更追踪 | 已完成，24 项业务与模型容错测试通过 |
| 04 | 四个页面及模型适配 | 已完成；四页导航和生成审核操作测试通过；真实 API 待本机配置密钥 |
| 05 | 自动化验收、备份恢复、运行说明与运行包 | 30 项本地测试通过；拟制闭环、备份恢复通过；源码运行包已生成，正在干净环境复现 |

每个阶段在检查后提交到 GitHub，提交记录对应可复查的工作成果。真实 API 调用、用户试用、线上部署与视频仅在实际完成后记录为完成。

## 已推送的阶段

- [实施范围与环境](https://github.com/workyy-SVG/OPAshuqian/commit/29401d9729320835e5b007efcb0f111afccf52bd)
- [资料导入、核对、事实修订与快照](https://github.com/workyy-SVG/OPAshuqian/commit/8923009ab95f27c7e76e047de50c21bdc520087f)
- [内容审核、导出、依赖追踪与模型适配](https://github.com/workyy-SVG/OPAshuqian/commit/6397cbc04a0f01201bec4911ad9bd092dbf0009f)
- [四个操作页面与应用测试](https://github.com/workyy-SVG/OPAshuqian/commit/f8b3060c36bba20bc50a7787dbf4ea0b8adb7f7b)

开发机直连GitHub的Git传输失败，本次使用已授权GitHub连接提交，保留原有仓库历史。运行数据库、原始经营数据和真实密钥均不上传。

## 已核对的官方接口

2026-10-31 核对：[DeepSeek 首次调用](https://api-docs.deepseek.com/)、[JSON 输出](https://api-docs.deepseek.com/guides/json_mode)、[Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest)。模型默认 deepseek-flash，可从本机配置修改。明确关闭思考模式并请求 JSON 输出。

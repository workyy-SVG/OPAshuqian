# 黔品智营

面向地方特色食品小微品牌的产品资料核对与内容协同工具。按实施手册实现 Python 3.13、Streamlit、SQLite 本地单体应用，支持DeepSeek、通义千问及无需密钥的模板模式。

**当前状态：已接入Open Food Facts条码查询与名称搜索，公开资料预览后进入待确认候选，保留来源与JSON快照。80项本地测试通过，核心覆盖率92.64%，静态检查通过；各次推送的CI结果见GitHub Actions。真实模型调用仍需单独验收。**

学生演示从[公开食品资料五分钟流程](docs/OPEN_FOOD_FACTS.md)开始。入口为“产品资料 → 公开食品资料”，无需新增API Key；名称、重量、配料核对确认后可直接用模板完成审核导出。网络不可用时继续使用CSV拟制样例。

逐项处理结果见[18项清单实施记录](docs/CHECKLIST_IMPLEMENTATION.md)，认证配置和升级恢复见[部署说明](docs/DEPLOYMENT.md)。PostgreSQL迁移与开放多品牌入驻保留为按需路线图。

本轮还修复了旧价格正文可误绑新依据的问题：正文的明确名称、净含量与价格在提交审核、通过审核和导出时重新校验。详见[优化记录](docs/OPTIMIZATION.md)。先前首版的Windows/Linux CI、独立环境复现与备份恢复记录保留在验收文档中。

## 四个工作页面

| 页面 | 可完成的工作 |
| --- | --- |
| 产品资料 | 公开食品条码/名称查询、候选预览、CSV导入、错误行与来源快照下载、手动补录、版本与历史 |
| 数据核对 | 按产品与渠道核对缺失和冲突、排除误录、重新分配、人工确认、查看处理依据 |
| 内容工作台 | 两类内容、可选价格与说明字段、模板或 DeepSeek 生成、保存快照、编辑新修订、审核与 TXT 导出 |
| 变更追踪 | 查看变化影响、撤回事实、模板重写或正文沿用并重绑新依据、保留历史 |

资料的名称、净含量和渠道价格按原文入库，重量统一为克，价格以 Decimal 换算为整数分。产品身份使用品牌、SKU、产品版本，价格额外区分渠道。所有候选必须人工确认才能参与生成。

## 安装与启动

Windows PowerShell 在项目根目录依次运行：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes --only-binary=:all: -r requirements-lock.txt
.\.venv\Scripts\python.exe -m scripts.init_db
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address=127.0.0.1
```

浏览器打开终端显示的本机地址，默认 [http://127.0.0.1:8501](http://127.0.0.1:8501)。环境准备好后，也可双击根目录 `run.cmd` 启动。停止应用在终端按 Ctrl+C。

没有 `py` 命令且已安装 uv 时可改用：

```powershell
uv python install 3.13
uv venv --python 3.13 .venv
uv pip install --python .venv/Scripts/python.exe --require-hashes --only-binary :all: -r requirements-lock.txt
```

Linux / macOS 使用 `python3.13 -m venv .venv`，后续解释器路径改为 `.venv/bin/python`。本机验证平台为Windows；Windows、Linux、macOS及Docker均已在此前CI中验证，最新结果见[Actions](https://github.com/workyy-SVG/OPAshuqian/actions)。

## 第一次体验

需要逐按钮操作和可直接上传的分步CSV，请看 [成品使用说明](docs/USER_GUIDE.md)。[分步体验资料](samples/walkthrough)使用独立TRY编号：先上传01、核对并生成两份内容，再上传02体验调价追踪；03用于格式错误，04是空白模板。

1. 在侧栏填写操作人，在产品资料页点击“导入拟制演示样例”。会建立 P001 V1、P001 V2、P002 V1 三个对象，保留 2 条错误行和 1 条重复证据。
2. 选择 P001 V1，进入数据核对页。净含量有 200g、0.2kg 和 250g：根据本次拟制场景，先排除 250g 并说明原因，再确认 200g；0.2kg 会作为同值依据保留。
3. 确认产品名称和 retail 价格。生成商品介绍、朋友圈文案时可加入已有的配料和储存说明。
4. 在“审核与历史”选择草稿，提交人工审核；逐句核对后填写说明并审核通过，下载 TXT。
5. 回产品资料页补录价格 `14.00`，字段选“价格”、范围选“零售”，说明来源与调价原因。到数据核对页确认新依据。CSV中的代码仍为price_cent和retail。
6. 在变更追踪页看到旧内容待复查。生成模板新修订，或核对正文后重绑当前依据，重新审核导出。旧修订及原审核不会被覆盖。

所有样例、脚本自动确认和价格变更均为拟制演示，不代表真实经营效果或真实用户审核。直接操作页面时，事实取舍与内容审核由经营者本人完成。

## 模型配置

复制配置示例到本机文件，可填写一个或两个模型的密钥：

```powershell
Copy-Item .streamlit/secrets.example.toml .streamlit/secrets.toml
```

```toml
[deepseek]
api_key = "本机填写，勿提交"
endpoint = "https://api.deepseek.com/chat/completions"
name = "deepseek-flash"

[qwen]
api_key = "本机填写，勿提交"
endpoint = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
name = "qwen-plus"
```

也支持 `DEEPSEEK_API_KEY` 和 `DASHSCOPE_API_KEY` 环境变量。模型配置集中管理，密钥不写入数据库和日志。仅允许两个提供方的官方 HTTPS 端点，关闭思考模式并请求 JSON 输出。调用包含所选确认快照，请仅使用有授权的资料。

配置后可在内容工作台选择“DeepSeek 实时生成”或“通义千问实时生成”。可分别执行一次真实接口检查（会消耗 API 额度，产品编号以本机数据库为准）：

```powershell
.\.venv\Scripts\python.exe -m scripts.check_model 1 --confirm-live
.\.venv\Scripts\python.exe -m scripts.check_model 1 --provider qwen --confirm-live
```

401 / 402等配置与余额错误不会自动重试；默认连接超时、429和部分5xx最多额外重试一次，采用指数退避与抖动。429优先尊重Retry-After，超过最大等待则停止，不提前重试。QIANPIN_RETRY_ATTEMPTS（1至5）、QIANPIN_RETRY_BASE_DELAY与QIANPIN_RETRY_MAX_DELAY（最多30秒）可在部署环境中调整。任务记录模型、提示词版本、次数、用量与脱敏错误码。提示词由prompts中的版本文件和哈希清单管理。崩溃遗留任务由用户核查后明确重试。

## 数据、测试与备份

默认数据库为 `runtime/qianpin.sqlite3`。原文件存放 `runtime/sources`，导出及审计文件存放 `runtime/exports`。原文件以哈希命名，数据库内记录相对路径，便于迁移。初始化可重复执行，不清空旧数据。`QIANPIN_RUNTIME_DIR` 和 `QIANPIN_DB_PATH` 可用于隔离演示库；默认路径按项目文件定位，不受启动目录影响。

```powershell
.\.venv\Scripts\python.exe -m pip install --require-hashes --only-binary=:all: -r requirements-dev-lock.txt
.\.venv\Scripts\python.exe -m mypy --config-file mypy.ini
.\.venv\Scripts\python.exe -m pytest tests -q --cov=services --cov=repository --cov=config --cov-fail-under=80
.\.venv\Scripts\python.exe -m scripts.backup_db
.\.venv\Scripts\python.exe -m scripts.restore_check runtime/backups/某份备份.sqlite3 runtime/restored.sqlite3
```

备份使用 SQLite 在线备份接口。恢复演练只写入新路径，不覆盖运行数据库；检查完整性、外键及关键表记录数。完整迁移还需复制 `runtime/sources` 和 `runtime/exports`，只有数据库备份不包含原始文件。

独立运行完整拟制演示并验证备份恢复（目标目录必须尚不存在）：

```powershell
.\.venv\Scripts\python.exe -m scripts.demo_flow --out-dir runtime/my-demo
$env:QIANPIN_RUNTIME_DIR = "$PWD/runtime/my-demo"
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address=127.0.0.1
```

脚本输出 `demo-report.json`，演示库与默认业务库隔离。结束演示并在同一终端返回默认库时执行 `Remove-Item Env:QIANPIN_RUNTIME_DIR`，再重启应用。

## 打包与可选部署

```powershell
.\.venv\Scripts\python.exe -m scripts.package_release
```

生成 `outputs/qianpin-*.zip`。白名单包含代码、依赖锁、样例、测试和说明，不含真实密钥、运行数据库或 `.venv`。解压后按上述安装命令复现。

Docker构建与容器冒烟已由GitHub验证。Compose仅暴露宿主机回环端口并挂载runtime，同时启用登录保护，需先按部署说明配置账号。非回环监听自动要求登录；本机127.0.0.1体验保持可用。实际对外试用仍须配置HTTPS与域名，首版仅运行一个应用实例。

## 范围和验证记录

首版采用整个输入快照的保守内容级依赖，可能出现人工判断后无需改写的提醒。审核和实际下载时再次读取当前依据；已下载文件和外部已发布内容需要经营者自行替换。

本地首版不含电商自动发布、开放客服、开放多品牌入驻、定时生效和句子级定位。真实 API 效果、用户试用、性能规模、评审视频和赛事提交材料仍需实际完成后记录。

参见 [实施记录](docs/IMPLEMENTATION.md)、[验收记录](docs/VALIDATION.md)、[演示步骤](docs/DEMO.md)。

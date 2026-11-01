# 本机运行与受保护部署

## 本机体验

run.cmd和.streamlit/config.toml默认监听127.0.0.1。继续用浏览器访问http://127.0.0.1:8501，无需为纯本机演示设置账号。侧栏仍填写本次操作人。

安装运行依赖时使用哈希校验：

```powershell
.\.venv\Scripts\python.exe -m pip install --require-hashes --only-binary=:all: -r requirements-lock.txt
```

开发和验收另装requirements-dev-lock.txt，之后运行：

```powershell
.\.venv\Scripts\python.exe -m pip install --require-hashes --only-binary=:all: -r requirements-dev-lock.txt
.\.venv\Scripts\python.exe -m mypy --config-file mypy.ini
.\.venv\Scripts\python.exe -m pytest tests -q --cov=services --cov=repository --cov=config --cov-fail-under=80
```

运行锁与开发锁分别包含跨平台分发文件哈希。依赖更新后用uv pip compile --generate-hashes --universal重新生成并验证，不手工填哈希。pip freeze只记录版本，不能生成哈希锁。

## 准备登录账号

只在自己的终端交互生成口令哈希，明文口令不作为命令参数，也不写入仓库：

```powershell
.\.venv\Scripts\python.exe -m scripts.create_password_hash
```

两次输入至少12字符的口令。程序输出PBKDF2哈希，将它填入本机.streamlit/secrets.toml；模型配置可继续保留在同一文件的deepseek/qwen段。

```toml
[access]
required = true
username = "reviewer"
password_hash = "将本机脚本输出的完整哈希填在这里"
session_seconds = 1800
```

也支持QIANPIN_AUTH_REQUIRED=true、QIANPIN_AUTH_USER与QIANPIN_AUTH_PASSWORD_HASH环境变量。口令哈希同样属于敏感配置，不提交GitHub。没有默认账号或通用口令。

非回环地址监听会自动要求登录，即便required=false也不能关闭这项保护。未配置有效账号时显示配置提示，并停止在业务数据初始化和查询之前。登录后操作人与审核人使用登录账号，不能在侧栏改名。连续5次失败后，该账号等待5分钟；会话默认30分钟到期。退出会撤销服务器会话，下载正文、原始资料和错误行时再次检查登录。

本轮提供单账号部署能力，不承诺多用户角色权限、多品牌隔离或企业单点登录。需要多人协作时再设计账号与品牌授权关系。

## Docker与对外试用

compose.yaml默认只映射宿主机127.0.0.1，并明确要求登录。先在宿主机配置好.streamlit/secrets.toml，再构建运行：

```text
docker compose build
docker compose up -d
docker compose logs --tail 80 web
```

runtime持久挂载；升级已有数据库前程序会生成pre-migration备份。对外访问在宿主机配置HTTPS反向代理到127.0.0.1:8501，保留应用登录。不要将容器端口直接公开为无需HTTPS的业务入口。

当前已经通过GitHub上的Linux镜像构建、容器内认证/迁移/单位测试和健康端点检查；自建Docker服务的域名、证书与公网网络尚未配置。现有Streamlit Community Cloud应用的更新方式与公开食品演示流程见[说明](OPEN_FOOD_FACTS.md)。

## 迁移、恢复和日志

schema版本使用PRAGMA user_version，首版基线为1，查询索引增量为2。已有未标版本的库先核验结构、在线备份，再在单个写事务中升级。失败整体回滚；新程序拒绝打开比自己更新的数据库。migrations中的已应用文件和提示词清单不直接修改，追加新版本。

升级前备份放在runtime/backups；JSON运行事件在runtime/logs/events.jsonl，按UTC午夜轮转并保留14份。事件只记录操作、结果、错误码、编号和耗时，操作人记摘要；正文、密钥、认证头与来源资料不进入日志。数据库审计记录保留原有人工依据与操作记录。

恢复时先停止应用，将备份恢复到新路径，用scripts.restore_check核验，另外保留原始sources和exports目录。不要用删除旧库或覆盖历史数据的方式处理升级问题。

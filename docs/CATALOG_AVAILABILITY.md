# 水饮分类503的处理与验收边界

## 已确认的事实

原分类请求为 `/api/v2/search?categories_tags=en:beverages&page_size=12&page=1&fields=...`。用户线上页面返回HTTP503，表示接口或上游网关没有正常提供结果，不能解释为“水饮没有商品”。当前分类参数是合法的，没有证据表明存在拼写错误。

核对官方OpenAPI定义及服务端源码后确认：默认查询还进行排序和总数统计。大分类可能涉及较多记录，这是可优化的请求成本，但尚不能证明它是线上503的唯一原因。

- [官方分类搜索与排序参数](https://github.com/openfoodfacts/openfoodfacts-server/blob/main/docs/api/ref/api.yaml)：支持 `sort_by=nothing` 取消默认排序。
- [官方查询实现](https://github.com/openfoodfacts/openfoodfacts-server/blob/main/lib/ProductOpener/Display.pm)：`estimate_result_count` 支持 `no_count=1` 跳过统计。此时响应中的 `count` 可能只是本页条数，不能当作全库总数。

## 本次改动

1. 分类请求添加 `no_count=1&sort_by=nothing`；保留字段过滤、每页12项和页码上限。
2. 水饮默认使用“饮用水”，另外提供果汁、茶饮料、碳酸饮料及原有综合分类。优先缩小范围，保留综合查询能力。
3. 500、502、503、504及网络异常最多额外重试一次，间隔0.5秒；每次请求都计入公共接口频率限制。403、429、重定向等不自动重试，不通过备用代理绕过限制。
4. 成功结果原子保存到 `runtime/food-catalog-cache/`，1小时内直接复用。上游故障时可回退到同一分类、同一页7天以内的真实成功结果，并标明缓存、获取时间及北京时间；不会使用其他分类、模拟记录或业务数据填充。
5. 缓存最多保留128页，每页文件限制2MB；过期或损坏缓存拒绝使用。失败请求不保存为空结果。缓存依赖磁盘文件，普通进程重启后可读取，Community Cloud重部署后是否保留取决于平台，不提供持久性承诺。
6. 不再统计总数；根据当前是否返回满页决定下一页按钮。最后满页之后可能再出现一个空页，可返回上一页。取消排序后，数据源更新可能影响分页顺序。

首次请求一直失败时没有历史成功页可回退，依然会提示上游故障；不会声称“缓存已彻底解决接口不可用”。图片功能和候选预览保留。

## 验证方法

```bash
.venv/bin/python -m pytest tests -q --cov=services --cov=repository --cov=config --cov-fail-under=80
.venv/bin/python -m mypy --config-file mypy.ini
.venv/bin/python -m scripts.check_food_catalog
.venv/bin/python -m scripts.check_food_catalog --subcategory 饮料与饮用水
```

诊断脚本绕过本地缓存，只做公共接口只读请求，不导入、不写业务数据库；输出成功返回的商品条码与名称，失败退出码为1。测试覆盖轻量参数、跳过统计时分页、503重试后恢复、非瞬态错误不重试、缓存隔离、缓存过期损坏，以及缓存时间提示和预览交互。模拟响应测试证明处理逻辑，不能作为公网接口恢复的证据。

## 尚待完成的真实接口复验

本次执行环境实际请求 `world.openfoodfacts.org` 被云环境代理拒绝，CONNECT返回403；这是此执行环境的网络白名单限制，和用户线上截图中的503不同，不能据此认定Streamlit站点也被403阻止。

已在本次云环境配置草稿中增加 `world.openfoodfacts.org` 和 `images.openfoodfacts.org`，未改变其他网络预设。草稿保存不代表正在运行的环境已放行。需要在本次Codex云环境设置中保存并发布配置后，重新执行上述诊断脚本，才能判断轻量请求在真实服务上是否成功；这不是向Streamlit Secrets填写密钥，也不需要Open Food Facts API Key。

公开网站仍需部署包含此修复的main提交。到时应分别验证饮用水、综合水饮及翻页；若优化请求仍持续503，需要依据真实响应继续判断上游服务状态，不应把未验收状态写成“已完全恢复”。

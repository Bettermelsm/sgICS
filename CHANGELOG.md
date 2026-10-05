# CHANGELOG

格式：`## [版本号] - 日期`，下挂 Added / Changed / Fixed。

## [v0.5.1] - 2026-10-05
### Fixed
- 回复日志 Admin 关闭手工新增/删除入口：之前所有字段只读导致新增页跳过必填的 session 外键，
  点保存报 IntegrityError；日志只能由消息泵生成、不可删（保审计完整性）

## [v0.5.0] - 2026-10-05
### Added
- 草稿审核流：ReplyLog 状态机（草稿/已发送/已转人工/已驳回/发送失败）+ 审核人/审核时间/发送时间审计；
  Admin 回复日志每行「审核」入口，审核页展示风控预检，确认发送（二次确认）/ 转人工 / 驳回
- 风控模块 `core/safety.py`：人工发送开关（每店默认关）、服务时间窗口（默认 9–23 北京时间）、
  频率限制（默认每店每 10 分钟 20 条）、熔断（近 30 分钟失败 3 次停发）；计数走 DB 跨进程有效；
  均可经环境变量调整（SEND_LIMIT_COUNT / SEND_LIMIT_MINUTES / SERVICE_HOURS / SEND_FAIL_STREAK_LIMIT）
- 轮询服务化：`poll_douyin` 默认轮询全部启用店铺，SIGTERM/SIGINT 优雅退出，失败指数退避；
  docker-compose 新增 `poller` 常驻服务
- `PollerHeartbeat` 心跳模型 + `check_douyin` 登录态检查命令；引导卡片 04 显示最后轮询时间/异常
- `DouyinAdapter.check_login()`：轻量登录态检查（不触发扫码流程），login() 复用
### Changed
- `poll_douyin --shop-id` 默认为空 = 全部启用店铺（原默认 shop-id 1）
- 真实发送唯一入口为 Admin 人工审核；`poll_douyin` 的 ALLOW_SEND=False 断言保留

## [v0.4.0] - 2026-10-05
### Added
- Mock 抖店工作台（`adapters/mock_workbench.html`）：模拟"商家后台 → 右上角「网页版飞鸽」"两步进入，
  含扫码登录遮罩（localStorage 持久模拟 cookie）、会话列表、消息面板、发送/转人工按钮，
  动作写入隐藏日志供自动化断言
- `demo_adapter --mock` 命令：Docker 里离线跑通 登录→轮询→发送→转人工 全流程（真实浏览器验证）
- 话术测试器：Admin → 关键词规则 →「话术测试」，输入一句话即显示命中哪条规则 / 转人工 / AI 兜底，
  含命中说明与耗时，只测试不入库不发送
- `pipeline_for_shop()` / `ruleset_for_shop()`：规则装配逻辑抽为共用函数（命令与 admin 视图共用）
- `PipelineResult.detail`：命中说明字段（命中哪条规则/关键词/AI 兜底）
### Changed
- 适配器入口两步化：商家后台 → 点「网页版飞鸽」（支持新标签页切换）；入口 URL 改由 `DOUYIN_ENTRY_URL`
  环境变量配置（fxg.jinritemai.com 已变为抖店官网，不再硬编码为工作台地址）
- 术语统一：用户界面统一称"抖店客服工作台"，"飞鸽"仅保留为产品原名备注
### Fixed
- `poll_douyin` 复用 `pipeline_for_shop()`，消除规则装配重复代码

## [v0.3.2] - 2026-10-05
### Added
- Admin 首页引导卡片：01 建店铺 / 02 配话术 / 03 接飞鸽 / 04 收草稿，
  每张卡片一句话做法 + 实时完成状态（店铺数/规则数/登录态/今日草稿数）

## [v0.3.1] - 2026-10-05
### Added
- Admin 右上角显示版本号（登录页表单下方同样显示），确认当前运行版本
- `core/version.py` 作为版本号唯一来源，随发布 tag 同步更新
### Fixed
- `core` 在 INSTALLED_APPS 中移至 admin 之前，使 admin 模板覆盖生效

## [v0.3.0] - 2026-10-05
### Added
- 抖店 Playwright 适配器完整实现：扫码登录（保存登录态）/ 轮询新消息 / 发送 / 转人工
- `login_douyin` 命令：无头截图二维码，手机扫码后保存登录态（之后免扫码）
- `poll_douyin` 消息泵：轮询→去重（内存+DB external_id 双重）→走流水线→存草稿
- `adapters/debug.py` 诊断包：失败自动收集截图/DOM/日志，供远程排错
- `docs/DOUYIN.md` 真实联调手册（含子账号最小权限建议）
- 迁移 0002：ChatMessage.external_id（平台消息 ID，消息去重用）
### Changed
- Dockerfile 安装 Playwright chromium（含系统依赖）
- docker-compose 挂载登录态与诊断目录到 /data 卷（重建不丢）
### 安全
- v0.3 全程草稿模式：`poll_douyin` 内 `ALLOW_SEND = False` 写死，
  `send_message` / `transfer_to_human` 已实现但无任何命令调用

## [v0.2.0] - 2026-10-05
### Added
- `check_glm` 命令：一键验证智谱 Key 有效性、模型名与往返延迟
- `demo_pipeline --multi`：多轮连续对话演示，验证上下文传递（建议配合 --real）
- GLM 网关加固：中文错误信息（Key 无效/限流/超时/空回复）、超时自动重试 1 次
- Admin 回复日志列表：显示客户名、店铺、消息预览
### Changed
- 网关异常统一为 GLMError（中文），便于一线排查

## [v0.1.0] - 2026-10-03
### Added
- Docker 化交付：Dockerfile / entrypoint.sh / docker-compose.yml，
  `docker compose up --build` 一行启动
- 数据库路径可配（DB_PATH），数据落挂载卷持久化
- 容器首次启动自动迁移 + 自动创建 demo 管理员账号
- README 增加 Docker 一行启动说明
### Changed
- README 重组：Docker 为推荐方式，Python 直装为备选

## [v0.0.0] - 2026-10-03
### Added
- 项目起点：Django demo 骨架
- 回复流水线（转人工→关键词→AI兜底→默认回复→出站替换）
- LLM 网关（GLM 真实 / Mock 离线）
- Django admin 演示工作台（店铺/会话/三类规则/回复日志）
- 抖店 Playwright 适配器骨架与契约
- 演示命令 `demo_pipeline` 与 7 个单测

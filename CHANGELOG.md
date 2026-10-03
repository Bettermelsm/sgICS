# CHANGELOG

格式：`## [版本号] - 日期`，下挂 Added / Changed / Fixed。

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

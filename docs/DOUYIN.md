# 抖店真实联调手册（v0.4）

目标：把机器人接到你真实的抖店客服工作台（飞鸽），**只收消息、只存草稿，不发送**。

> 入口说明（2026-10-05 查证）：`fxg.jinritemai.com` 现已变为抖店官网（商家入驻页），
> 不再是工作台入口。网页版飞鸽改从**抖店商家后台右上角「网页版飞鸽」**进入。
> 真实入口地址用环境变量 `DOUYIN_ENTRY_URL` 配置（见下）。

## 0. 前置准备

1. **建议开一个客服子账号给机器人**（而非主账号）：
   抖店后台 → 子账号管理 → 新建客服子账号，只给"接待/查看会话"权限，
   不给改价、退款、导出客户信息等权限。最小权限，出事面小。
2. 更新代码并重建镜像（v0.4 加了 Playwright 浏览器，首次构建多几分钟）：
   ```bash
   cd /mnt/e/03FDE/SGA20260930FD01/Process/cs-demo
   git pull
   docker compose up --build -d
   ```
3. 在 Django Admin（http://localhost:8000/admin）新建一个店铺账号，
   名称写你的真实店名，**保持"自动回复"关闭（草稿模式）**。
   记下它的 ID（一般是 2，演示店铺是 1），下面命令用 `--shop-id` 指定。
4. 配置真实入口：在 `.env` 或 compose 环境里设置
   `DOUYIN_ENTRY_URL=你的抖店商家后台地址`（登录后右上角点「网页版飞鸽」）。

## 0.5 先在 Mock 页验证（Docker 里可跑，无需账号）

```bash
docker compose exec web python manage.py demo_adapter --mock
```

离线跑通 登录→轮询→发送→转人工 全流程，确认环境里的 Playwright 没问题，
再进行下面的真实联调。

## 1. 扫码登录

```bash
docker compose exec web python manage.py login_douyin
```

- 容器里打开商家后台 → 点右上角「网页版飞鸽」，把二维码截成 `qr.png`
- 终端会打印 qr.png 的路径；**用手机把图片传出来扫码**
  （`docker compose cp web:/app/qr.png ./qr.png` 可把图拷到 WSL 里）
- 扫码确认后自动保存登录态到 `douyin_state.json`，之后免扫码
- 登录态过期（一般几周）时重跑一次本命令即可

## 2. 轮询收消息（先单轮试）

```bash
docker compose exec web python manage.py poll_douyin --shop-id 2 --once
```

- 拉取会话列表 → 去重入库 → 走回复流水线 → **存草稿**
- 去 Admin → 回复日志查看生成的草稿（来源标记为 `keyword:draft` / `ai:draft` 等）
- 单轮正常后，持续跑：
  ```bash
  docker compose exec web python manage.py poll_douyin --shop-id 2 --interval 10
  ```
  Ctrl+C 退出。

## 3. 出问题时：发诊断包

任何一步失败，命令会自动在诊断目录下生成
`debug/<步骤>-<时间>/`（容器内路径 `/data/debug`，宿主机拷出：`docker compose cp web:/data/debug ./debug`），内含：

- `screenshot.png` — 失败时的页面截图
- `dom.html` — 完整页面 HTML（用于校准选择器）
- `info.txt` — URL、操作日志、异常堆栈

把整个目录发给开发者，修完 push 后你 `git pull` 重建镜像再跑。
**预期**：第一轮大概率需要校准选择器（真实工作台 DOM 未公开），
1–2 个来回后稳定。

## 4. v0.4 明确不做的事

- ❌ 真实环境不自动发送：`poll_douyin` 里 `ALLOW_SEND = False` 写死
- ❌ 真实环境不自动转人工：`transfer_to_human` 同上
- ❌ 不处理图片/订单卡片消息：只处理文本

发送与转人工的方法已在 Mock 页上真实验证通过（见 `demo_adapter --mock`），
真实环境的发送放行流程留到后续版本单独设计。

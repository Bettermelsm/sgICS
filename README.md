# 智能客服 Demo（Django 版）

Django 自研路线第一步：**大脑先跑通**。本 demo 实现原 ChatGPT-On-CS 的
回复流水线（转人工 → 关键词 → AI兜底 → 默认回复 → 出站替换），
LLM 接智谱 GLM，抖店客服适配器（飞鸽工作台）以 Playwright 网页自动化为方案（骨架已就绪，
真实店铺联调为下一版本）。

## 零、Docker 一行启动（v0.1 推荐）

前置：安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)
（Win11 需开启 WSL2 与 BIOS 虚拟化）。

> 国内构建加速：Docker Desktop → Settings → Docker Engine，
> 在 `registry-mirrors` 中添加 `["https://docker.m.daocloud.io"]`，
> 否则拉取基础镜像可能很慢。Dockerfile 中的 pip 已默认走国内镜像。

```bat
:: 解压后进入目录，复制环境文件
copy .env.example .env
:: 需要真实 GLM 时，把 ZHIPU_API_KEY 填进 .env（先不填也行，离线演示）

:: 一行启动
docker compose up --build
```

- 工作台：http://localhost:8000/admin/（账号 `admin` / 密码 `admin123`）
- 离线演示：`docker compose exec web python manage.py demo_pipeline`
- 多轮对话演示：`docker compose exec web python manage.py demo_pipeline --multi`
- GLM 连通性检查（需先在 .env 填 ZHIPU_API_KEY）：
  `docker compose exec web python manage.py check_glm`
- 真实 GLM 演示：`docker compose exec web python manage.py demo_pipeline --real`
- 真实 GLM 多轮演示：`docker compose exec web python manage.py demo_pipeline --real --multi`
- 适配器全流程演示（Mock 工作台，离线可跑）：
  `docker compose exec web python manage.py demo_adapter --mock`
- 跑单测：`docker compose exec web python manage.py test`
- 数据持久化在 Docker 卷 `csdata` 中，重建容器不丢

下面是**不装 Docker、直接用 Python** 的方式（二选一即可）。

## 一、Win11 环境准备（零基础按顺序做）

0. 先把本项目文件夹放到电脑上（例如解压到 `D:\cs-demo`）
1. 安装 Python 3.11+：
   - 打开 https://www.python.org/downloads/ ，点黄色的 "Download Python 3.x" 按钮下载 64 位安装包
   - 运行安装包，**第一屏务必勾选 "Add python.exe to PATH"**，再点 Install Now
   - 验证：按 `Win+R` 输入 `cmd` 回车，输入 `python --version`，能显示版本号即成功
   - 若提示"不是内部命令"：说明上一步没勾选 PATH，卸载重装一次并勾选
2. 打开项目所在文件夹，在地址栏输入 `cmd` 回车（终端会自动定位到该目录）
3. 创建虚拟环境（避免污染系统 Python）：
   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   ```
   成功后命令行最前面会出现 `(.venv)` 字样
4. 安装依赖（约几分钟）：
   ```bat
   pip install -r requirements.txt
   ```
   若下载很慢，用国内镜像：
   ```bat
   pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
   ```
5. Playwright 浏览器（第二步真实店铺联调用，第一步可跳过）：
   ```bat
   playwright install chromium
   ```
6. 配置：复制 `.env.example` 为 `.env`（直接复制文件改名）
   - 离线演示：什么都不填（自动用 Mock AI）
   - 真实 GLM：填入 `ZHIPU_API_KEY`（https://open.bigmodel.cn/ 控制台获取），
     `GLM_MODEL` 按控制台当前可用模型名填写

## 二、启动

```bat
python manage.py migrate
python manage.py createsuperuser   :: 按提示设 admin 账号
python manage.py runserver
```

浏览器打开 http://127.0.0.1:8000/admin/ ：
- **店铺账号**：可看到"演示店铺"（运行 demo 命令后自动创建），`自动回复` 默认关闭 = 草稿模式
- **关键词规则 / 转人工规则 / 出站替换规则**：演示用，可按自己店铺话术修改
- **会话 / 回复日志**：跑完 demo 后可查看完整决策记录

## 三、跑演示（不用真实店铺）

```bat
python manage.py demo_pipeline           :: 离线演示（Mock AI）
python manage.py demo_pipeline --real    :: 调真实 GLM（需先配 ZHIPU_API_KEY）
```

会依次模拟三条客户消息：关键词命中 → 转人工关键词 → 普通咨询（AI兜底），
终端打印每条的决策来源、耗时、是否可发送。演示给别人看时建议开 `--real`。

## 四、跑测试

```bat
python manage.py test
```

## 五、第二步：接真实抖店（v0.3 联调中）

详见 `docs/DOUYIN.md` 联调手册。三条命令：

```bash
docker compose exec web python manage.py login_douyin              # 扫码登录
docker compose exec web python manage.py poll_douyin --shop-id 2 --once   # 单轮试跑
docker compose exec web python manage.py poll_douyin --shop-id 2   # 持续轮询
```

**铁律**：v0.3 全程草稿模式，只收消息、只存草稿，不发送。
真实发送与转人工验证留到 v0.4。

## 六、后续演进方向

- 实时推送：Django Channels（WebSocket）把新消息推到工作台
- 后台任务：Celery + Redis 做消息轮询、发送重试、DLQ
- 工作台前端：admin 先顶 demo，正式版做独立前端页面
- 更多平台：按 `adapters/base.py` 契约新增拼多多/千牛适配器
- 知识库 RAG：商品/售后文档向量检索，接到 AI 兜底之前

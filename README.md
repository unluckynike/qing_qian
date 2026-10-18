# 青签 · qing_qian

基于**吕祖灵签**(一百签)的求签、解签网页应用。

> 设计原则:**随机归随机、签文归典籍、模型只做解读。**
> 抽签由后端安全随机数决定;签诗/解曰/卦象/分项释义来自固定签文库;AI 仅结合所问之事做个性化白话解读。
>
> 仅供传统文化娱乐参考,请勿迷信。

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.10 · FastAPI · SQLAlchemy 2.0(psycopg2)· OpenAI 兼容 SDK |
| 前端 | Vue 3 · Vite · TypeScript · GSAP(道观古风 UI,微动画) |
| 数据库 | PostgreSQL 16(Docker Compose,启动自动建表) |
| 签文库 | `backend/data/lvzu_signs.json`(100 签,随仓库版本管理) |

## 目录结构

```
qing_qian/
├── DESIGN.md                    # 设计蓝图(架构/数据/API/AI 全案)
├── docker-compose.yml           # PostgreSQL 16
├── backend/
│   ├── app/                     # FastAPI 应用(routers/services/orm)
│   ├── data/lvzu_signs.json     # 100 签签文库(唯一数据源)
│   ├── scripts/scrape_zhouyi.py # 签文抓取脚本(带缓存,可重跑)
│   ├── requirements.txt
│   └── .env.example             # 配置样例
├── frontend/                    # Vue3 单页应用(4 个页面)
└── gui-test-screenshots/        # 浏览器实测截图(证据留档)
```

## 快速开始

**1. 起数据库**

```bash
docker compose up -d db        # postgres:16-alpine → localhost:5432
```

**2. 起后端**(Python 3.10)

```bash
cd backend
python3.10 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env           # 按需填写 LLM_API_KEY
.venv/bin/uvicorn app.main:app --reload --port 8000
```

**3. 起前端**

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173(vite 代理 /api → 8000)
```

## 配置(`backend/.env`)

| 变量 | 说明 | 默认 |
|---|---|---|
| `DATABASE_URL` | 数据库连接串 | 对应 docker-compose 的 qingqian 库 |
| `LLM_API_BASE` | OpenAI 兼容接口地址 | 智谱 `https://open.bigmodel.cn/api/paas/v4` |
| `LLM_API_KEY` | **必填才能用 AI 解签**;不填时抽签与静态签文照常可用 | 空 |
| `LLM_MODEL` | 模型名 | `glm-4-flash` |
| `LLM_TEMPERATURE` / `LLM_MAX_TOKENS` | 解签参数 | 0.8 / 1200 |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | **后台管理账号**(密码为空时后台接口不可用) | admin / 空 |
| `ADMIN_TOKEN_HOURS` | 后台登录有效期(小时) | 12 |

**优雅降级**:未配置 `LLM_API_KEY` 时,`/api/interpret` 返回 503 并提示配置方式;前端隐藏入口并展示提示条,签文阅读不受影响。数据库不可用时同样降级(抽签不落库)。

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查(含 LLM 配置状态) |
| GET | `/api/signs` | 100 签列表 |
| GET | `/api/signs/{no}` | 单签完整详情 |
| POST | `/api/draw` | 安全随机抽签 → `{drawing_id, sign}` |
| POST | `/api/interpret` | AI 解签,SSE 流式;支持追问(带 `reading_id` + `history`) |
| GET | `/api/history` | 最近抽签与解签记录 |
| POST | `/api/admin/login` | 后台登录(换取令牌) |
| GET/PUT/POST/DELETE | `/api/admin/*` | 后台管理:概览 / 签文记录 / 用户 / AI 配置(需 Bearer 令牌) |

## 后台管理

访问 `/#/admin`,账号取自 `backend/.env` 的 `ADMIN_USERNAME` / `ADMIN_PASSWORD`(示例默认 `admin` / `qingqian-admin`,**公开部署前务必修改**)。

| 模块 | 功能 |
|---|---|
| 概览 | 抽签 / 解签 / 追问 / 用户计数、今日抽签、AI 配置状态 |
| 签文记录 | 最近抽签与解签记录(分页),可删除(级联删除对应解签与追问) |
| 用户管理 | 用户列表与删除(历史抽签记录保留) |
| AI 配置 | base_url / 模型 / 温度 / 输出上限 / API Key,保存即生效,支持连通性测试;密钥仅存本机数据库且脱敏展示 |

AI 配置存于数据库 `settings` 表,**优先于 .env**;清空对应配置(或删除行)即回退到 .env。

SSE 事件:`data: {"delta": "…"}` 逐段 → `data: {"done": true, "reading_id": …}` → `data: [DONE]`。
解签落库:首答写 `readings`,追问写 `messages`(每次调用记录 `model` 与 `prompt_version`)。

## 签文库与抓取

签文库来源:zhouyi.cc 吕祖灵签 100 签详情页(古典原文属公版;白话释义整理自公开网页,仅内部参考)。

```bash
python3 backend/scripts/scrape_zhouyi.py            # 全量(优先命中页面缓存)
python3 backend/scripts/scrape_zhouyi.py --limit 3  # 调试
python3 backend/scripts/scrape_zhouyi.py --no-cache # 强制重新抓取
```

已知源站缺口(源站自身缺失,非解析问题):第 82 签卦象并入解曰(已提取)、第 97 签卦象为空、第 90 签无白话详解段且缺“行人/诉讼”两项释义。

## 生产模式

前端构建产物由后端直接托管:

```bash
cd frontend && npm run build     # 产出 frontend/dist,自动挂载到 FastAPI "/"
```

之后仅启动后端(8000)即可对外服务(接口 + 页面同源)。

## 测试留档

`gui-test-screenshots/` 为浏览器黑盒实测截图:求签全流程、摇签瞬时态、签文详情(竖排签牌)、签文库检索、签事记落库记录。GUI 测试中发现并修复:竖排签诗折列错位、顶栏透明度过高。

## 合规

- 全站及 AI 输出均带“仅供传统文化娱乐参考”声明;
- 提示词原则:签文原文不改写、不做医疗/投资/法律具体建议;
- 公开部署前请替换白话释义为基于公版古文的自行整理版本,并按生成式 AI 合规路径评估。

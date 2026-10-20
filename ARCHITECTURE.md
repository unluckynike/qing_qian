# 青签 · 系统架构设计

> 版本:v1.0 · 2026-10-20
> 配套文档:[DESIGN.md](DESIGN.md)(设计蓝图)· [README.md](README.md)(使用说明)
> 本文档包含两部分:**当前架构设计**(现状说明)与**架构评估**(合理性分析与演进建议)。

---

## 1. 设计原则

| 原则 | 落地方式 |
|---|---|
| 随机归随机 | 抽签用 `secrets` 安全随机,**不经过任何外部服务** |
| 签文归典籍 | 100 签签文库 JSON 是唯一数据源,AI 不可改写签文 |
| 模型只做解读 | LLM 仅在解读环节被调用,失败/未配置不影响静态功能 |
| 配置即数据 | AI 配置存入数据库(DB 优先于 .env),后台改完即生效 |
| 优雅降级 | 无 API Key、数据库不可用、未启用后台,三种场景都不阻断核心功能 |
| 动效服务内容 | 微动画克制(reduced-motion 跳过),并有看门狗兜底保证内容始终可见 |

---

## 2. 系统全景

```
┌─────────────────────────── 浏览器 (Vue3 SPA) ───────────────────────────┐
│  视图层 5 路由:  求签(/) · 签文详情(/sign/:no) · 签文库(/library)         │
│                 签事记(/history) · 后台管理(/admin)                      │
│  API 客户端(api.ts): REST + SSE 流式解析;admin 令牌(localStorage)        │
│  动效层: 页面过渡(CSS) + GSAP 入场时间线(context 作用域 + 看门狗)         │
│  样式层: CSS 变量设计系统(宣纸/朱砂/鎏金) + 响应式断点 600/700/860        │
└──────────────┬──────────────────────────────────────────────────────────┘
               │ HTTP / SSE          ┌──────────────────────────┐
┌──────────────▼──────────────────┐  │  外部服务                 │
│      FastAPI 后端 (:8000)       │  │  LLM(OpenAI 兼容)        │
│                                 │  │  默认智谱 GLM,可后台切换  │
│  路由层 routers/ (薄,14 接口)    │  └─────────▲────────────────┘
│   ├ signs.py      签文库查询     │            │ httpx(仅 interpret/test)
│   ├ divination.py 抽签/解签/历史 │            │
│   └ admin.py      后台(9 接口)   │────────────┘
│                                 │
│  服务层 services/ (领域逻辑)     │   ┌──────────────────────────┐
│   ├ signstore.py 签文库加载/随机  │   │  签文库(唯一典籍数据源)   │
│   ├ prompt.py    提示词组装(v2)  │◀──┤  backend/data/           │
│   ├ llm.py       流式客户端/测试  │   │  lvzu_signs.json(100 签) │
│   └ ai_config.py 动态配置(DB>env)│   │  随 Git 版本管理          │
│                                 │   └──────────────────────────┘
│  持久层 orm.py (SQLAlchemy 2.0) │
└──────────────┬──────────────────┘
               │ psycopg2(连接池,不可用自动降级)
┌──────────────▼──────────────────┐
│   PostgreSQL 16 (Docker Compose)│
│   users / drawings / readings   │
│   / messages / settings         │
└─────────────────────────────────┘
```

**代码规模**:后端 14 个 Python 文件约 940 行;前端 11 个源文件约 1460 行;API 共 14 个端点(签文 2 + 求签解签 3 + 后台 9)。

---

## 3. 分层设计

### 3.1 后端分层(单向依赖:路由 → 服务 → 持久层)

| 层 | 文件 | 职责 | 约束 |
|---|---|---|---|
| 路由层 | `routers/signs.py` `divination.py` `admin.py` | HTTP 出入参、状态码、SSE 封装 | 薄,不写业务规则 |
| 服务层 | `signstore` `prompt` `llm` `ai_config` | 签文库、提示词、模型调用、配置解析 | 不感知 HTTP |
| 持久层 | `orm.py` `db.py` | 表定义(带注释)、引擎/会话 | 表结构唯一出处 |

**关键机制**

- **降级开关**:`db_ready()` 每次请求实时探测;库不可用时抽签不落库、配置回退 .env、后台接口返回 503 —— 全站核心功能不受影响。
- **配置优先级链**:`settings 表(后台写入) > .env 默认值`,由 `ai_config.get_ai_config()` 统一解析并做类型归一;每次调用实时读取,改配置**无需重启**。
- **鉴权**:单管理员账号(.env),登录换 HMAC-SHA256 签名令牌(含过期时间,密钥派生自账号密码),密码变更即令旧令牌全部失效;`Authorization: Bearer` 校验。

### 3.2 前端架构

| 模块 | 文件 | 说明 |
|---|---|---|
| 应用外壳 | `App.vue` `main.ts` `router.ts` | 顶栏/页脚、路由过渡、5 个路由(懒加载) |
| API 客户端 | `api.ts` | REST 封装、统一错误提取、SSE 增量解析(`\n\n` 分帧)、admin 令牌管理 |
| 视图 | `views/*.vue` ×5 | 求签 / 签文详情 / 签文库 / 签事记 / 后台管理 |
| 设计系统 | `styles.css` | CSS 变量(色/字/影)、组件类(面板/按钮/签牌/表格)、响应式断点 |
| 动效 | 视图内 GSAP + `App.vue` 过渡 | **作用域化**:`gsap.context(scope)` + `onUnmounted revert()`;**看门狗**:4s 强制清动画内联样式 |

**状态策略**(刻意保持轻量):无全局状态库;服务端数据按需拉取;仅 admin 令牌持久化于 localStorage。当前 5 页规模下成立(规模阈值见 §6)。

### 3.3 数据架构

| 数据 | 载体 | 理由 |
|---|---|---|
| 签文库(100 签) | JSON(随 Git) | 只读、体量小、需人工审校与版本追溯 |
| 抽签/解签/追问 | PostgreSQL 5 表 | 会增长、需关联查询、后台管理 |
| AI 运行时配置 | settings 表 | 前台后台共享、即时生效 |

```
users(id, openid, nickname, created_at)                       -- 登录体系预留
drawings(id, user_id→users, sign_no 1-100, category, question, created_at)
readings(id, drawing_id→drawings CASCADE, model, prompt_version, content, created_at)
messages(id, reading_id→readings CASCADE, role user/assistant, content, created_at)
settings(key PK, value, updated_at)                           -- AI 配置(优先于 .env)
```

全部表/列/约束带中文注释(建表自动写注释;存量库用 `scripts/apply_comments.py` 同步)。

---

## 4. 关键流程

### 4.1 抽签(不经 LLM)

```
用户填所问/选分类 → POST /api/draw → secrets 随机 1-100 → 查签文库 → 落库 drawings
→ 返回 {drawing_id, sign 全文} → 前端动画 ≥2s → 跳转 /sign/:no(fresh=1)
```

### 4.2 AI 解签(SSE 流式)

```
POST /api/interpret {sign_no, question, drawing_id?}
→ 校验(长度/注入词黑名单) → signstore 取签文
→ prompt.build(签文注入 system + history + 当前问题)
→ ai_config 取有效配置 → LLM 流式
→ 逐段 SSE: {"delta"} → 完成落库 readings → {"done", reading_id} → [DONE]
追问: 带 reading_id + history → messages 追加记录
```

### 4.3 后台配置生效

```
后台表单 → PUT /api/admin/settings → settings 表 upsert
→ 下次 /api/interpret 调用时 ai_config 读到新值 → 立即生效(无需重启)
「测试连接」:POST /settings/test → 用当前有效配置发最小请求,返回模型/延迟
```

---

## 5. 部署形态

| 形态 | 组成 | 说明 |
|---|---|---|
| 开发 | PG(Docker) + uvicorn(8000) + vite(5173 代理 /api) | `npm run dev` 热更新 |
| 生产 | PG(Docker) + uvicorn 单进程 | `npm run build` 后 FastAPI 直接托管 `frontend/dist`(同源,免 CORS) |
| 数据备份 | Docker 卷 `pgdata` | 签文库随 Git;备份 `pg_dump` 即可 |

---

## 6. 架构评估

### 6.1 合理之处(经实测验证)

1. **职责边界**清晰:签文库(JSON)与动态数据(DB)彻底分离,`sign_no` 仅是 1-100 的弱引用,不存在双写/同步问题;
2. **降级链完整**且互相独立:无 Key(503+前端提示)、无库(不落库仍可抽签)、无后台(503),核心体验(抽签+静态签文)永久可用;
3. **提示词可追溯**:`readings` 记录 `model + prompt_version`,改口径可回查历史;
4. **配置即数据**:AI 参数后台即改即生效,运维成本趋近于零;
5. **动效有防护**:GSAP 全部作用域化 + 卸载回收 + 看门狗兜底,实测在渲染被节流的环境下仍保证内容可见;
6. **表注释规范**:schema 自文档化,配合 DBeaver 直接可读。

### 6.2 技术债与风险(按优先级)

| # | 项 | 现状 | 风险/建议 |
|---|---|---|---|
| 1 | 无自动化测试 | 仅 GUI 测试截图留档 | 建议补 pytest(接口冒烟)+ vitest(组件),接 CI |
| 2 | 无限流/缓存 | 直接透传 LLM | 公开部署前加:IP/令牌限流、热点签文缓存(Redis 可选) |
| 3 | SSE 无断线重连 | 流中断即报错,已显示内容保留 | 可加 retry 事件或前端自动重试 |
| 4 | 管理员体系单一 | .env 单账号 | 需要多管理员时迁 `users.role` 表驱动 |
| 5 | 用户体系 | ✅ 用户名+密码注册/登录已上线(记录归属、签事记隔离) | 手机号短信验证码/微信登录可按需扩展(users.phone 字段预留) |
| 6 | 签文库检索在前端 | 100 条全量加载,内存过滤 | 当前体量合理;如需全文检索再入库(PG tsvector) |
| 7 | prompt 版本是手工字符串 | v2 | 频率上升后可文档化变更记录 |

### 6.3 演进路径(触发条件驱动,不提前建设)

```
公开部署  → 限流 + 缓存 + 生成式 AI 合规(见 DESIGN.md §10)
用户增长  → users 表启用 + 登录 + 历史归户
签量变大  → 签文库入库 + 全文检索(JSON 仍为审校源)
运维需求  → metrics 接口/日志聚合 + CI 流水线
```

---

## 7. 自适应(响应式)设计规范

### 7.1 断点

| 断点 | 规则 |
|---|---|
| ≤ 860px | 签文页双栏(古文解/白话)降为单栏;`.grid-2` 纵向堆叠 |
| ≤ 700px | 签诗字号 25→17px、字距收紧;**签诗允许自然换行**(长句不再溢出) |
| ≤ 600px | 顶栏压缩:隐藏副标题、导航内边距收缩 |
| ≤ 560px | 快捷入口卡片单列 |

### 7.2 排版自适应规则

- **签诗**:`white-space: normal + overflow-wrap: anywhere + text-wrap: balance`(支持时自动均衡分行),左右对称留白;右侧留白同时避让「青签印」印章,任何宽度下文字不压印章、不溢框;
- **表格**(后台):容器 `overflow-x: auto` 横向滚动,不挤压列;
- **网格**(签文库/分项释义/统计卡):`auto-fill + minmax` 自动降列;
- **动效**:`prefers-reduced-motion` 全部跳过;GSAP 看门狗兜底(节流环境 4s 后强制可见)。

### 7.3 验证记录

| 场景 | 结果 |
|---|---|
| 窄窗 565×851(用户实际场景) | 无横向溢出,签诗完整在框内 ✓ |
| 移动 390×844 | 无横向溢出,签诗完整在框内 ✓ |
| 桌面 1280×720 | 双栏布局,长签诗自动两行均衡 ✓ |

---

## 8. 安全与合规要点

- 后台:单管理员 + 签名令牌(密码变更即失效);密钥脱敏展示(仅留末 4 位);
- 注入防护:所问之事 ≤100 字 + 特征词黑名单(前后端双层);
- 数据:`.env` 不入库不入 Git;签文库古典原文公版,白话释义来源声明见 README;
- 全站及 AI 输出均带"仅供传统文化娱乐参考"声明。

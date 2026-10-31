# 项目结构 · 江山行止 · 文献

## 一、顶层一览

```
poem-data/
├── data/           发布物（JSON，唯一真相之一）
├── schema/         数据契约（JSON Schema）
├── shared/         共享表（版本、书目）
├── web/            前端（零构建，单页）
├── server/  Django 后端（admin + API）
├── scripts/        校验、索引、闸门、本地服务
├── docs/           文档
├── README.md  LICENSE  .gitignore  .env.example
```

## 二、每个目录是什么、要不要

| 路径 | 是什么 | 进 git | 必要性 |
|---|---|---|---|
| `data/` | 作品/人物/行迹/评点，一文件一条 | ✅ | **必须**，这是发布物 |
| `data/index.json` | 列表索引，由 `scripts/build-index.mjs` 生成 | ✅ | **必须**，前端与 API 都要 |
| `schema/` | 四个 JSON Schema：work / comment / person / journey | ✅ | **必须**，前后端与校验器共用 |
| `shared/` | `editions.json`（版本表） | ✅ | **必须**，作品用 id 引用 |
| `web/` | 前端单页与资源 | ✅ | **必须** |
| `server/` | Django 工程（`atlas/` 配置、`corpus/` 应用） | ✅ | **必须** |
| `server/.venv/` | Python 虚拟环境 | ❌ | 本地生成，可随时重建 |
| `server/staticfiles/` | `collectstatic` 产物 | ❌ | 部署时生成 |
| `server/db.sqlite3` | 本地开发库 | ❌ | 本地生成，可随时 `import_json` 重建 |
| `__pycache__/`、`*.pyc` | Python 字节码 | ❌ | 自动生成 |
| `scripts/` | 校验器、索引生成、提交闸门、本地静态服务 | ✅ | **必须** |
| `docs/` | 结构与 AI 编码规范 | ✅ | **必须** |
| `.env` | 真实凭据 | ❌ | 本地私有，**永不入库** |
| `.env.example` | 键名与占位值 | ✅ | 必须，给人看怎么配 |

## 三、已删除的东西

| 曾存在 | 删除原因 |
|---|---|
| `viewer-debug.html` | 早期调试用查看器，被 `web/index.html` 取代，0 处引用 |
| `server/`（FastAPI） | Django 确定为后端；线上 8081 跑的是服务器上的副本，本地删除不影响 |

## 四、数据流向

```
data/*.json ──import_json──▶ 数据库（SQLite 本地 / PostgreSQL 线上）
                                  │  admin 修改
                                  ▼
                            export_json ──▶ data/*.json ──git──▶ 发布
                                  │
                            --check 闸门（不一致即拒绝提交）
```

**规矩：一次只有一个真相。** 本地开发用 SQLite；线上用 PostgreSQL；
`data/*.json` 始终是「发布物」，承载 git 的版本与审查。

## 五、命名与放置规则

| 要放什么 | 放哪 |
|---|---|
| 一条新作品 | `data/works/<题名>.json` |
| 一条新人物 | `data/persons/<拼音>.json` |
| 一条新行迹 | `data/journeys/<拼音>.json` |
| 一条评点 | `data/comments/<作品key>.json`（无评点则不建文件） |
| 新字段 | 先改 `schema/`，再改模型与导入导出 |
| 新命令 | `server/corpus/management/commands/` |
| 新校验 | `scripts/validate.mjs` |
| 新文档 | `docs/` |

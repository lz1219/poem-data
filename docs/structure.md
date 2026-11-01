# 项目结构 · 江山行止 · 文献

项目目标和取舍见 [project-charter.md](project-charter.md)，内容质量见 [editorial-policy.md](editorial-policy.md)；本文只说明文件职责与实际数据流。

完整古籍库补全按[corpus-data-plan.md](corpus-data-plan.md)实施。原PostgreSQL的book/text_unit/paragraph通过语料API提供整书阅读；与下述精选作品JSON编辑/发布流分工不同，不将整部语料重复放入works目录。

## 一、顶层一览

```
poem-data/
├── data/           发布物（JSON，发布唯一真相）
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
| `schema/` | JSON Schema：work / comment / person / journey / research | ✅ | **必须**，前后端与校验器共用 |
| `shared/` | `editions.json`（版本表） | ✅ | **必须**，作品用 id 引用 |
| `research/ingest.sql` | 完整原件与整理数据的隔离库结构，不属于公开正文 | ✅ | 配合 `scripts/raw_ingest.py`；操作见 [data-ingestion.md](data-ingestion.md) |
| `scripts/backfill_shiji.py` / `server/corpus/sql/0001_corpus_origins.sql` | 固定《史记集解》版本的原库增量导入与来源关联；默认预览 | ✅ | 复用book/edition/text_unit/paragraph；实际范围与验收见 [首批补库报告](reports/corpus-backfill-0002.md) |
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

**规矩：经审查的 JSON 是发布真相。** 数据库是编辑与研究工作台；本地开发用 SQLite，线上用 PostgreSQL；
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

## 学术资料增补

来源在 shared/sources.json；公开研究记录、修订与摘引在 data/research、data/research-history、data/witnesses。完整采集原件在仓库外 .local 及语料库 research_ingest 隔离区，备份和内部研究线索留仓库外；完整原件与内部正文不进入静态发布包。research-index.json 由研究脚本或数据库导出生成。

典籍库存与缺口见 [book-register.md](book-register.md)，入库命令与校验边界见 [data-ingestion.md](data-ingestion.md)。data/book-register.json 为书目和版本覆盖快照，data/ingestion-report.json 为最终处理报告；存储通过和学术待核分别报告。

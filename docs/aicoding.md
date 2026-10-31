# AICoding 规范 · 江山行止 · 文献

> 本文件约束「在这个仓库里写代码的人和 AI」。
> 冲突时优先级：**运行中的代码 > `schema/` > 本文件 > README**。

## 0. 先读什么

动手前依次读：`docs/structure.md`（放哪）→ `schema/*.json`（契约）→ 本文件（怎么做）。
不清楚就停下来问，**尤其涉及删除、改契约、改部署**。

## 1. 五条不可妥协

1. **数据是资产，代码是容器。** 先确认数据形状，再写代码；反过来的改动一律驳回。
2. **一次只有一个真相。** JSON 或数据库，二选一；切换靠部署配置，不允许两边同时可写。
3. **一切叙述必须有据。** `source` / `basis` 缺一即校验失败，不设例外。
4. **评点与赏析分线。** 古人的话进 `commentary`（四要素齐全），我们的话进 `appreciation`（标「本站自撰」）。**AI 生成的文字永远不许进评点。**
5. **不手改生成物。** `data/index.json`、导出文件由命令产出；要改就改源，再跑命令。

## 2. 改动的标准流程

| 你要改 | 顺序 |
|---|---|
| 加字段 | `schema/` → `scripts/validate.mjs` → `corpus/models.py` → `import_json` / `export_json` → 跑往返 |
| 加作品 | 新建 `data/works/<key>.json` → `import_json` → `export_json --check` |
| 改后台 | `corpus/admin.py` / `forms.py`，**校验写在 `model.save()`，不写在视图** |
| 加接口 | `corpus/views.py` + `corpus/urls.py`，路径与既有风格一致（`/api/<复数>`、`/api/<复数>/<key>`） |
| 改数据结构 | 先提 issue 说清影响面，再动；**这类改动必须人工确认** |

## 3. 提交前必须

```bash
node scripts/check.mjs     # 三道闸门：数据契约 / 索引同步 / 数据库往返
```

- 全绿才提交；`pre-commit` 会自动拦。
- 确需跳过（例如只改文档而环境没装 Python）：`git commit --no-verify`，并在提交信息里说明原因。
- 换机器后先跑 `node scripts/install-hooks.mjs` 装钩子。

## 4. 命名与结构

| 类型 | 规则 | 例 |
|---|---|---|
| 作品 key | 与作品题名一致，中文原样 | `琵琶行`、`春望` |
| 人物 key | 拼音，无空格 | `baijuyi`、`dufu` |
| CBDB 人物 | `p<cbdb_id>` | `p24146`（陈寿） |
| 未知作者 | `au<序号>` / `anonymous` | `au001` |
| 字段名 | JSON 用 lowerCamel；数据库用 snake_case | `traditionalDerived` / `traditional_derived` |
| 提交信息 | `type(scope): 中文摘要` | `feat(api): 索引接口加 60 秒缓存` |

## 5. 后端约定

- **校验在模型层**：`Apparatus.save()` 要求 `basis`、`Commentary.save()` 要求三要素、`Stop.save()` 要求 `source`。
- **禁止 N+1**：列表页必须 `annotate(Count(...))`，不许在循环里 `.count()`。
- **热路径加缓存**：`/api/index`、`/api/search` 带 TTL 缓存并回写 `X-Cache` 头。
- **远程数据库视为慢链路**：本地 SQLite、线上 PG 同机；跨公网查询只在开发时接受。
- **错误不回显内部细节**：DRF 默认行为即可，不要 `str(e)` 直出。
- **凭据只走环境变量**：`.env` 已 gitignore；代码与文档里不得出现真实口令。

## 6. 前端约定

- 保持零构建：单个 `index.html` + 原生 JS，不引入打包器。
- 数据优先读 `/api/*`；**接口不可达时必须能退回静态 `data/*.json`**（渐进增强）。
- 新增页面必须可深链：`#/work/<key>`、`#/person/<key>`、`#/journey/<key>`。
- 中文标点与排版遵循既有风格；不引入外部字体 CDN。

## 7. 给 AI 代理的额外约定

1. **先读后写**：先看 `docs/`、`schema/`，再动文件。
2. **小步提交**：一次一件事，提交信息说清「改了什么、为什么」。
3. **不擅自扩大范围**：不顺手重构无关模块，不引入新框架/新语言。
4. **删除前查引用**：确认 0 引用再删；有引用就报告并等待确认。
5. **不确定就停**：涉及契约、部署、删除、外部服务时，先问。
6. **报告差异**：改完给出「改了什么 / 验证结果 / 剩余风险」三段。
7. **不编造**：缺数据就说缺，不生成看起来合理的假数据。

## 8. 禁区

- 不提交 `db.sqlite3`、`.venv/`、`staticfiles/`、`node_modules/`
- 不把真实口令写进 `README`、脚本、提交信息
- 不手工编辑 `data/index.json`
- 不在 `commentary` 里放没有出处的评语
- 不在 `data/works/*.json` 里省略 `appreciation.by` / `license`

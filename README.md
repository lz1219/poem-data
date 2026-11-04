# 江山行止 · 文献与数据

让古籍读得懂，让解释查得到依据，让人物与作品回到历史时空中。

面向公共阅读、教学研读与专业考据的中文古籍平台；三种用途共享文献、版本、证据与修订，按需深入。本文献站与[地图站](https://github.com/lz1219/jiangshan-xingzhi)互通。

定位与长期取舍见[项目总纲](docs/project-charter.md)，内容准入与审校见[编纂规范](docs/editorial-policy.md)，AI批量译注、段落阅读与卷一试点见[AI阅读细则](docs/ai-reading-policy.md)。这些规范是建设目标，实际完成情况见[资料状态](docs/data-status.md)和项目看板。

典籍库存、实际取得版本及尚缺材料见[典籍台账](docs/book-register.md)；完整原件与数据快照的入库、整理、验证见[操作说明](docs/data-ingestion.md)。隔离研究区不自动成为公开核定正文。

## 这是什么

本仓库包含文献站、数据源与研究工作台。原始语料、经过编纂的作品和候选研究记录分开管理：

| 目录 | 内容 |
|---|---|
| web/ | 前端单页（零构建） |
| server/ | Django 后端：admin 录入 + 只读 API |
| docs/ | 项目定位、编纂规范、结构与 AI 编码规范 |
| data/works/ | 一件作品一个文件：正文、大意、注释、背景、赏析、校记、系年 |
| `data/persons/` | 人物：生卒、字号、别名、CBDB/Wikidata ID |
| `data/journeys/` | 行迹：站点、年代、经纬度、出处、站间承接语 |
| `data/comments/` | 历代评点（仅有评点的作品才建文件） |
| `shared/` | 版本表、书目、地名 |
| `schema/` | JSON Schema |

## 三条硬规则

1. **一切叙述必须有据。** 每段叙述都带 `source`；缺出处即校验失败。
2. **繁简不混。** `text.paragraphs` 是繁体原文，`paragraphsSimplified` 是简体。
   若繁体是由简体反推的（无底本可依），必须标 `traditionalDerived: true`。
3. **评点与赏析分栏。** 评点是古人说的（须有评者·朝代·原文·卷页），
   赏析是本站自撰（`by: 本站自撰`）。**不允许把 AI 生成的话放进评点栏。**

## 生成站点的数据文件

`js/atlas_works.js` / `atlas_overlay.js` / `atlas_journeys.js`
在 [江山行止](https://github.com/lz1219/jiangshan-xingzhi) 仓库里是**生成物**：

```bash
node scripts/emit-atlas.mjs --target ../jiangshan-xingzhi          # 生成
node scripts/emit-atlas.mjs --target ../jiangshan-xingzhi --check  # 只比对
```

规则：
- **本仓库的 `data/*.json` 是唯一真相**，站点文件不手改
- 上游已有站点在 overlay 运行时修订，保留上游文件；同键多站拒绝歧义覆盖；未知年份独立展示
- 提交闸门会跑 `--check`，生成物与数据不一致就拒绝提交

## 两种部署

| 形态 | 在哪 | 能力 |
|---|---|---|
| **完整版**（同源） | 自有服务器 `:8081`：Django 同时托管前端、API，以及 `/atlas/` 下的江山行止 | 作品 / 人物 / 行迹 / 作者 / 典籍 / 仕历 / 全文检索 / 地图 |
| **静态版** | GitHub Pages | 作品 / 人物 / 行迹（语料库功能隐藏，顶部给出完整版入口） |

```bash
node scripts/build-static.mjs --full-site http://47.94.110.181:8081/   # 产出 dist/
```

静态版由 `.github/workflows/pages.yml` 在推送 main 时自动构建发布。

## 校验与提交闸门

```bash
node scripts/check.mjs        # 数据 / 索引 / 地图生成物 / 研究记录 / 数据库往返
node scripts/install-hooks.mjs  # 装 pre-commit，自动拦不合格提交
```

前端零构建，Node 脚本无 npm 依赖；研究发布检查使用 Python 标准库。检查：字段与枚举、繁简段数一致、校记有无依据、评点是否已核原文、
系年是否唯一且与 `composed.year` 一致、行迹站序是否连续、作者是否有对应人物。

## 现状

| 项 | 数量 |
|---|---|
| 作品 | 69 |
| 人物 | 35 |
| 行迹 | 20 |
| 繁体取自电子来源、非反推 | 20（原典版本仍需核对） |
| 繁体为反推 | 49（已标注，待核底本） |

## 许可

本站自撰内容按 **CC BY-SA 4.0** 发布；第三方原典、影像与数据保留其来源和使用条件，不以本站总署名替代来源核验。地图代码继承上游 GPL-3.0，与内容责任和来源标识分别管理。

转载或再分发请保留署名与出处字段。

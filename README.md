# 江山行止 · 数据

中国古典诗文的结构化数据：作品、人物、行迹、校记、评点。
配合 [江山行止](https://github.com/lz1219/jiangshan-xingzhi) 使用，也可单独消费。

## 这是什么

不是语料库，是**带考据结构**的策展数据：

| 目录 | 内容 |
|---|---|
| web/ | 前端单页（零构建） |
| server/ | Django 后端：admin 录入 + 只读 API |
| docs/ | 结构与 AI 编码规范 |
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
- 上游已有的行迹只**补缺站**（按「年 + 古地名」去重），不覆盖上游
- 提交闸门会跑 `--check`，生成物与数据不一致就拒绝提交

## 两种部署

| 形态 | 在哪 | 能力 |
|---|---|---|
| **完整版**（同源） | 自有服务器 `:8081`，Django 同时托管前端与 API | 作品 / 人物 / 行迹 / 作者 / 典籍 / 仕历 / 全文检索 |
| **静态版** | GitHub Pages | 作品 / 人物 / 行迹（语料库功能隐藏，顶部给出完整版入口） |

```bash
node scripts/build-static.mjs --full-site http://47.94.110.181:8081/   # 产出 dist/
```

静态版由 `.github/workflows/pages.yml` 在推送 main 时自动构建发布。

## 校验与提交闸门

```bash
node scripts/check.mjs        # 三道：数据契约 / 索引同步 / 数据库往返
node scripts/install-hooks.mjs  # 装 pre-commit，自动拦不合格提交
```

零依赖。检查：字段与枚举、繁简段数一致、校记有无依据、评点是否已核原文、
系年是否唯一且与 `composed.year` 一致、行迹站序是否连续、作者是否有对应人物。

## 现状

| 项 | 数量 |
|---|---|
| 作品 | 69 |
| 人物 | 27 |
| 行迹 | 10 |
| 繁体取自底本 | 18 |
| 繁体为反推 | 51（已标注） |

## 许可

数据：**CC BY-SA 4.0**
（与代码仓库的 GPL-3.0 分开：代码继承自上游，数据是本项目自撰。）

转载或再分发请保留署名与出处字段。

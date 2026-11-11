# 接手指南（给新的协作者或 AI）

> 读完这一页，你应该能：跑起来、改数据、跑闸门、不踩已知的坑。
> 细节在各专题文档里，这里只给"怎么动手"。

> 最新交接与统一文献库任务见 [智能体接手说明](agent-handoff-20261111.md)；其中记录了数据库优先的新要求及尚未切换的旧契约。

## 一、两个仓库

| 仓库 | 是什么 | 技术 |
|---|---|---|
| **poem-data** | 文献站 + 数据源（唯一真相） | Django 6.1 + DRF，零构建前端（`web/index.html`） |
| **jiangshan-xingzhi** | 江山行止（地图站，江山时序的 GPL 分支） | 纯静态，classic script，无打包器 |

**关系**：poem-data 的 `data/*.json` 是唯一真相 → `scripts/emit-atlas.mjs` 生成地图站的
`js/atlas_works.js`、`js/atlas_overlay.js`、`js/atlas_journeys.js`。

> 数据整理以服务器现有 PostgreSQL 为准，不再维护本地 SQLite。测试须使用隔离环境；JSON 仍按现有发布流程维护。详见 [数据库工作位置](corpus-operations.md#数据库工作位置)。

## 二、跑起来（本地）

```bash
# 文献站（Django，端口 5322）
cd poem-data/server
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
cd .. && cd data   # 确认 data/ 在仓库根
set DATA_DIR=<repo>/data
set PUBLIC_DIR=<repo>
cd ../server && .venv/Scripts/python manage.py runserver 127.0.0.1:5322

# 地图站（纯静态，端口 5199）
cd jiangshan-xingzhi && node scripts/_serve.cjs
```

**语料库**（可选）：`CORPUS_DSN=postgresql://<user>:<pwd>@<host>:5432/jiangshan`。
不配也能跑，只是语料相关接口返回 503。

## 三、数据长什么样

```
poem-data/data/
  works/*.json     69 篇：正文（繁/简）、大意、注释、背景、赏析、系年、校记
  persons/*.json   35 位：生卒、字号、别名、CBDB id、journeyKey
  journeys/*.json  20 条：导语 + 站点（年/地/事/出处）+ 站间承接语
  index.json       自动生成，勿手改
```

**契约（不可妥协）**：

1. 一切叙述必须有 `source`；缺 source 会被 `_validate_data.cjs` 判错误。
2. 原文逐字取自基线，不手抄；繁简必须成对。
3. 赏析只收本站自撰（CC BY-SA）；结合史事的推断放 `inference` 并给 `basis`。
4. 文 / 史传标「摘录」（`excerpt: true`）。
5. 不给原文代加标点——标点是校勘成果；只标状态，用**别人标好的版本**。

## 四、改名与闸门

```bash
cd poem-data
node scripts/check.mjs          # 四道闸门：data / index / atlas / db

cd ../jiangshan-xingzhi
node scripts/_validate_data.cjs # 出处 / 枚举 / 推测依据 / 读本序号
node scripts/check-docs.mjs     # 文档体检
node scripts/sync_version.js    # 改过 js/ 必跑，重算 ?v= 缓存戳
```

**发布纪律**：`git push` 等于发布（触发 CI + Pages）。
本地可以随便 commit，**推送前必须与项目持有人确认**（pre-push 钩子会拦）。

## 五、常用管理命令（poem-data/server）

| 命令 | 用途 |
|---|---|
| `manage.py import_json` / `export_json` | JSON ↔ 数据库；`--check` 验证往返无损 |
| `manage.py import_wikisource --page 舊唐書 --book 舊唐書` | 从维基文库导标点本（按卷） |
| `manage.py crosscheck_career` | 行迹 ↔ CBDB 仕历交叉校验 |
| `manage.py check_places` | 站点 ↔ 地名库核对 |
| `manage.py discover_variants` | 用语料找异文候选 |
| `manage.py backfill_punctuated` | 回填 `text_unit.punctuated` |

## 六、已知的坑（都踩过）

| 坑 | 现象 | 正确做法 |
|---|---|---|
| **繁简没归一** | 搜「出师表」搜不到《出師表》 | 用 `title_simp` / `author_simplified` / `c_name_simp` 列比对 |
| **同名地名** | 「江州」匹配到重庆、「和州」匹配到河北南和 | 结合人物与年代判定，不能取第一条 |
| **CBDB 有年无地** | 韦庄 9 段任职零地点 | 改走 C 路径（史料 + 诗题），不要硬凑 |
| **CBDB 伪年份** | `-1` / `0` 显示成公元前 | 一律 `CASE WHEN > 0` |
| **生年 0** | 渲染成「前0」 | 数据里用 `null`，显示层兜底 |
| **容器绑定目录** | 换目录后容器仍读旧内容 | 原地解包 + `docker restart` |
| **PowerShell 改全角空格** | 正则里的 U+3000 被改写，切分失败 | 用行首字符判定，别在命令行里拼正则 |
| **Django 字段名** | Person 是 `born` / `died`，不是 `birth_year` | 看 `corpus/models.py` |

## 七、当前进度与缺口

见 `docs/data-status.md`（覆盖率、标点来源、受源限制项）与
`docs/journey-plan.md`（行迹人物清单、CBDB 覆盖分析、分批计划）。

**关键数字**（2026-11）：作品 69 / 人物 35 / 行迹 20 / 站点 201；原典标点覆盖 63.7%
（四部史书标点本已入，清史稿仍有 49 卷无标点）。

**已知未完成**：历代评点 0 条（缺权威源）、49 篇繁体为反推、李商隐等需 C 路径。

## 八、凭据

**不在仓库里。** 数据库口令、服务器登录、后台管理员账号请向项目持有人索取，
不要写进任何提交、文档或聊天记录。

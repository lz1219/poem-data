# 统一文献库模型规格与苏轼样板实施方案

更新日期：2026-11-11。本规格响应项目持有人 2026-11-11 指示，落实统一文献库“作品”与“典籍”单一入口设计，以线上 PostgreSQL 为数据依据，优先复用现有宋词唐诗语料，建立跨版本统一身份与端到端样板。

---

## 一、核心原则与设计目标

1. **单一文献入口**：
   - 读者使用一个文献入口，按作品、人物、典籍目录等多种方式浏览。
   - 彻底打破“精选作品（69篇）”与“全文语料（8.8万首/2300卷）”的隔阂，精选篇目展示深度译注与赏析，语料库篇目展示可靠底本并可渐进补充研读。
2. **正文真相归于见证（Witness），作品拥有统一身份（Canonical Identity）**：
   - 一篇作品（Work）确立唯一稳定标识（如 `sushi-shuidiaogetou`），聚合题名、词牌、别名、体裁与作者。
   - 作品正文不采用硬编码孤立文本，而是挂载一个或多个**文本见证（Witness）**，每个见证指向具体底本（如宋词语料 ID 112216、传习录卷一等），记录原文本、SHA-256、摘录范围与异文说明。
3. **行迹关联独立解耦**：
   - 行迹站点引用（Stop Reference）是外部关系，不能因为作品未被行迹引用就拒绝建立作品身份，也不能为入库而虚构站点引用。
4. **学术规范与 AI 审校透明**：
   - 忠实译文、定位注释与自撰赏析明确记录来源（`provenance`）与审校状态（`review_status: unreviewed / verified`）。AI 生成内容显著标示，不得冒充古籍或定论。
5. **零构建与数据库驱动**：
   - 保持前端零构建、无 npm 运行时依赖；以线上 PostgreSQL 为数据依据，通过数据库导出驱动地图生成器。

---

## 二、统一实体模型契约

### 1. 统一作品实体（Work）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `work_key` | string | 是 | 全局稳定逻辑键（如 `sushi-shuidiaogetou` 或现有 `水调歌头`） |
| `title_zh` | string | 是 | 标准题名（如《水调歌头·明月几时有》） |
| `title_en` | string | 否 | 英文题名 |
| `aliases` | list[string] | 否 | 别名与词牌异称（如 `["水调歌头", "明月几时有"]`） |
| `genre` | string | 是 | 体裁枚举：`shi` / `ci` / `fu` / `wen` / `history` / `qu` |
| `author_key` | string | 是 | 作者标识，关联统一人物（如 `sushi`） |
| `composed` | object | 否 | 系年与地名（年代、年代性质、地点名、证据依据；待核须明确标示） |
| `level` | string | 是 | `popular`（通俗） / `academic`（学术有校记/考辨） |

### 2. 文本见证实体（WorkWitness）

一个作品可以拥有 1 个主见证（Primary Witness）和 0~N 个对比见证。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `witness_key` | string | 是 | 见证标识（如 `witness-ci-song-112216`） |
| `work_key` | string | 是 | 外键关联作品 |
| `edition_name` | string | 是 | 版本或底本名称（如《全宋词》中华书局本、维基文库标点本） |
| `is_primary` | boolean | 是 | 是否为默认展示的主见证（默认 true） |
| `corpus_target` | object | 否 | 关联语料库物理实体（`type: "poem" | "text_unit" | "paragraph"`, `id: integer`） |
| `source_url` | string | 否 | 上游固定提交 URL / 文件指针（如 GitHub commit 路径） |
| `source_pointer` | string | 否 | JSON Pointer（如 `/459`）或页码/行号 |
| `is_excerpt` | boolean | 是 | 是否为摘录（true 则必须说明摘录范围） |
| `excerpt_range` | object | 否 | 摘录具体范围：起始/结束行、省略内容说明（如杜甫诗中间省略四句） |
| `variant_notes` | string | 否 | 版本异文说明（如《卜算子》末句异文及考证引文） |
| `text_paragraphs` | list[string] | 是 | 繁体正文行列表 |
| `text_paragraphs_simp` | list[string] | 否 | 简体正文行列表（与繁体严格对应） |
| `text_sha256` | string | 是 | 正文字符串 SHA-256（防静默漂移） |

### 3. 研读与译注实体（WorkReading）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `work_key` | string | 是 | 关联作品 |
| `meaning` | string | 否 | 篇章总体大意 |
| `paragraphs_reading` | list[object] | 否 | 逐段研读：包含段落序号、忠实译文、定位词注（term + explain） |
| `background` | string | 否 | 写作历史背景（必须有史料出处） |
| `appreciation` | object | 否 | 赏析正文、分节结构、推测与依据（inference + basis） |
| `provenance` | string | 是 | 生成方式：`original`（本站自撰） / `ai_generated`（AI起草） |
| `review_status` | string | 是 | `unreviewed`（AI未审） / `verified`（已人工审校） |
| `license` | string | 是 | 版权许可（默认 `CC BY-SA 4.0`） |

### 4. 行迹引用实体（WorkStopLink）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `work_key` | string | 是 | 关联作品 |
| `journey_key` | string | 是 | 行迹人物标识（如 `sushi`） |
| `stop_seq` | integer | 是 | 站点序号（如第 5 站密州） |
| `relation` | string | 是 | 关系类型：`stop-quotes-work`（站点引文） / `composed_at`（在此创作） / `mentioned`（提及） |
| `matching_text` | list[string] | 否 | 站点引文与作品重合的词句片段 |
| `basis` | string | 是 | 关联依据与限制说明（明确不代表在此亲历或唯一作年） |

---

## 三、苏轼五篇样板数据映射表

| 作品与键 | 关联语料库底本 | 见证特征与异文 | 行迹站点关联 | 研读与审校状态 |
|---|---|---|---|---|
| **《水调歌头》**<br>`sushi-shuidiaogetou` | 宋词 `corpus_poem` ID 112216<br>(`ci.song.1000.json` /459)<br>SHA: `ab4122ab...` | 语料无小序；两份电子文本标点分行对照；全篇收录 | 密州站（seq 5）<br>引用：“人有悲欢离合…”<br>关系：`stop-quotes-work` | 自撰大意、注释5条、背景、赏析齐备；系年1076密州有据 |
| **《定风波》**<br>`sushi-dingfengbo` | 宋词 `corpus_poem` ID 112266<br>(`ci.song.1000.json` /509) | 异文说明：语料作“回首向来潇洒处”，精选底本作“萧瑟处”，保留双通说明 | 黄州站（seq 8）<br>引用：“竹杖芒鞋轻胜马…”<br>关系：`stop-quotes-work` | 自撰大意、注释、赏析齐备；系年1082黄州 |
| **《念奴娇》**<br>`sushi-niannujiao` | 宋词 `corpus_poem` 对应候选<br>首句“大江东去”精确命中 | 全篇对照；版本分行统一 | 黄州站（seq 7 湖州 / seq 8 黄州赤壁）<br>赤壁怀古相关作品 | 自撰译注与赏析已入库 |
| **《望江南》**<br>`sushi-wangjiangnan` | 宋词 `corpus_poem` ID 112310 | 题名别称：“望江南・忆江南”；正文前12字匹配 | **无直接行迹引文**<br>（独立作品身份，不虚构站点引用） | 密州超然台作；自撰研读保留 |
| **《卜算子》**<br>`sushi-busuanzi` | 宋词 `corpus_poem` ID 112312<br>SHA: `5f79a2d9...` | **版本异文**：语料末句“枫落吴江冷”，精选作“寂寞沙洲冷”。标引林玫仪《明郎瑛词话辑校》第148页，保留学术异文线索 | **无直接行迹引文**<br>（黄州定惠院作） | 异文详细考证注释已附，正文未篡改 |

---

## 四、实施与演进步骤

1. **结构准备**：在 `data/links/` 与统一模型检验器中支持完整的 `WorkWitness` 与 `WorkStopLink` 映射，确保已有两首苏轼候选无缝升级。
2. **两库过渡策略**：
   - 保持线上 `jiangshan_web` 与 `jiangshan` 稳定运行；
   - 采用只读联合查询（View / 组合 API）实现作品与语料文本见证的关联，暂不强制在生产库进行破坏性表结构重组。
3. **前端入口贯通**：
   - 改造 `web/index.html`：作品列表支持展示来自统一模型的见证与语料关联，读者点击苏轼即可同时看到精选名篇与全量词作；
   - 作品详情页展示主见证，可切换对比见证与版本异文。

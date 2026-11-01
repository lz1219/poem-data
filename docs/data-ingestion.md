# 完整资料的入库、整理与验证

本批处理27个 Kanripo 原典仓库的29个固定版本快照，以及现有作品、人物、行迹、站点和研究历史。其中21个仓库为本批新增，两个补充分支与master同来源链，不计独立佐证。服务于[项目总纲](project-charter.md)确定的公共阅读、文学历史研读和专业考据三种用途。研究原件共用一套出处基础，不因入库或机器验证而成为核定事实。

## 存放与隔离

现有语料库的 `research_ingest` 区保存完整 ZIP、包内全部文件、来源目录及 JSON 原态。字节按 SHA-256 寻址，仓库提交入库工具与汇总报告；完整原件和内部研究正文不进入公开生成物。公开阅读接口仍使用原来的 `public` 表和经审查 JSON。

`source_snapshot` 固定仓库、提交号、包哈希与采集记录；`edition` 保留原文件底本标记；`unit` 保存卷目原值与分类；`page` 保存原页标记和原文件字节范围，包含卷首元数据，不能当作自然段或图像页已经人工核对。SBCK的数字`JUAN`可能是重排编号，仅保留为`juanHeader`；原书卷号候选取自`FILE`或明确卷题，另存`fileLabel`和卷首行。不能确定类别的单元保留`unclassified`，待人工核定。

`record_snapshot` 保存现有数据及每一研究修订；`record_link` 建立作者、人物、所属行迹和研究对象关系；`quote_match` 把已有摘引定位到原文件字节。历史 AI 参与、待核状态、反证和内部可见性均保留在快照中。报告仅公开汇总数。

## 操作顺序

使用项目现有 Python 环境及 psycopg，不安装新依赖。凭据通过本地文件或 `CORPUS_DSN` 传入，不能提交到仓库。

先依 `data/book-acquisition-plan.json` 执行 `scripts/acquire-books.py`，按书保存固定提交与原包，可续传，受阻入口保留记录并换源；以后确认条件变化时可显式加 `--retry-blocked`，每入口仍最多两次。`scripts/organize-books.py --credentials <本地文件>` 核对既有卷篇和诗歌库的书目归属，生成 `data/book-register.json`；其中采集状态为制作台账当时的快照，最终入库阶段以 `data/ingestion-report.json` 为准。恢复的三类目录保留 GitHub API 原始响应、固定目录提交和 Git blob 标识，不覆盖以前的失败记录。

```text
server/.venv/Scripts/python scripts/raw_ingest.py land
server/.venv/Scripts/python scripts/raw_ingest.py land --credentials <本地文件> --apply
server/.venv/Scripts/python scripts/raw_ingest.py organize --credentials <本地文件> --apply
server/.venv/Scripts/python scripts/raw_ingest.py verify --credentials <本地文件> --apply --repeat
```

`land` 默认预览；`organize`、`verify` 不带 `--apply` 时只读。验收时加 `--repeat` 实际重放本批落库与整理并核对所有研究区表行数不增加，随后全量回读；这会写检查点，须同时 `--apply`。首次入库后以 `data/ingestion-current.json` 指定批次，也可显式传 `--batch`。输入改变应另建批次，禁止用旧批次验证新输入。原始缓存默认在仓库外 `.local/research-cache`；需迁移时用 `--cache` 指定同一完整缓存。

每次写入前，在仓库外 `.local/backups` 保存批次和公开表指纹检查点。完整输入已另存固定哈希缓存；这类检查点不是整库恢复备份。工具仅追加隔离区数据和更新批次处理状态，不清空表，不覆盖公开正文。失败写事务整体回滚；重复执行使用相同内容身份，冲突内容由全量验证拦截。原始数据不可用本工具覆盖修正，应建立新快照。

## 验证边界

验证回读全部原件，与本机固定清单逐字节比较，同时检查包内文件路径、JSON 快照、全部原页范围、结构关联和引文位置。公开语料的 12 张表同时核对行数与行内容指纹。损坏的引文、来源文件或对象关系阻止验证成功；非支持类型的定位明确记录为未定位，不静默跳过。大原件按字节分片读回，写入按负载分组，保留单一原子事务。快照身份包含完整来源元数据，旧来源不被新修订覆盖。

`integrityPassed` 仅证明本批存储和整理满足上述检查；`academicReview` 仍为 `pending`。反推繁体、纯年份系年占位、站点事实及卷目歧义均单独保留。1,968个文件单元含55个同源分支单元，不等于1,968卷，也不证明27个仓库所题原典没有缺卷；16条版本见证及其引用修订只证明对应片段存在，不证明全文已校。

原有38条书目中，9条有卷篇，2条仅有诗歌库记录，27条目前只是出处占位。另有同书异名、版本并列和现代栏目名混作书名的候选关系，已列入书目台账，未擅自合并。《文忠集》入口受阻；另一个目录题为《欧阳文粹》的仓库，实际SBCK文件题作《欧阳文忠公集》并有重排组件，不能据目录名称断言选本或全集。《三国志》的master、WYG均只检出《魏志》卷首，蜀、吴两部分仍缺。王阳明文件的重排编号与原卷号也已分别记录。地方志按具体站点争议选书，独立年谱版本、其他史书版本或影像继续留缺口，不能因取得某一仓库而自动销项。

机器汇总见 `data/ingestion-report.json`；来源权限和底本、篇题、上下文的人工作业继续按来源台账与研究记录推进。当前无新增公开正文、译文或已核事实。

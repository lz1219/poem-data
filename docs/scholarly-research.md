# 学术资料与 AI 推测

项目长期定位见 [项目总纲](project-charter.md)，原文、译注、赏析与AI的共同质量标准见 [编纂规范](editorial-policy.md)。本文记录现有研究基础能力及其限制。

本批由用户明确授权，执行规格见兄弟仓库 docs/specs/0002-scholarly-research/。来源优先、公开来源广泛调查但不死磕。研究资料在数据库工作台核查，审查后的 JSON 是发布唯一真相；不允许后台修改和文件修改互相静默覆盖。

## 数据约定

- `shared/sources.json`：提供者、底本、访问与使用条件、上游来源链；GitHub 固定提交，维基固定修订；未知许可不自动允许再分发。
- `data/research/*.json`：独立记录，稳定 id、revision、subject、status、provenance、evidence、reasoning、counterEvidence、alternatives、reviewHistory。状态为 pending / partial / verified / restricted / rejected；verified 表示完成指定核验，不自动证明论断正确。
- `data/research-history/<id>/<revision>.json`：不可变快照；引用包含 id、revision、卷篇/页、正文哈希。旧版本仍可访问。
- `data/research-index.json`：脚本生成，不手改；作品、人物、行迹、站点均有结构与证据缺口记录。

AI 记录公开条件：原文引文可在保存的来源中定位、有真实 sourceId 与版本哈希、模型/版本/生成时间齐备、有推理及反证检索说明。页面固定显示「AI推测·未经人工审校」或「AI推测·已人工审校」，审校人和历史保留。无据线索只能内部保存；拒绝记录退出默认列表。旧记录不得补造模型或人工署名。

## 实施与复现

调查/库存/核查命令与结果见 `docs/source-survey.md` 和 `docs/data-status.md`。外部原始响应放仓库外缓存，公开仅发布已确认可分发的摘引与元数据。推测绝不进入事实索引、默认年表或地图路线。

## 限制

结构审查、机器引文命中和人工学术审校分别记录，不能互相替代。来源暂不可达和无法确定权限均需留档，不能靠生成文本填空。

## 本批结果与限制

- 来源入口15类，固定目录8份（另1份受阻）；6部原典固定提交，262个文本文件仅保存在外部研究缓存。目录与文件数对照见 data/edition-coverage.json，不把卷首/附录计成正文卷。
- 对象结构与缺口初审325条；版本见证16条，均为机器定位候选，尚未人工核定；公开AI文本解释1条。内部历史推测11条仅存私有工作台。
- 49篇反推繁体错误归入全唐诗电子本的问题已修正；原文未改，反推标识未取消。69条纯年份系年依据改为pending，原年份保留。
- 原文、版本、系年与行迹仍需逐条核原书，不宣称整个库已经达到学术确证。模型精确快照未由会话环境公开，AI记录明确保留该复现限制。

### 命令

```text
python scripts/research.py survey
server/.venv/Scripts/python scripts/research.py inventory --credentials <本地凭据文件>
python scripts/collect-witnesses.py
python scripts/research.py audit
server/.venv/Scripts/python scripts/import-research-notes.py --credentials <本地凭据文件>
server/.venv/Scripts/python scripts/import-research-notes.py --credentials <本地凭据文件> --apply
node scripts/check.mjs
node scripts/test-contracts.mjs
server/.venv/Scripts/python server/manage.py test corpus
```

语料库追加只进入 research_note，默认只读预检；--apply 写前备份、同修订幂等，冲突回滚。事务备份与本批新增ID在仓库外backups目录，可按topic/内容逐条核对后撤销本批新增行。旧事实和原文表不修改。业务库增加研究来源、原件及不可变修订模型；线上应用迁移须随发布批次执行。

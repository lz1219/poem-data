# 《资治通鉴》卷一校改记事译注

2026-11-05，依据卷一版本16和维基文库固定修订2489405，追加15个来源块的 AI 未审译文和15条注释；主要处理短记事中的方括号校改、括号异读及卷首纪年名称。楚声王条所据电子本的“疑”在译文中保留，不因翻译确定其人。注释仅解释所据电子本标记和本译取字，不代替来源编者校记，不裁决异文。候选文件为 `data/paragraph-explanations/zztj-volume001-variants-candidates.json`。

正式入库前已备份15个目标与原卷，服务器文件 `/opt/corpus-data-jobs/paragraph-explanations-variants-20261105/before.json.gz`，SHA-256 `bf84b7f5f0c7b64381e06458ab3fd8d3b3ea67b0f168f180ba318018c0271e7e`；宿主读回、回滚演练及无残留检查通过。正式写入后独立核对原句、原文哈希、版本和15个注释锚点；重复导入不增加记录。生产网页在1200px和390px抽验疑读提示与待补状态通过。

随后追加6个较长议论与记事来源块，4条注释，包含魏武侯与吴起论山河之险及太史公议论；均为 AI 未审内容。候选见 `data/paragraph-explanations/zztj-volume001-narratives-candidates.json`。备份 `/opt/corpus-data-jobs/paragraph-explanations-narratives-20261105/before.json.gz`，SHA-256 `4f2935020deaea5cab60ca367bc9d9fc23fe0c81310999aee1617b9cd31b8efc`；宿主读回、回滚演练、无残留、重复导入、独立原句及锚点核验通过，桌面和手机抽验吴起议论译文通过。

卷一91个来源正文块中74块已有 AI 未审译注、17块待补；这不是人工确认的自然段分母，也不代表语义准确或学术审校完成。剩余包括长篇议论、复杂叙事和待辨校改，需逐项处理。AI标识与原有来源校记保持独立。

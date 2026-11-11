# 《资治通鉴》卷一来源块译文覆盖

2026-11-05，依据卷一版本 16 和维基文库固定修订 2489405，补入三家分晋议论、智赵继承、秦献公即位以及魏文侯事迹共 4 个来源正文块的 AI 未审译文和 13 条注释，候选分别见 `data/paragraph-explanations/zztj-volume001-order-candidates.json` 与 `data/paragraph-explanations/zztj-volume001-weihou-candidates.json`。对“沉之渊旁”保留字面翻译及待核提示；异文依据和语义均待审校。

两批分别备份目标段落及卷记录，服务器路径及 SHA-256：

- `/opt/corpus-data-jobs/paragraph-explanations-order-20261105/before.json.gz`：`351e4b9c1d257ecf8086916369fc5cb9099b9081153fdff6b9d15c11061f2896`。
- `/opt/corpus-data-jobs/paragraph-explanations-weihou-20261105/before.json.gz`：`12092cd58a1409fa4f6295e6dfa10ed611c5cc04e53381930a74b65522d0ba78`。

备份回读、事务回滚演练、无残留检查、正式入库独立回读及重复导入均通过。对照固定库存逐条核验后，91 个来源正文块均有 AI 未审译文，注释共 91 条，人工审校 0；原文哈希、注释锚点和 AI 标识通过程序检查。来源块并非人工核定的自然段，内容准确性、译注充分性、重点赏析、异文及跨段阅读仍待核查和完善。

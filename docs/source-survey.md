# 来源调查

调查时间：2026-11-01T04:30:16.744741+00:00。原始响应缓存在仓库外；每入口最多两次请求。

| 来源 | 类型 | 入口状态 | 下载/入库/分发 |
|---|---|---|---|
| [Kanripo 汉籍](https://github.com/kanripo/KR-Catalog) | github | reachable | 待具体资源核实 |
| [chinese-poetry](https://github.com/chinese-poetry/chinese-poetry) | github | reachable | 待具体资源核实 |
| [CBDB](https://github.com/cbdb-project/cbdb_sqlite) | github | reachable | 待具体资源核实 |
| [维基文库](https://zh.wikisource.org/w/api.php?action=query&meta=siteinfo&format=json) | text | reachable | 待具体资源核实 |
| [中国哲学书电子化计划](https://ctext.org/tools/api) | text | reachable | 待具体资源核实 |
| [识典古籍](https://www.shidianguji.com/) | text | reachable | 待具体资源核实 |
| [中研院汉籍](https://hanchi.ihp.sinica.edu.tw/) | text | reachable | 待具体资源核实 |
| [国家图书馆](https://www.nlc.cn/) | catalog-image | reachable | 待具体资源核实 |
| [台北国家图书馆](https://rbook.ncl.edu.tw/NCLSearch/Search) | catalog-image | unavailable | 待具体资源核实 |
| [哈佛燕京图书馆](https://library.harvard.edu/collections/chinese-collection) | catalog-image | unavailable | 待具体资源核实 |
| [京都大学汉籍目录](https://kanji.zinbun.kyoto-u.ac.jp/kanseki/) | catalog-image | unavailable | 待具体资源核实 |
| [东京大学东洋文化研究所](https://www.ioc.u-tokyo.ac.jp/kanseki/) | catalog-image | unavailable | 待具体资源核实 |
| [书格](https://www.shuge.org/) | catalog-image | reachable | 待具体资源核实 |
| [Wikidata](https://www.wikidata.org/wiki/Wikidata:Main_Page) | structured | reachable | 待具体资源核实 |
| [CHGIS](https://chgis.fas.harvard.edu/) | structured | unavailable | 待具体资源核实 |

## 调查边界

入口可达不等于已查到所需底本。已取得并固定8份 Kanripo 目录；正史类 KR2a 目录两次请求未成功，作为受阻项保留，其余包括传记、地理、别集、总集、诗文评及词曲目录；各条记录另列具体命中与未检索项。未取得可用文本的条目不得标为已核。

## 优先次序

反推繁体作品的底本 → 系年史料原句 → 行迹年地与人物身份 → 相关缺卷 → 独立版本校记与历代评点。

## 受阻与切换

unavailable 来源保留错误类型和测试日期；不绕过登录/访问控制。转查其他来源或影像；权限未知仅发布目录链接。付费、账号申请与人工查阅不阻塞公开来源批次。

## 本批固定版本采集

| 原典 | 固定版本文件（含卷首/附录） | 正文片段候选 |
|---|---|---|
| 李太白文集 / WYG | 31 | 6 |
| 九家集注杜詩 / WYG | 37 | 3 |
| 白氏文集 / SBCK | 73 | 2 |
| 東坡全集 / WYG | 116 | 3 |
| 東坡詞 / WYG | 2 | 1 |
| 竹山詞 / WYG | 3 | 1 |

原件保存在仓库外缓存；公开16条定位摘引。机器命中不等于篇题、底本、全文、系年均已核定；未取消任何反推繁体标记。目录对照见 data/edition-coverage.json。

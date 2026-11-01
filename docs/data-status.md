# 数据现状与核查缺口

生成时间：2026-11-01T04:33:57.709232+00:00。由 scripts/research.py audit 生成。

| 对象 | 已覆盖结构与缺口审查 |
|---|---|
| works | 69 |
| persons | 35 |
| journeys | 20 |
| stops | 201 |

所有记录均有核查状态、问题和下一步；结构初审不等于人工史实核定。

69条旧系年依据的年份占位仍需原句；反推繁体未经核对不取消标识。实际卷篇库存见 data/corpus-inventory.json；来源状态见 docs/source-survey.md。

## 复现

```text
python scripts/research.py survey --cache <仓库外缓存>
server/.venv/Scripts/python scripts/research.py inventory --credentials <本地凭据文件>
python scripts/research.py audit --cache <同一缓存>
```

## 首批补充

6部固定提交原典（262文件，外部缓存）；16条逐字定位版本见证候选；1条有据AI解释公开待审。49篇反推繁体仍待核。69条纯年份系年占位已退出采信状态，不能据此声称作年已确考。

11项Django回归、故障注入/地图回归、研究发布检查、数据库往返及浏览器动态/静态回退与手机布局已通过。公开修订与内部历史分开保存。

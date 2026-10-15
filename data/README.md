# 等级表数据声明 / Notice on the venue-tier data

## 是什么

本目录下的 `*.csv` 是 [ShowJCR](https://github.com/hitfyd/ShowJCR) 项目在提交
[`4687a8f6`](https://github.com/hitfyd/ShowJCR/tree/4687a8f608f20aaf004299992f5d347dba009361)
中整理发布的数据文件的**原样副本**(未做任何修改，可用 `scripts/fetch_data.py` 校验 sha256):

| 文件 | 内容 | 原始发布方 |
|---|---|---|
| `CCF2026-UTF8.csv` | 中国计算机学会推荐国际学术会议和期刊目录(2026) | 中国计算机学会(CCF) |
| `FQBJCR2025-UTF8.csv` | 中科院文献情报中心期刊分区表升级版(2025) | 中国科学院文献情报中心 |
| `JCR2025-UTF8.csv` | Journal Citation Reports 2025(分区、影响因子) | Clarivate |
| `XR2026-UTF8.csv`、`XR2026Conferences-UTF8.csv` | 新锐期刊/会议分区(2026) | 新锐分区表发布方 |
| `GJQKYJMD2025.csv` | 国际期刊预警名单(2025) | 中国科学院文献情报中心 |

## 条款

- 这些文件沿用 ShowJCR 仓库的许可(GPL-3.0),**不适用**本仓库代码的 MIT 许可。
- 排名、分区、影响因子等内容的权利归上表中的原始发布方所有。本仓库与这些机构没有任何关联，也未获其授权或认可。
- 附带这些文件只为方便学术研究中的文献标注，仅供参考;请勿用于商业用途，正式场合请以发布方的官方版本为准。
- 数据可能有遗漏或错误(例如会议名称匹配失败、分区年份滞后),本 skill 的标注结果不构成任何评价依据。
- **如果您是权利方并希望移除这些文件，请提交 issue 或联系仓库维护者，我们会立即删除。** 删除后 skill 仍可运行：用户可以运行 `scripts/fetch_data.py` 自行从 ShowJCR 获取。

## English summary

The `*.csv` files are unmodified copies of data files published by the ShowJCR project (commit `4687a8f6`). They remain
under ShowJCR's GPL-3.0 terms and are **not** covered by this repository's MIT license. Rankings, quartiles and impact
factors belong to their publishers (CCF, the National Science Library of CAS, Clarivate, …); this project is not
affiliated with or endorsed by them. Provided for academic reference only. Rights holders: open an issue and the files
will be removed promptly; the skill keeps working via `scripts/fetch_data.py`.

## 维护者：更新等级表

新年度数据发布后(由维护者操作，普通用户通过 `git pull` 获得):

1. 在 ShowJCR 找到新的提交 SHA 和文件名。
2. `python3 -I scripts/fetch_data.py --commit <SHA> --force`
3. 同步修改:`scripts/fetch_data.py` 的 `PINNED` 与 `SHA256`、`scripts/venues.py` 的 `TIER_FILES`(文件名常随年份变化;再确认 `load_tiers()` 用到的列名仍存在)、本文件和 `data/SOURCE.txt` 中的年份与提交号。
4. 用一小批论文跑 `venues.py` 核对结果，删除旧年份文件，提交并在 CHANGELOG 记一笔。

用户若在本地自行 `--force` 下载了别的版本，`git pull` 可能因工作区有改动而失败;用 `git checkout -- data/` 恢复即可。

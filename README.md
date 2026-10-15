# research-lineage

一个 [Claude Code](https://claude.com/claude-code) skill:把你收集的一批论文整理成**研究脉络**——谁在谁的基础上做、领域在追问哪些问题、问题如何被提出/回答/质疑/迁移、哪里还是空白，以及每篇论文发表在哪里、等级如何(CCF、中科院分区、JCR、新锐分区、预警名单)。最终生成一份叙述性报告和一个可离线打开的交互网页。

A Claude Code skill that turns a folder of papers into a research-lineage map: citation graph, question lineage, timeline, gaps, venue tiers, and a narrative report rendered as one self-contained interactive HTML page.

## 它做什么

| 步骤 | 由谁完成 | 产出 |
|---|---|---|
| 收集元数据与引用关系(arXiv、Semantic Scholar、OpenAlex) | 脚本 | `papers.json`(带缓存，增量更新) |
| 图分析：奠基论文、桥梁、前沿、传承链、方向间流动、可能遗漏的论文 | 脚本 | `graph.json`、`analysis.md` |
| 研究问题树：每篇论文提出什么问题、立场(提出/扩展/评测/质疑/重构/综述) | Claude 判断 + 脚本校验 | `questions.json`、`questions_digest.md` |
| 发表情况与等级标注;预印本转正式发表后自动更新 | 脚本 | `venues.csv`、`venues_stats.md`、`venue_changes.md` |
| 脉络报告 | Claude | `narrative.md` |
| 交互网页：报告、问题脉络、时间线、引文网络、发表情况(可缩放、可检索) | 脚本 | `lineage.html` |

脚本只用 Python 标准库，不需要 `pip install`。

## 安装

需要 git 和 Python 3.9+。

```bash
# 对所有项目可用(装到 ~/.claude/skills/research-lineage)
curl -fsSL https://raw.githubusercontent.com/wdsjxsg-spec/research-lineage/main/install.sh | bash

# 或者手动
git clone https://github.com/wdsjxsg-spec/research-lineage.git ~/.claude/skills/research-lineage
# 等级表已随仓库附带，无需另外下载
```

只想在某个项目里用：`bash install.sh --project /path/to/project`(装到该项目的 `.claude/skills/`)。

**更新:** `git -C ~/.claude/skills/research-lineage pull`,或重新运行 `install.sh`。你的自定义提示词在项目里，不受影响;新年度的等级表也随 `pull` 一起更新。

**可选环境变量:**
- `S2_API_KEY`:Semantic Scholar API key([免费申请](https://www.semanticscholar.org/product/api)),论文多时能明显减少限流。
- `OPENALEX_MAILTO`:你的邮箱，进入 OpenAlex 的礼貌队列;`OPENALEX_API_KEY` 同理。

## 使用

**还没有论文？** 直接告诉 Claude 主题和几篇你认可的代表论文(arXiv 号、DOI 或标题都行):

> 帮我建一个"RAG 幻觉评测"的论文集，代表作是 2309.01431,只要 2022 年以后的

Claude 会先和你确定范围(`scope.md`),再按相关度检索 arXiv / OpenAlex,并沿代表作的参考文献和被引继续找，按规则打分后列出候选(不下载);你确认后批量下载入库，然后进入下面的脉络分析。

**已有论文:**

在 Claude Code 中打开存放论文的目录，直接说:

> 分析 papers/ 里这批论文的研究脉络
> 这个领域在追问哪些问题?哪些还没解决?
> 统计一下这些论文的发表情况和 CCF/中科院分区

论文按子目录分方向(`papers/01-xxx/`、`papers/02-yyy/`),文件名形如 `<arXiv ID>_<标题>.pdf` 时识别最准;非 arXiv 论文可以提供带 `doi` 列的 CSV。详见 [SKILL.md](SKILL.md)。

输出默认放在论文目录旁边的 `lineage/`,用浏览器打开 `lineage/lineage.html` 即可。

## 自动更新

对 Claude 说"每天自动追踪新论文、每周更新脉络",它会按 [references/automation.md](references/automation.md) 为你的项目配置:

- **每日:** 按你的领域检索 arXiv / Semantic Scholar / OpenAlex 新论文(去重、打分、下载到待审目录，可选严格规则自动入库),然后重建脉络图和发表情况。
- **每周:** 用 `claude -p` 按你的范围审核新论文、给新论文标注研究问题、增量修订报告，并写周报 `lineage/updates.md`。

领域相关的内容(检索式、锚点论文、打分规则、分类、时间表)全部写在项目里的一个 `research-lineage.json` 中，由 Claude 根据你的 `scope.md` 生成，并先用你已有的论文集离线测量召回和误收(`crawl.py --eval`),确认后才安装定时任务。示例见 [automation/config.example.json](automation/config.example.json)。定时任务用 cron(Linux/macOS);Windows 可用任务计划程序运行同样的命令。

## 自定义提示词

skill 不知道你的领域，也不知道你想要什么样的报告。把要求写进项目里的 `lineage/prompts/`,Claude 在对应步骤会先读它们，并以它们为准:

| 文件 | 作用 |
|---|---|
| `scope.md` | 领域定义：锚点论文、收录条件、不收清单。防止论文集"走偏"后照样分析 |
| `questions.md` | 问题树偏好：固定的根问题、命名方式、粒度 |
| `narrative.md` | 报告的结构、侧重点、篇幅、语气 |
| `extra.md` | 通用要求(术语、汇报风格等) |

模板和说明在 [prompts.example/](prompts.example/)。也可以在对话中直接说"以后报告都要……",Claude 会写进对应文件。这些文件在你的项目里，更新 skill 不会覆盖它们。

## 数据与版权

- 等级表(`data/*.csv`)是 [ShowJCR](https://github.com/hitfyd/ShowJCR) 整理的 CCF 推荐目录 2026、中科院分区表升级版 2025、JCR 2025、新锐分区 2026、国际期刊预警名单 2025 的**原样副本**,随仓库提供，开箱即用。它们沿用 ShowJCR 的 GPL-3.0 条款，不属于本仓库的 MIT 许可;排名本身归原发布方(CCF、中国科学院文献情报中心、Clarivate 等)所有，仅供学术参考。权利方要求时我们会立即移除。完整声明见 [data/README.md](data/README.md)。
- 如果数据被移除或损坏,`python3 -I scripts/fetch_data.py` 会从同一 ShowJCR 提交重新下载并校验 sha256。
- 论文元数据来自 arXiv、Semantic Scholar 和 OpenAlex 的公开 API。
- 等级描述的是出版场所，不是论文质量;本 skill 不用等级给论文排序。

## 目录

```
SKILL.md              skill 说明(Claude 读)
scripts/              collect / analyze / questions / venues / render / fetch_data
references/           指标解读、问题树方法(Claude 在相应步骤读)
prompts.example/      自定义提示词模板
automation/           自动更新：run.py(daily/weekly/cron)、crawl.py、每周任务提示词模板、配置示例
data/                 等级表(ShowJCR 副本，声明见 data/README.md)、venue_aliases.json
install.sh            安装与更新
```

## 参与改进

欢迎提 issue 和 PR。比较有价值的方向：更多出版场所别名(`data/venue_aliases.json`)、新年度等级表的适配(见 [data/README.md](data/README.md) 的"维护者：更新等级表")、英文报告的打磨。改动脚本后，至少用一小批论文完整跑一遍 collect → analyze → venues → render。更新记录见 [CHANGELOG.md](CHANGELOG.md)。

## 许可证

代码以 [MIT](LICENSE) 许可发布。`data/*.csv` 等级表不适用 MIT,见 [data/README.md](data/README.md)。

# 更新记录

## 0.1.0 — 2026-10-15

首个公开版本。

- 收集：arXiv + Semantic Scholar,OpenAlex 补充非 arXiv 论文的引用关系;缓存与增量更新。
- 分析：奠基、桥梁、前沿论文，传承链，方向间流动，可能遗漏的论文;无分类时自动聚类。
- 研究问题树：标注模板、校验、问题间的引用分支(提出/回答/质疑/迁移/重开)。
- 发表情况：CCF 2026、中科院分区 2025、JCR 2025、新锐分区 2026、预警名单 2025;预印本每 7 天复查是否已正式发表(标题完全相同)。
- 网页：报告、问题脉络、时间线、引文网络、发表情况五个标签页;图表可缩放平移;论文表可检索、排序。
- 自定义提示词：项目内 `lineage/prompts/`(scope / questions / narrative / extra),模板在 `prompts.example/`。
- 等级表：随仓库附带 ShowJCR 原样副本(声明见 `data/README.md`);`scripts/fetch_data.py` 可从固定提交重新下载并校验。
- 从主题建库:`crawl.py --bootstrap`(不限近期、按相关度、沿种子论文的参考文献与被引扩展，只列候选不下载),`add_papers.py` 支持 `title:` 标题输入;流程见 SKILL.md 第 0 步。
- 自动更新:`automation/`(通用爬虫 + 每日重建 + 每周 `claude -p` 审核与标注 + cron 安装),领域规则写在项目的 `research-lineage.json`,配置流程见 `references/automation.md`。
- 安装：`install.sh`(克隆或更新;缺少等级表时自动补下载)。

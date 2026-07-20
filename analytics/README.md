# job_hunter_iter — 复盘分析模块（决策通道 + 校准闭环）

在 `octpus1230216-alt/job_hunter` 上加的「向后复盘闭环」最小可用实现。
目标：收集**已投递 / 已读不回 / 不合适**的结果，分析为啥没回音，对照岗位改简历，量化版本改进。

> **范式要点（来自 287 条真实申请的调参实验）**：「七维匹配度」几乎不预测录取结果（AUC<0.5），
> 真正决定结果的是「公司竞争力层级」（顶级厂实测过筛率仅 7.7% vs 非顶级 28%）。
> 因此本模块把**匹配度当可解释特征**、**预测交给决策通道 / 竞争力因子校准**，而非用 fit×因子直接当命中率。
> 实验显示 LLM 决策通道（过筛概率）AUC≈0.64，优于离线城市因子 0.61。

> 借鉴自 `MadsLorentzen/ai-job-search`（代码已逐文件读过）：`outcome.md` 数据模型、`04-job-evaluation.md` 五维评分（本模块已扩展为七维）、`apply.md` 的诚实不虚构原则、`job-scraper` 可插拔 portal 架构、`verify_pdf.py` 的 ATS 思路（Phase 2）。

## 快速开始（零依赖，免 API key）

```bash
cd job_hunter_iter
python seed_demo.py          # 写 5 条示例 + 2 版简历
python ingest_resume.py upload <原简历.pdf/.docx/.txt> --version orig   # 上传并解析原简历（FR9，改简历/指出不足的基准）
python score.py --all        # 离线 heuristic 七维评分（无 key 可跑，默认取该投递的 resume_version 作 profile）
python analyzer.py --out docs/report_demo.md   # 出复盘报告（含 fit×outcome 交叉 + A/B 回复率 + 差距分析提示词）
python revise.py --mode heuristic   # 对照被拒岗位生成修改草稿（免 key）
python export.py --version v2 --compile   # 导出 LaTeX/PDF 简历（无 TeX 则只出 .tex）
python export.py --ats --version v2 --jd <岗位id>   # ATS 关键词覆盖率校验
```

## 六大模块

| 文件 | 作用 | 双通道 |
|---|---|---|
| `collect.py` | 多源录入我的投递结果 | 手动 / CSV / 截图 OCR（贴 WorkBuddy）/ 爬虫占位 |
| `ingest_resume.py` | 上传并解析原简历（doc/pdf/txt → 文本），作为评分/改简历基准 | 直读 txt/md/tex / `pdftotext`(pdf) / `textutil`(doc, macOS) / 双通道降级提示词 |
| `score.py` | 七维匹配度评分（技能/经验/文化/职业/背景契合/薪资匹配/层级匹配，加权出总评；另含公司竞争力档位与真实概率）；**决策通道**：`--mode decide` 让 LLM 直接输出「是否建议投递 + 真实过筛概率 + 理由」（推荐预测出口） | 离线 heuristic（默认）/ LLM 直连（`--mode llm`）/ 决策通道（`--mode decide`）/ 导出提示词（`--export-prompt`） |
| `tune.py` | **校准闭环（零依赖）**：读 SQLite → 按 `competition_breakdown` 算各档位 positive/n + Beta 收缩 → 输出 `COMPETITION_FACTOR` 建议值 + 可粘贴字典 + 七维预测力诊断 | 命令行直接跑 `python analytics/tune.py`，或网页「🎯 校准」页可视化 |
| `analyzer.py` | 基础统计 + fit×outcome 交叉 + **简历版本 A/B 回复率** + JD 差距分析 | 导出提示词贴 WorkBuddy（默认）/ LLM 直连（`--mode llm`，预留） |
| `revise.py` | 对照被拒/已读不回岗位的 JD 差距，生成修改后简历草稿（Drafter-Reviewer 思路） | 导出提示词贴 WorkBuddy（默认）/ 启发式草稿（`--mode heuristic`，免 key）/ LLM 双代理（`--mode llm`） |
| `export.py` | 简历 LaTeX 生成 + ATS 关键词覆盖率校验 | 生成 .tex（默认）/ 编译 PDF（`--compile`）/ ATS 校验（`--ats`） |
| `modules/store.py` | SQLite 存储层（数据模型落地，含 `resume_ab()` A/B 分组统计） | — |

## 产品文档（资深 PM 视角，聚焦说明与需求，不含市场分析）

| 文档 | 内容 |
|---|---|
| `docs/PRODUCT_OVERVIEW.md` | 产品说明：定位、闭环、价值、设计原则 |
| `docs/PRD.md` | 产品需求文档：目标、用户故事、FR 总览与详述、成功度量 |
| `docs/DESIGN_SPEC.md` | 设计规格：架构、数据模型、状态机、七维评分、双通道、模块接口、A/B 口径 |
| `docs/REQUIREMENTS.md` | 功能需求验收清单：逐条 FR 的验收标准与边界 |
| `docs/PRD_ANALYTICS.md` | 合并进 `job_hunter` 主仓的接口映射草案 |

## 数据模型（落在 `data/job_search.db`）

`applications` 表关键字段：
- 结果状态 `last_status` ∈ {applied, in_progress, interview, offer, hired, offer_declined, **rejected(不合适)**, **no_response(已读不回)**, interview_only, withdrawn}
- 七维评分 `fit_technical / fit_experience / fit_behavioral / fit_career / fit_background(背景契合) / fit_salary(薪资匹配) / fit_level(层级匹配)`，加权 `fit_overall`；另 `competition_level`(公司竞争力) / `realistic_prob`(真实概率)
- `job_quality`(1–5 手动，岗位本身好坏)；`resume_version`(A/B 变量)
- 归档 `archive_path` → `data/applications/<company>_<role>/`（借 MadsLorentzen 约定，存 `job_posting.md` + `outcome.md`）
- `resumes` 表：版本 / 正文 / change_log

## 录入方式

```bash
python collect.py add                         # 交互式逐条录入
python collect.py import-csv csv_template/application_template.csv   # 批量
python collect.py image <截图.png>            # 截图 → 打印「贴给 WorkBuddy」提示词（OCR 免 key）
python collect.py image --json <回填.json>    # WorkBuddy 返回 JSON 后导入
python collect.py scraper                      # 预留爬虫接口（暂不实现）
python ingest_resume.py upload <原简历.pdf/.docx> [--version orig]   # 上传原简历并解析为文本（📝 待实现，FR9）
```

## 关键原则
- **诚实不虚构**：差距必须可见，不为凑关键词编造经历。
- **已读不回 = 弱信号**：不当因果，不据此大改简历。
- **高 fit + 不合适 = 重点信号**：说明不是岗不对人，而是简历没讲清匹配点（交叉分析会自动高亮）。
- **原简历为基准（FR9，已实现）**：指出不足 / 对照 JD 改简历都从你上传的原简历（doc/pdf/txt）出发，需先有原简历文本才能比对。

## 与 job_hunter 的合并指引
见 `docs/PRD_ANALYTICS.md`。当前 `job_hunter_iter` 是自包含 SQLite 工具；合并进主仓需 clone `octpus1230216-alt/job_hunter` 后，将 `modules/`、`collect.py`、`score.py`、`analyzer.py`、`revise.py`、`export.py` 按 `docs/PRD_ANALYTICS.md` 的接口对齐并入（主要改动：`tracker.py` 扩字段、`pages/` 加复盘页、LLM 走现有 `llm.py` 双通道）。环境 git 现已可用，可直接 `git init` 提交本目录，或与主仓做目录级合并。

## 网页集成与数据闭环

本模块已通过网页暴露给日常使用：
- **📊 审核挑选**：一键运行 AI 决策通道（按过筛概率排序），替代纯匹配度。
- **🎯 校准**：可视化 `tune.py`——各档位实测过筛率 + 建议因子，一键写回
  `data/competition_overrides.json`（运行时优先于 store.py 默认值）；并诊断 fit_overall 预测力。
- **数据闭环**：网页「📈 投递追踪」（JSON，modules.tracker）每次状态更新自动回灌 analytics SQLite，
  「✨ 生成简历」生成后写入追踪——真实结果自动流入校准。历史数据可点「🔄 回灌校准库」补齐。
- **🏢 AI 推荐公司**：发现页调用 `company_finder` 拓展投递方向（纯 LLM，无需联网）。
- **🔒 可选鉴权**：设置环境变量 `JOBHUNTER_PASSWORD`（或 Streamlit secrets 的 `password`）后，全页面需密码访问。

## 后续阶段（已实现部分）
- ✅ Phase 1：简历版本 A/B 回复率（`analyzer` A/B 小节）、JD 关键词抽取（ATS 校验复用）
- ✅ Phase 2 核心已落地：`revise.py` Drafter-Reviewer 双代理、`export.py` LaTeX + ATS 校验
- ✅ 网页集成 + 校准闭环 + 决策通道 + 数据回流 + 可选鉴权 已在 v1.6.0 / v1.7.0 落地（见根 CHANGELOG）
- ⏳ 待做：可插拔爬虫 connector（BOSS/脉脉 portal skill）、用复盘数据反哺评分框架的自动再训练

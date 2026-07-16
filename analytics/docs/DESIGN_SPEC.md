# 设计规格（Design Spec）· 复盘分析模块

> 版本：v1.0 · 日期：2026-07-15 · 状态：已实现
> 范围说明：本文档描述产品的技术设计与实现口径，**不含市场分析与可行性验证**。

---

## 1. 架构总览

```
                        录入层（投递结果 + 原简历）
   collect.py（结果：manual/csv/image/scraper）      ingest_resume.py（原简历：txt/md/tex/pdf/doc/docx）
        └──────────────────────────┬──────────────────────────┘
                                    ▼
                          modules/store.py  ◀── SQLite (data/job_search.db)
                                               │  (统一读写, 单一数据源)
        ┌──────────────┬──────────────┬────────┴────────┬──────────────┐
        ▼              ▼              ▼                  ▼              ▼
     score.py      analyzer.py     revise.py         export.py      (A/B 统计)
   七维评分        统计+交叉+差距   对照JD改简历      LaTeX+ATS校验    resume_ab()
        │              │              │                  │
        └──────────────┴───── 双通道 ┴──────────────────┘
              export(贴WorkBuddy) / heuristic(本地) / llm(直连,需key)
```

**数据流原则**：所有模块只通过 `store.py` 读写 SQLite，不直接拼 SQL；评分类结果回写 `fit_*`，分析类结果输出 Markdown / 提示词。

**双主线复用同一底座**：本产品服务两个目标，但**不需要两套架构**——
- **目标 A（前瞻）**：`collect`(prospect) → `score --profile`(对照原简历) → `revise` → `export`，终点是"改好的简历"。
- **目标 B（复盘）**：`collect`(已投结果) → `score` → `analyzer`(统计/交叉/A-B)，终点是"复盘结论"。
- 二者共享 `ingest_resume`(原简历基准)、`store`(单一数据源)、七维评分模型、双通道策略。区别仅在入口记录的状态（`prospect` vs 真实结果）与终点产物。架构评估结论见 §11。

## 2. 目录结构

```
analytics/
├── collect.py              # 多源录入（4 适配器）
├── ingest_resume.py        # 原简历上传与解析（doc/pdf/txt → 文本，📝 待实现）
├── score.py                # 七维评分（双通道）
├── analyzer.py             # 统计 + 交叉 + 差距 + A/B
├── revise.py               # 对照 JD 改简历（三模式）
├── export.py               # LaTeX 生成 + ATS 校验
├── seed_demo.py            # 示例数据（5 条 + 2 版简历）
├── csv_template/
│   └── application_template.csv
├── modules/
│   └── store.py            # 存储层（数据模型 + 统计查询）
├── data/                   # 运行时生成（被 .gitignore 排除）
│   ├── job_search.db
│   ├── applications/<company>_<role>/{outcome.md, job_posting.md, revised_resume.md}
│   └── resume_*.tex / *.pdf
├── docs/                   # 产品文档
├── README.md
└── .gitignore              # 排除 data/ 个人数据
```

## 3. 数据模型

### 3.1 `applications` 表（每条投递结果一行）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | INTEGER PK | 自增 | 主键 |
| `platform` | TEXT | | BOSS / 脉脉 / 其他 |
| `company` | TEXT | ✅ | 公司名 |
| `sector` | TEXT | | 行业 |
| `role` | TEXT | ✅ | 岗位 |
| `role_type` | TEXT | | 实习/初级/中级/高级/专家 |
| `channel` | TEXT | | 来源渠道（主动沟通/猎头/内推/海投） |
| `applied_date` | TEXT | | 投递日期 YYYY-MM-DD |
| `source_url` | TEXT | | JD 链接 |
| `jd_text` | TEXT | | JD 关键段落（差距分析原材料） |
| `hr_reply` | TEXT | | HR 原话（可选） |
| `resume_version` | TEXT | | A/B 变量：用的第几版简历 |
| `last_status` | TEXT | ✅ | 结果状态（见 §4） |
| `status_date` | TEXT | | 状态更新日期 |
| `fit_technical` | INTEGER | | 七维·技能 0–100 |
| `fit_experience` | INTEGER | | 七维·经验 0–100 |
| `fit_behavioral` | INTEGER | | 七维·文化 0–100 |
| `fit_location` | TEXT | | 地点：PASS / FAIL / FLAG（不加权） |
| `fit_career` | INTEGER | | 七维·职业 0–100 |
| `fit_background` | INTEGER | | 七维·背景/领域契合 0–100（新增） |
| `fit_salary` | INTEGER | | 七维·薪资期望匹配 0–100（新增） |
| `fit_level` | INTEGER | | 七维·目标层级匹配 0–100（新增） |
| `competition_level` | TEXT | | 公司竞争力档位：顶级厂/一线大厂/中厂B轮C轮/初创天使轮/未知（不计入 fit） |
| `realistic_prob` | INTEGER | | 真实通过概率估计 0–100 = fit_overall × 竞争力因子（顶级厂0.30/一线0.50/中厂0.70/初创0.90/未知0.60） |
| `fit_overall` | INTEGER | | 加权总分 0–100 |
| `job_quality` | INTEGER | | 岗位本身好坏 1–5（手动，不参与匹配） |
| `notes` | TEXT | | 备注 |
| `archive_path` | TEXT | | `data/applications/<company>_<role>/` |

### 3.2 `resumes` 表（每版简历一行）

| 字段 | 类型 | 说明 |
|---|---|---|
| `version` | TEXT PK | 简历版本号（如 orig/v1/v2） |
| `text` | TEXT | 简历正文（原简历上传后存解析出的纯文本） |
| `created_date` | TEXT | 创建日期 |
| `change_log` | TEXT | 这版改了啥（A/B 实验记录） |
| `source_file` | TEXT | 原文件来源路径（FR9，上传原简历时记录） |
| `source_format` | TEXT | 原文件格式（doc/docx/pdf/txt/md/tex，FR9） |

## 4. 状态机（`last_status`）

**枚举值**
`prospect`(待分析/观望，新 JD 未投) · `applied`(已投待回音) · `in_progress`(流程中) · `interview`(进入面试) · `offer`(拿 offer) · `hired`(已入职) · `offer_declined`(拒 offer) · `rejected`(不合适，主动拒绝) · `no_response`(已读不回，沉默) · `interview_only`(面了无下文) · `withdrawn`(主动撤投)

**信号分类（分析口径）**
- **强信号** `STRONG_SIGNAL = {rejected}`：主动拒绝，信息量大，重点分析。
- **弱信号** `WEAK_SIGNAL = {no_response, interview_only}`：沉默，不当因果，不据此大改简历。
- 其余状态（prospect/applied/interview/offer…）为中性或正向；`prospect` 仅为目标 A 的"待评估 JD"，**不参与目标 B 的复盘统计与 A/B 回复率**（见 §8 口径过滤）。

**流转规则**：状态由用户录入/更新（`set_status`），系统不自动流转；分析时按"强/弱信号"分桶，而非按时间线强制推进。

## 5. 七维评分模型（+公司竞争力 / 真实概率）

| 维度 | 字段 | 权重 | 取值 |
|---|---|---|---|
| 技能 Technical | `fit_technical` | 24% | 0–100 |
| 经验 Experience | `fit_experience` | 20% | 0–100 |
| 文化 Behavioral | `fit_behavioral` | 12% | 0–100 |
| 职业 Career | `fit_career` | 24% | 0–100 |
| 背景契合 Background | `fit_background` | 12% | 0–100（新增：领域/项目背景隐性契合） |
| 薪资匹配 Salary | `fit_salary` | 4% | 0–100（新增：期望 vs 岗位区间） |
| 层级匹配 Level | `fit_level` | 4% | 0–100（新增：岗位级别 vs 资历） |
| 地点 Location | `fit_location` | 不加权 | PASS / FAIL / FLAG |

**总分**：`fit_overall = round(技*0.24 + 经*0.20 + 文*0.12 + 职*0.24 + 背*0.12 + 薪*0.04 + 级*0.04)`

**公司竞争力（不计入 fit）**：同一 fit 在顶级厂真实命中率更低。`competition_level`（顶级厂/一线大厂/中厂B轮C轮/初创天使轮/未知）由 `store.infer_competition` 依公司名推断或 `collect` 显式录入；`realistic_prob = round(fit_overall × 竞争力因子)`，因子：顶级厂0.30 / 一线0.50 / 中厂0.70 / 初创0.90 / 未知0.60。复盘应以 `realistic_prob` 而非单纯 `fit_overall` 判断真实命中率。

**分档（交叉分析用）**：Strong(≥75) / Good(60–74) / Moderate(45–59) / Weak(30–44) / Poor(<30)

**heuristic 模式说明**：无 LLM 时以"JD 与简历关键词重叠率"作代理（`overlap→30~95` 映射），文化/背景给中性分，薪资/层级用简单规则解析，公司竞争力按名推断，地点默认 PASS。**这是基线，非真实评分**；真实评分用 `--mode llm` 或 `--export-prompt`。

## 6. 双通道架构

贯穿 score / analyzer / revise 三处，三选一：

| 模式 | 行为 | key | 产出 |
|---|---|---|---|
| `export`（默认） | 打印结构化提示词 | 否 | 用户贴给 WorkBuddy 完成分析/评分 |
| `heuristic` | 本地规则计算 | 否 | 基线结果（评分/修改草稿） |
| `llm` | 直连 OpenAI 兼容接口 | 是 | 全自动 JSON 结果 |

- `score.py`：`--mode heuristic`(默认) / `--mode llm` / `--export-prompt`
- `analyzer.py`：`--mode export`(默认, 提示词) / `--mode llm`(预留)
- `revise.py`：`--mode export`(默认) / `--mode heuristic` / `--mode llm`

**LLM 调用约定**：`OPENAI_API_KEY` 环境变量；模型 `OPENAI_MODEL`（默认 `gpt-4o-mini`）；`response_format=json_object`。`revise --mode llm` 走 Drafter→Reviewer 双调用（独立上下文审查）。

## 7. 模块接口（CLI 与核心函数）

### 7.1 `modules/store.py`（存储层）
- `init_db(db_path=DEFAULT_DB) -> Connection`
- `add_application(**fields) -> int`（自动补 `archive_path`）
- `get_all() / get_by_id(id) / get_by_status(list) / get_unscored()`
- `update_fit(id, *, technical, experience, behavioral, location, career, background, salary, level, competition, overall, realistic)`
- `set_status(id, status, status_date)`
- `add_resume(version, text, created_date, change_log)`
- `get_resume(version) / get_latest_resume()`
- `count_by(column)` — 允许列：`platform/last_status/role_type/sector`
- `fit_outcome_cross()` — fit 分档 × 状态 交叉
- `resume_ab()` — 按 `resume_version` 分组算投递数/正反馈/回复率

### 7.2 `collect.py`
- `python collect.py add` — 交互录入
- `python collect.py import-csv <file.csv>` — 批量导入
- `python collect.py image [<截图.png>] [--json <回填.json>]` — OCR 双通道
- `python collect.py scraper` — 爬虫占位
- 适配器基类 `ScraperAdapter.fetch() -> list[dict]`（预留，抛 `NotImplementedError`）

### 7.3 `score.py`
- `python score.py --all [--mode heuristic|llm] [--profile <file>]`
- `python score.py --id <N> [--mode llm] [--export-prompt] [--profile <file>]`
- 核心：`heuristic_score(jd, profile, company) -> dict` / `score_with_llm(row, profile) -> dict` / `build_llm_prompt(...)`；评分时优先读取该投递记录的 `resume_version` 文本做对照（保证 A/B 准确）

### 7.4 `analyzer.py`
- `python analyzer.py [--mode export|llm] [--out <md>]`
- 输出四段：基础统计 / fit×outcome 交叉 / JD 差距提示词 / A/B 回复率
- 核心：`build_report(conn, mode)` / `_print_cross` / `_gap_section` / `_print_ab`

### 7.5 `revise.py`
- `python revise.py [--id <N>] [--mode export|heuristic|llm] [--model <m>]`
- 默认目标：所有 rejected/no_response 且 `resume_version` 非空
- 产出：`data/applications/<slug>/revised_resume.md`
- 核心：`heuristic_revise(jd, resume) -> dict` / `llm_revise(...)`(Drafter+Reviewer) / `build_workbuddy_prompt(...)`

### 7.6 `export.py`
- `python export.py --version <v> [--out <tex>] [--compile]`
- `python export.py --ats --version <v> --jd <id>` — ATS 覆盖率
- 核心：`resume_to_latex(version, text)` / `ats_coverage(jd, resume) -> {coverage, missing, total}`

### 7.7 `ingest_resume.py`（原简历上传，已实现）
- `python ingest_resume.py upload <file> [--version <v>]` — 上传原简历
- 解析器分发：`.txt/.md/.tex` 直读；`.pdf` 走 `pdftotext`；`.doc/.docx` 走 `textutil`(macOS) / `libreoffice --convert-to txt`
- 无可用解析器 → 打印"贴给 WorkBuddy 提取文本"提示词（双通道降级）
- 核心：`parse_resume(path) -> str` / `ingest(path, version)` → `store.add_resume(...)`
- 解析结果作为基准版本，供 `score --profile` 与 `revise` 引用

## 8. A/B 回复率口径

**定义（SQL，`resume_ab()`）**
- 分组键：`resume_version`（非空）
- `positive` = `last_status IN ('interview','offer','hired','offer_declined')`
- `回复率 = positive / n × 100%`

**对比判定（`analyzer._print_ab`）**
- 取 `versions` 列表的首（最早）与尾（最新）
- `delta = 新版本回复率 − 旧版本回复率`
- 判定：delta>0 → 📈 有效；delta<0 → 📉 无效需复盘；delta=0 → ➖ 持平

**统计注意**：样本量过小（n<5）时结论不可靠，展示但不强下结论；`resume_version` 缺失的记录不计入。

## 9. 归档约定

每条投递记录归档到 `data/applications/<company>_<role>/`（`slug` = 小写、空格转下划线、非字母数字转 `_`）：
- `outcome.md` — 状态 + 面试阶段勾选 + 备注
- `job_posting.md` — JD 原文（供差距分析）
- `revised_resume.md` — 修改草稿（revise 产出，不覆盖原简历）

## 10. 技术约束与合并说明

- **零重依赖**：MVP 仅用 stdlib（`sqlite3`/`argparse`/`re`/`csv`/`json`/`subprocess`）。可选：`openai` / `pdftotext` / `lualatex`。
- **存储差异**：本模块用 SQLite；主仓用 JSON（`data/applications/applications.json`）。合并时需统一存储抽象或双写。
- **LLM 接口差异**：本模块直连 OpenAI 兼容；主仓 `llm.py` 抽象 DeepSeek/OpenAI/Ollama。合并时 analyzer/revise 应改走主仓 `llm.py`。
- **隐私**：`data/` 经嵌套 `.gitignore` 排除，个人投递数据不入库、不上云。
- **合并落点（规划）**：Streamlit 页 `pages/07_📉_复盘分析.py`；爬虫做成 `connectors/<portal>_portal.py` portal adapter。
- **原简历解析依赖（FR9，可选）**：`.pdf` → `pdftotext`（poppler）；`.doc/.docx` → macOS 自带 `textutil` 或 `libreoffice --headless --convert-to txt`。两者缺省时降级为"双通道提示词"，不阻断 MVP；图片型 PDF 无文本层时提示走 OCR 提取。

## 11. 两大目标下的架构评估（结论）

**评估问题**：产品需同时服务「目标 A 前瞻（新岗位→分析→改简历）」与「目标 B 复盘（已投递→回溯）」，现有架构是否需要改变？

**结论：核心架构无需重做，仅需一处轻量补强（现已实现）。**

| 维度 | 评估 | 是否需要改 |
|---|---|---|
| 数据存储 | `store` + SQLite 单一数据源，A/B 两主线共用，无需分库 | 否 |
| 七维评分模型（含公司竞争力） | `score` 同时服务"评估新 JD"与"给已投结果打分"，模型通用 | 否 |
| 双通道策略 | export/heuristic/llm 三模式贯穿 score/revise，两主线通用 | 否 |
| 原简历基准 | `ingest_resume` 已落地，A 作起点、B 作参照 | 否 |
| 新 JD 的入口 | 当前"分析一个新岗位"需先建一条 application 记录，但 `status` 缺"尚未投递/待评估"语义，易与"已投递复盘"数据混淆 | ✅ 已加 `prospect` |
| 复盘数据纯净度 | `analyzer` 的看板/交叉/A-B 应按"真实投递状态"过滤，避免 `prospect` 污染结论 | ✅ 已过滤 |

**已落地的两处改动（低风险，非阻塞）**
1. ✅ **状态枚举加 `prospect`（待分析/观望）**：目标 A 录入新 JD 时状态填 `prospect`，明确"尚未投递、仅评估"。改动点：`store.py` `STATUS_ENUM` 增 `prospect` + `EXCLUDE_FROM_REVIEW` 集合；`collect.py add` 交互提示与 OCR 提示词补 `prospect` 说明。无表结构变更。
2. ✅ **复盘口径显式过滤 `prospect`**：`store.count_by` / `fit_outcome_cross` / `resume_ab` 新增 `exclude_prospect=True`（默认），取数时 `WHERE last_status NOT IN ('prospect')`；`analyzer._print_stats` 加口径说明。评分类 `get_unscored` **不过滤**（目标 A 的新 JD 也要被评分）。

**验证**：临时库单测通过——`prospect` 不进看板/交叉/A-B，但 `get_unscored` 仍覆盖 `prospect`（新 JD 可评分）。

**不做（避免过度设计）**
- 不拆 `jobs` 表与 `applications` 表：MVP 阶段单表 + `prospect` 状态即可清晰区分，拆分会带来存储抽象与迁移成本，留待合并进主仓时再考虑（见 §10）。
- 不为目标 A 单独做"JD 分析页"：复用 `collect`(prospect) + `score --profile` + `revise` + `export` 已能跑通，等 Streamlit 看板时再聚合。

**一句话**：底座（store / 七维模型 / 双通道 / 原简历）两目标通用；唯一要补的是"新 JD 用 `prospect` 状态入场 + 复盘统计排除 `prospect`"，属小修，不重构。

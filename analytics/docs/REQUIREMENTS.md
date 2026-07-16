# 功能需求验收清单（Requirements / Acceptance）

> 版本：v1.0 · 日期：2026-07-15
> 范围说明：逐条功能需求（FR）的验收标准与边界条件，**不含市场分析与验证**。
> 每条 FR 可追溯到 PRD §6 与用户原始诉求。

---

## FR1 多源录入"我的投递结果 / 新 JD"

- **优先级**：P0 · **状态**：✅ 已实现（服务目标 A + B）
- **前置条件**：`modules/store.py` 已初始化（`data/job_search.db` 存在）。
- **输入**：
  - `add`：交互式逐字段输入（含 `status`；**新 JD 填 `prospect`（待分析/观望）**）；
  - `import-csv <file>`：CSV（列名对齐 `applications` 表，见 `csv_template/`）；
  - `image [截图] [--json 回填.json]`：截图路径或 WorkBuddy 返回的 JSON；
  - `scraper`：无输入（占位）。
- **处理逻辑**：各适配器统一产出字段 dict → `store.add_application` 入库；同时写归档 `data/applications/<slug>/`。**`prospect` 记录归属目标 A（待评估 JD），不参与目标 B 的复盘统计与 A/B**（口径见 DESIGN_SPEC §8/§11）。
- **验收标准**：
  1. `company` 与 `role` 任一为空时拒绝入库并提示。
  2. CSV 导入跳过缺 `company`/`role` 的行，返回成功条数。
  3. `image` 无 `--json` 时打印"贴给 WorkBuddy"提示词；带 `--json` 时解析入库（缺 company/role 则取消）。
  4. `scraper` 调用 `ScraperAdapter().fetch()` 抛 `NotImplementedError` 并打印扩展位说明，不崩溃。
  5. ✅ `prospect` 状态录入后，目标 B 的 `count_by`/`fit_outcome_cross`/`resume_ab` 默认（`exclude_prospect=True`）显式排除之，不污染复盘结论；评分类 `get_unscored` 不排除（新 JD 也要评分）。
- **边界/异常**：
  - `job_quality` 非 1–5 整数 → 存 NULL，不报错。
  - CSV 空字符串字段 → 转为 NULL。
- **关联**：`collect.py`、DESIGN_SPEC §4（状态机）、§11（架构评估）

## FR2 七维匹配度评分（+公司竞争力/真实概率）

- **优先级**：P0 · **状态**：✅ 已实现（v1.1 由五维扩展为七维，并新增公司竞争力维度）
- **输入**：`--id <N>` 或 `--all`；`--mode heuristic|llm`；`--export-prompt`；`--profile <file>`（默认取该投递的 `resume_version`，否则最新简历）。
- **七维**：技能 / 经验 / 文化 / 职业 / **背景契合** / **薪资期望匹配** / **目标层级匹配**（各 0–100，权重 0.24/0.20/0.12/0.24/0.12/0.04/0.04）。
- **额外维度（不计入 fit）**：
  - `competition_level`（公司竞争力档位：顶级厂/一线大厂/中厂B轮C轮/初创天使轮/未知）——同一 fit 在顶级厂真实命中率更低；
  - `realistic_prob` = `fit_overall × 竞争力因子`（顶级厂0.30 / 一线0.50 / 中厂0.70 / 初创0.90 / 未知0.60）——真实通过概率估计。
- **处理逻辑**：
  - `heuristic`：JD 与简历关键词重叠率 → 七维分（基线）；薪资/层级用简单规则解析；公司竞争力按名推断；
  - `llm`：调 OpenAI 兼容接口返回 JSON → 七维分 + competition_level + realistic_prob；
  - `export-prompt`：打印评分提示词，不调接口、不写库。
- **验收标准**：
  1. 七维分写入 `fit_technical/experience/behavioral/career/background/salary/level` 与 `fit_location`，`fit_overall` 按权重计算，`competition_level`/`realistic_prob` 一并写入。
  2. 评分时优先读取该投递记录的 `resume_version` 文本做对照（保证 A/B 准确），无则回退最新简历。
  3. `--all` 只评 `fit_overall IS NULL` 的记录，不覆盖已评分/预填值。
  4. `--id <N>` 强制重评指定记录。
  5. `llm` 缺 `openai` 包或 `OPENAI_API_KEY` 时明确报错退出，不静默失败。
- **边界/异常**：
  - JD 或简历为空 → heuristic 给中性默认分（约 50）。
  - 权重合计 = 1.0，地点不参与加权。
- **关联**：`score.py`、`store.update_fit`、`store.infer_competition`、`store.competition_breakdown`
- **变更说明**：v1.0 为五维（技能/经验/文化/职业/地点）；v1.1 扩出背景契合/薪资匹配/层级匹配三维并新增公司竞争力维度——复盘数据证明"技能重叠高却仍被拒"多由背景契合、薪资期望错配、目标层级错配、公司竞争激烈导致，原五维无法捕捉。

## FR3 结果看板（统计）

- **优先级**：P0 · **状态**：✅ 已实现
- **输入**：无（读全库）。
- **处理逻辑**：`count_by` 对 `last_status/platform/role_type/sector` 分组计数。
- **验收标准**：
  1. 输出四类分组占比，空值显示为 `(空)`。
  2. 仅允许白名单列（`platform/last_status/role_type/sector`），其他列抛 `ValueError`。
- **关联**：`analyzer._print_stats`、`store.count_by`

## FR4 fit×outcome 交叉分析

- **优先级**：P0 · **状态**：✅ 已实现
- **输入**：无（需 `fit_overall` 非空）。
- **处理逻辑**：`fit_outcome_cross` 按分档 × 状态计数；按强/弱信号 + 分档标注信号。
- **验收标准**：
  1. Strong/Good + `rejected` → 标注"高匹配却被拒：简历没讲清匹配点"。
  2. Strong/Good + `no_response`/`interview_only` → 标注"高匹配却沉默：别急着大改"。
  3. 低分档 + `rejected` → 标注"低匹配被拒：意料之中"。
- **边界/异常**：`fit_overall` 全为空时交叉表为空，不报错。
- **关联**：`analyzer._print_cross`、`store.fit_outcome_cross`

## FR5 JD 差距分析

- **优先级**：P0 · **状态**：✅ 已实现
- **输入**：`--mode export`(默认) / `llm`(预留)；需 rejected/no_response 记录且最好有 `jd_text` 与对应简历版本。
- **处理逻辑**：拉目标记录 → 拼 JD + 简历版本正文 → 默认打印"贴给 WorkBuddy"提示词；`llm` 预留直连。
- **验收标准**：
  1. 默认模式输出结构化提示词（含每段 JD、简历版本、正文），用户可直接贴给 WorkBuddy。
  2. 提示词含"诚实不虚构""已读不回为弱信号"约束。
  3. 无 rejected/no_response 记录时给出"暂无"提示，不报错。
- **边界/异常**：目标记录无对应 `resume_version` → 提示"未记录该版本简历，可手动补充"。
- **关联**：`analyzer._gap_section`

## FR6 简历版本 A/B 回复率

- **优先级**：P1 · **状态**：✅ 已实现
- **输入**：无（需 `resume_version` 非空）。
- **处理逻辑**：`resume_ab` 分组算投递数/正反馈；`_print_ab` 对比首尾版本。
- **验收标准**：
  1. 正反馈口径 = interview/offer/hired/offer_declined。
  2. 回复率 = 正反馈/投递数 × 100%，四舍五入。
  3. 存在 ≥2 版本时输出 delta 与 📈/📉/➖ 判定。
- **边界/异常**：
  - 无 `resume_version` 记录 → 提示"暂无，无法对比"。
  - n=0 时回复率显示 0%，不除零。
- **关联**：`analyzer._print_ab`、`store.resume_ab`

## FR7 对照 JD 修改简历

- **优先级**：P2 · **状态**：✅ 已实现
- **输入**：`--id <N>` 或默认（rejected/no_response 且 `resume_version` 非空）；`--mode export|heuristic|llm`；`--model`。
- **处理逻辑**：
  - `export`：打印 Drafter+Reviewer 提示词（贴 WorkBuddy）；
  - `heuristic`：本地规则找 JD 有/简历缺的关键词 → 生成草稿写盘；
  - `llm`：Drafter 起草 → Reviewer 独立审查 → 终稿写盘。
- **验收标准**：
  1. `heuristic`/`llm` 产出 `data/applications/<slug>/revised_resume.md`，不覆盖原简历。
  2. `heuristic` 过滤泛词（"经验/能力/要求"等），最多列 12 个缺失关键词。
  3. `llm` 缺依赖/key 时明确报错退出。
  4. `export` 模式不写库、只打印提示词。
- **边界/异常**：无目标记录 → 提示"用 collect 录入带 resume_version 的 rejected/no_response"。
- **关联**：`revise.py`

## FR8 简历 LaTeX 导出 + ATS 校验

- **优先级**：P2 · **状态**：✅ 已实现
- **输入**：`--version <v>`；`--out <tex>`；`--compile`；`--ats --jd <id>`。
- **处理逻辑**：
  - 默认：简历正文 → 极简 LaTeX `.tex`（转义特殊字符）；
  - `--compile`：检测 TeX 引擎编译 PDF（无则降级提示）；
  - `--ats`：纯 Python 算 JD vs 简历关键词覆盖率 + 缺失清单；有 PDF 且装 `pdftotext` 时查文本层 cid 乱码。
- **验收标准**：
  1. 生成合法 `.tex`（含 `\section*{简历 <v>}` 与转义后正文）。
  2. ATS 覆盖率 = JD∩简历关键词 / JD 关键词 × 100%，并列出缺失关键词。
  3. 无 TeX 引擎 → 只出 `.tex` 并提示安装 TinyTeX，不报错中断。
  4. 无 `pdftotext` → 跳过文本层检查并说明，不报错。
- **边界/异常**：
  - 未指定 `--version` → 提示并返回。
  - `--ats` 无有效 `--jd` → 提示"无法算覆盖率"。
  - 无 `ctex` 宏包/字体 → 编译失败但保留 `.tex`，提示可能缺包。
- **关联**：`export.py`

## FR9 原简历上传与解析（doc/pdf/txt → 文本）

- **优先级**：P0 · **状态**：✅ 已实现
- **前置条件**：`modules/store.py` 已初始化。
- **输入**：`upload <file> [--version <v>]`；文件扩展名 `.doc/.docx/.pdf/.txt/.md/.tex`。
- **处理逻辑**：
  - 按扩展名选解析器 → 纯文本；
  - 系统工具（textutil / pdftotext / libreoffice）优先；缺失则降级为"导出提示词"双通道；
  - 解析文本写入 `resumes` 表（拟新增 `source_file` / `source_format` 字段记录来源），作为基准版本（原简历）。
- **验收标准**：
  1. `.txt/.md/.tex` 上传后 `resumes.text` 与原文一致（空白/编码不丢）。
  2. `.pdf` 在装有 `pdftotext` 时提取正文文本；未装时明确提示"需 poppler，或走双通道贴文本"，不崩溃。
  3. `.doc/.docx` 在 macOS（textutil）或装有 LibreOffice 时转为文本；否则降级提示。
  4. 无可用解析器时打印 WorkBuddy 提取提示词，不静默失败。
  5. 上传后该版本可作为 `score --profile` 与 `revise` 的基准原简历被引用。
- **边界/异常**：
  - 文件不存在 / 非支持扩展名 → 报错退出并列出支持列表。
  - 解析文本为空（如图片型 PDF 无文本层）→ 提示"疑似图片型 PDF，请走双通道 OCR 提取文本"。
- **关联**：`ingest_resume.py`（拟新增）、`store.add_resume`（拟扩展 `source_file` / `source_format`）

---

## 验收总结

| FR | 优先级 | 服务目标 | 验收状态 |
|---|---|---|---|
| FR1 多源录入 | P0 | A + B | ✅ 4 适配器；`prospect` 状态 + 复盘口径过滤已落地（见 DESIGN_SPEC §11） |
| FR2 七维评分(+竞争力) | P0 | 共享 | ✅ 三模式 + 七维权重 + 竞争力/真实概率 + 防覆盖 |
| FR3 结果看板 | P0 | B | ✅ 四类分组 |
| FR4 交叉分析 | P0 | B | ✅ 强/弱信号高亮（demo 命中 2 条） |
| FR5 JD 差距 | P0 | B→A | ✅ 导出提示词 + 约束 |
| FR6 A/B 回复率 | P1 | B | ✅ 口径 + delta 判定 |
| FR7 改简历 | P2 | A | ✅ 三模式 + 落盘不覆盖 |
| FR8 LaTeX+ATS | P2 | A | ✅ 降级保护完整 |
| FR9 原简历上传 | P0 | A（基准）· B（参照） | ✅ 已实现 |

> 全部 FR 已按上述验收标准实现，并通过 `seed_demo.py` 全流程跑通验证。两目标框架已写入产品文档；`prospect` 状态补强已落地（`store` 加状态与过滤、`collect` 加提示、`analyzer` 加口径说明），并通过临时库单测（详见 DESIGN_SPEC §11）。

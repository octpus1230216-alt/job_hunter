# PRD：job_hunter「复盘分析」模块（Analytics / Feedback Loop）

> 供合并进 `octpus1230216-alt/job_hunter` 用。基于代码核查（job_hunter 现有模块 + MadsLorentzen/ai-job-search 借鉴）。
> 日期：2026-07-15 · 版本 v3

## 1. 背景与问题
用户已在 BOSS/脉脉 大量投递，出现两类负反馈：**主动拒绝（不合适 / rejected）** 与 **沉默（已读不回 / no_response）**。
现有 job_hunter「投递追踪」仅做状态标记与看板，**不产生可行动的洞察**，也无法对照岗位改进简历。
痛点原文：「把这些数据收集起来分析，最后对照岗位进行修改」。

## 2. 目标
把「投递追踪」升级为反馈闭环：从结果反推简历/策略问题，并量化改进效果（A/B）。
- 能回答：我的问题集中在哪类岗位？被拒 JD 与我简历差什么？换简历版本后回复率变没变？
- 输出：可落地的简历修改建议（诚实不虚构）。

## 3. 非目标（Out of Scope，本期不做）
- 不改「发现职位 / 智能匹配 / 生成简历」主流程（复用现有）。
- 不做自动代投。
- 不新增海外/国内采集平台（仅补 OCR 输入 + 爬虫占位接口）。

## 4. 数据模型变更（建议扩展现有追踪存储）
`applications` 增加字段：
- `last_status` 枚举新增 `rejected`(不合适) / `no_response`(已读不回) / `interview_only`
- 五维评分：`fit_technical / fit_experience / fit_behavioral / fit_location(PASS/FAIL/FLAG) / fit_career`，加权 `fit_overall`
- `job_quality`(1–5 手动，岗位本身好坏)
- `resume_version`（关联 `resumes`，A/B 变量）、`jd_text`、`hr_reply`
- 归档：`data/applications/<company>_<role>/{job_posting.md, outcome.md}`（借 MadsLorentzen 约定）

## 5. 功能需求
- **FR1 多源录入**：手动 / CSV / 截图 OCR（视觉 LLM 抽字段，确认后入库）/ 爬虫占位接口。
- **FR2 五维评分**：对齐 MadsLorentzen 五维（技能30/经验25/文化15/职业30 + 地点不加权）；子分写入投递记录。
- **FR3 结果看板**：状态 / 平台 / 级别 / 行业 占比。
- **FR4 fit×outcome 交叉**：高亮「高 fit + 不合适/已读不回」。
- **FR5 JD 差距分析**：对 rejected/no_response，拉 JD + 当时简历版本，列缺失技能/关键词与表述短板，给可替换段落。双通道（导出提示词贴 WorkBuddy / LLM 直连）。
- **FR6 A/B（Phase 1）**：不同 resume_version 的回复率对比。✅ 已实现（`store.resume_ab()` + `analyzer` A/B 小节）。
- **FR7 简历修改（Phase 2）**：对照 rejected/no_response 岗位的 JD 差距，生成修改后简历草稿。✅ 已实现（`revise.py`，三通道：导出提示词贴 WorkBuddy / 启发式草稿免 key / LLM 双代理）。
- **FR8 导出与 ATS（Phase 2）**：简历 LaTeX 生成 + ATS 关键词覆盖率校验。✅ 已实现（`export.py`：`--compile` 出 PDF、`--ats` 覆盖率表）。

## 6. 模块与页面
- `modules/analyzer.py`：统计 + 交叉 + 差距（调用 `llm.py`、`matcher.py`/五维、`resume_parser.py`）。
- `collect.py` / `score.py`：录入与评分。
- `pages/07_📉_复盘分析.py`：看板 + 交叉表 + 差距清单 + 建议区（待加）。
- 双通道：复用现有 `llm.py`（DeepSeek/OpenAI/Ollama）；无 key 时导出提示词贴 WorkBuddy。

## 7. 成功度量
- 定性：用户能明确说出「我的问题在 X」。
- 定量：同批岗位类型下，新简历版本回复率 ≥ 旧版本（A/B）。

## 8. 风险与合规
- 脉脉不支持 CDP，仅 OCR/手动，避免违规采集。
- 「已读不回」视为弱信号，不据此大改简历（防相关性误判为因果）。
- 所有数据本地，隐私优先；建议加 `.gitignore` 保护 `data/` 个人数据（借 MadsLorentzen `security_guards.py` 思路）。

## 9. 实现状态（2026-07-15）

独立可运行版本已落地于 `job_hunter_iter/`（SQLite + stdlib，零重依赖，免 key 跑通 MVP 全链路）：

| 需求 | 文件 | 状态 |
|---|---|---|
| FR1 多源录入 | `collect.py` | ✅ 手动/CSV/截图OCR/爬虫占位 |
| FR2 五维评分 | `score.py` | ✅ heuristic 默认 + LLM/导出提示词双通道 |
| FR3 结果看板 | `analyzer.py` | ✅ 状态/平台/级别/行业占比 |
| FR4 fit×outcome 交叉 | `analyzer.py` | ✅ 高亮「高 fit+不合适/已读不回」 |
| FR5 JD 差距分析 | `analyzer.py` | ✅ 导出提示词贴 WorkBuddy / LLM 预留 |
| FR6 A/B 回复率 | `store.resume_ab()` + `analyzer` | ✅ |
| FR7 简历修改 | `revise.py` | ✅ 三通道（含启发式免 key） |
| FR8 导出+ATS | `export.py` | ✅ LaTeX 生成 + ATS 覆盖率 |

**与 `job_hunter` 主仓合并**：仍为待办。当前 `job_hunter_iter` 是自包含 SQLite 工具，与主仓的 JSON 存储（`data/applications/applications.json`）+ `llm.py` 接口需对齐后才能并入；具体见第 6 节模块映射。环境 git 现已可用，可 `git init` 后提交，或 clone 主仓做目录级合并。

# 修改记录 (Changelog)

本文档记录项目的所有重要变更。

---

## v1.7.0 — 2026-07-20

### 新增 — 数据闭环 + 产品化（来自调参实验后续方案）
- **打通双存储孤岛（Phase 2）**：`modules/tracker`（UI 用 JSON）每次增改/状态更新自动回灌
  `analytics` 的 SQLite(applications)，新增幂等 `store.upsert_application_by_key`；追踪页「✨ 生成简历」
  生成后写入追踪，「📈 投递追踪」状态更新与「🔄 回灌校准库」按钮一起把真实结果流入校准页。
- **生成↔追踪打通**：生成定制简历时自动把岗位登记进投递追踪（含决策过筛概率），不再生成与追踪脱钩。
- **AI 推荐公司接入 UI（Phase 4）**：发现页新增「🏢 AI 推荐更多公司」面板，调用
  `modules/discovery/company_finder.expand_with_llm`（纯 LLM、无需联网），可勾选后注入 AI 搜索词。
- **AI 全网搜索健壮性**：`modules/ai_searcher` 不再静默吞错，接口失败/无返回时抛出明确错误，
  UI 给出可读提示（DuckDuckGo 即时接口已不稳定，建议改用国内平台/手动粘贴）。
- **可选访问鉴权（Phase 4）**：新增 `modules/auth.require_auth()`，设置环境变量 `JOBHUNTER_PASSWORD`
  （或 Streamlit secrets 的 `password`）后全页面需密码访问；未设置则保持开放。

### 文档
- 刷新 `analytics/README.md`（决策通道 / 校准页 / 数据闭环）；根 `README.md` 补充校准与决策说明。

---

## v1.6.0 — 2026-07-20

### 新增 — 决策通道接入网页 + 校准页（来自调参实验结论）
- **审核页修复（Phase 0）**：原审核页读取 `jobs_found` / `manual_jobs`（已无人写入）导致永远空白；
  改为读取发现页写入的 `st.session_state.all_jobs`，打通「发现 → 审核 → 生成」全链路。
- **删除死代码**：移除发现页未调用的 `_filter_jobs`。
- **决策通道接入审核页（Phase 1a）**：新增「🤖 运行 AI 决策排序」按钮，调用
  `modules/matcher.decide_single` 对每个岗位判断是否建议投递 + 真实过筛概率 + 理由；
  默认按过筛概率排序（实验显示该通道比纯匹配度更贴近真实录取，AUC≈0.64）。
- **竞争力因子可视化（Phase 1b）**：审核卡片展示公司竞争力档位（顶级厂折扣内置在决策中）。
- **新增校准页 `pages/07_🎯_校准.py`（Phase 1c）**：可视化 `analytics/tune.py` 逻辑——
  用实测 positive/n + Beta 收缩给出 `COMPETITION_FACTOR` 建议值，支持「一键写回」（写入
  `data/competition_overrides.json`，运行时优先于 store.py 默认值），并诊断七维 fit_overall 预测力。
- **store.py 运行时因子覆盖**：新增 `get_competition_factor` / `load_competition_overrides` /
  `save_competition_overrides`，校准无需改源码；`score.py` 已改用 `get_competition_factor`。

### 已知缺口（后续 Phase）
- ✅ 已在 v1.7.0 打通：网页「📈 投递追踪」（JSON）与 analytics SQLite 通过 `tracker._sync_sqlite`
  实时回灌，校准页可直接基于真实投递结果校准。

---

## v1.5.0 — 2026-06-09

### 精简 — 三终端 → 二终端架构
- **合并 `collector_server.py` → `boss_collector_cdp.py`**：端口 9999 统一处理
  - `/status` — 综合状态 + 职位统计
  - `/jobs` — 职位列表
  - `/navigate` — 搜索导航指令
  - `/collect` — 手动提交职位（兼容旧接口）
  - `/clear`、`/export` — 管理功能
- `collector_server.py` 归档为 `.archived`，不再需要独立运行
- Streamlit 页面所有 `localhost:8765` → `localhost:9999`
- 启动方式从 3 终端精简到 **2 终端**

### 版本备份
- 旧版文件备份在 `.backups/v1.4.0/`，包含完整的 3 终端架构
- 还原方式: `cp .backups/v1.4.0/* ../`

---

## v1.4.0 — 2026-06-09

### 新增 — Streamlit ↔ CDP 指令桥接 + 详情被动补全
- **指令桥接**：
  - `boss_collector_cdp.py` 内置 HTTP 指令服务器（端口 9999）
  - Streamlit 中 AI 搜索关键词改为按钮，点击后 POST 到 CDP Chrome 自动导航
  - 彻底解决了「Streamlit 链接→日常 Chrome 打开」和「CDP Chrome→手动输搜索词」之间的割裂
  - 支持 `/navigate`（单次导航）和 `/navigate/multi`（批量导航）
- **详情被动补全（方案 B）**：
  - 列表 API → 采集基础信息（🟡 status: basic）
  - 详情 API → 自动补全 JD（🟢 status: complete）
  - 按 job_url / job_id 精确匹配合并
  - Streamlit 中区分显示：🟢 完整可导入 / 🟡 提示点击补全
- **`collector_server.py` 更新**：新增 `/update` 端点 + `/status` 端点

### 反检测增强（v3）
- 基于 `get_jobs Discussion #250` 的 CDP 时间差检测原理，注入 console.table/performance.now 覆盖
- 反检测从通用 12 项补丁 → 精准针对 Boss 的 CDP 时间差检测

### 文档
- 新增 `docs/使用说明.md`：3 终端启动流程、完整使用教程、常见问题

---

## v1.3.0 — 2026-06-09

### 新增 — Boss直聘 CDP 网络拦截采集器
- **`boss_collector_cdp.py`**：通过 Playwright 连接 Chrome DevTools Protocol
  - 在 CDP 协议层拦截 Boss直聘 API 网络响应
  - 绕过 Content Security Policy，不受页面级 JS 限制
  - 静默运行，用户正常浏览即可自动采集
  - 支持本地缓存（collector_server 未启动时）
  - MD5 去重，避免重复采集同一职位
- **`run_boss_collector.bat`**：一键启动 Chrome + 采集器
- 更新发现职位页面指引，推荐 CDP 方案替代 Chrome Extension

### 技术说明
- 放弃 Chrome Extension 方案（10 轮迭代均因 CSP + 隔离世界限制失败）
- 改用 CDP 层网络拦截（参考 geekgeekrun/get_jobs 同类项目实践）
- Playwright `connect_over_cdp()` 连接用户浏览器，非侵入式采集

### 依赖变更
- 新增 `playwright>=1.50.0`

---

### 新增 — 发现职位模块全面重构
- **AI 职业定位引擎** (`modules/career_advisor.py`)：上传简历后AI自动分析
  - 核心方向推荐
  - 能力可迁移分析（换行业求职的核心功能）
  - 弱项提醒
  - 中英双语搜索关键词
  - 薪资锚定（基于市场数据，支持"不降薪"策略）
- **发现页一体化重写**：AI定位 → 多渠道搜索 → 审核挑选 三步在同一页面完成
- **JobSpy 正式集成**：海外平台搜索已安装并测试通过（LinkedIn/Indeed/Glassdoor）
- **搜索即匹配**：搜索结果实时显示匹配度评分，不再需要单独走匹配流程
- **行业标签系统**：每个岗位标注 🔵核心行业 / 🟢可迁移 / 🟡探索
- **国内平台直达链接**：AI生成Boss直聘/猎聘的搜索链接
- **投递速查卡** (`modules/generator.py`)：生成简历时同步输出
  - 一句话自我介绍
  - 为什么选择这家公司
  - 期望薪资建议
  - 面试薄弱点应对
  - 反问问题建议
  - 独特优势

### 修复
- 海外搜索"点击没反应"问题（缺少 JobSpy 依赖）
- 旧版"公司发现"功能空结果问题

### 技术变更
- 新增依赖：python-jobspy, tls_client, markdownify, regex
- pandas 降级至 2.x（JobSpy 兼容性要求）

---

## v1.1.1 — 2026-06-08
（略，见上方 v1.1.1 记录）

## v1.1.0 — 2026-06-08
（略，见上方 v1.1.0 记录）

## v1.0.0 — 2026-06-08
（略，见上方 v1.0.0 记录）

### 新增
- **中英双语支持**：简历和Cover Letter现在可以同时生成中文和英文两个版本
- **语言设置页面**：在配置页新增「语言设置」标签页，可选择是否生成双语版本和默认语言
- **使用说明书**：添加详细的使用说明页面（📖 使用说明），包含：
  - 5分钟上手指南
  - 功能详解（职位发现、智能匹配、风格自适应等）
  - 运行服务详细说明（命令行启动、常见问题）
  - FAQ 常见问题解答
- **修改记录页面**：在使用说明中内嵌修改记录标签页，方便回溯版本变更
- **Git 版本控制初始化**：项目纳入 Git 管理，所有变更可追溯

### 修复
- **修复连接稳定性问题**：添加 `.streamlit/config.toml` 配置，增加超时时间
- **简历上传稳定性**：改用 `st.status` 显示详细进度，添加错误恢复提示
- **LLM 客户端缓存**：使用 `@st.cache_resource` 缓存 LLM 客户端，避免重复初始化

### 优化
- **侧边栏全中文化**：侧边栏导航和状态指示全部改为中文
- **页面标题中文化**：所有页面标题和导航文字改为中文
- **简历解析**：新增「仅提取文本」按钮，不依赖 AI，速度更快更稳定
- **生成页面**：添加双语开关、进度状态显示、文件下载按钮优化

---

## v1.0.0 — 2026-06-08

### 初始版本

- **项目架构**：Streamlit 多页面应用（5页 + 说明书页）
- **5大核心模块**：
  - 配置页：简历上传、API设置、偏好配置
  - 发现页：海外平台搜索（JobSpy）、AI公司发现、手动JD粘贴
  - 审核页：匹配结果浏览、筛选、挑选
  - 生成页：风格分析、定制简历（HTML）、Cover Letter
  - 追踪页：投递状态管理、统计管道
- **LLM 抽象层**：支持 DeepSeek / OpenAI / Ollama 三种后端
- **简历解析**：PDF/DOCX → 结构化数据，带文件哈希缓存
- **职位发现引擎**：
  - 海外：JobSpy 集成（LinkedIn/Indeed/Glassdoor/Google Jobs）
  - 公司发现：三层扩展策略（职位提取 → AI扩展 → 榜单搜索）
- **智能匹配**：五维度评分（技能/经验/学历/文化/综合）
- **风格分析器**：四种公司文化分类（大厂/创业/外企/咨询）
- **简历生成器**：LLM定制 + HTML渲染，多风格模板
- **投递追踪**：状态管理、统计管道

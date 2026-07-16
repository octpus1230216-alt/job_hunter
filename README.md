# 🎯 job-hunter · 半自动找工作工具

> **Semi-automatic job-hunting toolkit** — discover roles across domestic (Boss直聘/猎聘) and overseas (LinkedIn/Indeed/Glassdoor) platforms, let AI match your résumé to each JD, and generate tailored bilingual résumés — all your data stays **100% local**.
>
> 一个**半自动**的求职辅助工具：帮你完成求职流程中最耗时的部分（发现职位、智能匹配、定制简历），但**最终是否投递由你决定**，工具不会自动代投。

---

## ✨ 功能特性

| 模块 | 说明 |
|------|------|
| 🔍 **职位发现** | 海外平台（LinkedIn / Indeed / Glassdoor，基于 [JobSpy](https://github.com/BericCrous/jobspy)）；国内平台通过浏览器 CDP 采集 Boss直聘 / 猎聘 |
| 🧠 **AI 职业定位** | 上传简历后 AI 自动分析核心方向、可迁移能力、弱项提醒、中英双语搜索词 |
| 🤖 **智能匹配** | 五维度评分（技能/经验/学历/文化/综合），搜索即匹配 |
| 🎨 **定制简历** | 根据目标公司文化风格（大厂 / 创业 / 外企 / 咨询），LLM 定制 + HTML 渲染，支持中英双语 |
| ✉️ **求职信 & 速查卡** | 一键生成 Cover Letter 与面试速查卡（自我介绍 / 为什么选这家 / 期望薪资 / 薄弱点应对） |
| 📊 **投递追踪** | 状态管理、管道看板，全程本地记录 |
| 🔒 **隐私优先** | 简历、配置、采集数据**全部存本地**，不上传任何第三方服务器 |

**AI 后端**：支持 DeepSeek / OpenAI / Ollama 三种，统一抽象层切换。

---

## 🏗️ 架构与工作原理

```
┌─────────────────────────────────────────────────────────┐
│  终端 1：boss_collector_cdp.py  (端口 9999)          │
│   · 启动系统 Chrome（持久化用户目录 ~/.chrome_profile） │
│   · CDP 协议层拦截 Boss直聘 API 响应（绕过 CSP）      │
│   · 统一 HTTP 服务：/status /jobs /navigate /clear     │
└───────────────────────────┬─────────────────────────────┘
                            │ 指令桥接 (HTTP POST)
┌───────────────────────────┴─────────────────────────────┐
│  终端 2：streamlit run app.py  (端口 8501)            │
│   · 5 个页面 + 使用说明页                            │
│   · AI 搜索关键词 → 按钮 → 触发 Chrome 自动跳转采集  │
└─────────────────────────────────────────────────────────┘

数据流向：简历 PDF/DOCX → 解析 → data/resume_parsed.json
         职位采集 → data/ → 匹配 → 生成 → output/（本地 HTML 简历）
```

**为什么用 CDP 层采集？** 浏览器扩展方案因 CSP + 隔离世界限制难以稳定注入；本项目改为在 Chrome DevTools Protocol 层拦截网络响应，不依赖页面 JS，更稳定且能规避反爬检测。详情见 `docs/DESIGN_SPEC.md`。

> ⚠️ **合规提醒**：自动采集招聘网站数据可能违反部分平台的《用户协议》。本项目仅供**个人求职**学习与研究使用，请自行评估风险、控制采集频率，勿用于商业爬取或大规模抓取。

---

## 📂 目录结构

```
job-hunter/
├── app.py                      # Streamlit 主入口
├── boss_collector_cdp.py      # 终端1：Chrome CDP 采集器 + 指令桥接（端口 9999）
├── search_worker.py            # 海外搜索后台 worker
├── daily_digest.py            # 每日职位摘要
├── config.example.yaml        # 配置模板（复制为 config.yaml 后填写）
├── requirements.txt
├── .gitignore                 # 已忽略 config.yaml / data/ / resume / output / .backups
├── pages/                     # 6 个 Streamlit 页面
│   ├── 01_⚙️_配置.py
│   ├── 02_🔍_发现职位.py
│   ├── 03_📊_审核挑选.py
│   ├── 04_✨_生成简历.py
│   ├── 05_📈_投递追踪.py
│   └── 06_📖_使用说明.py
├── modules/                   # 核心模块
│   ├── llm.py                # LLM 抽象层（DeepSeek/OpenAI/Ollama）
│   ├── resume_parser.py      # 简历解析（PDF/DOCX → 结构化）
│   ├── matcher.py            # 智能匹配评分
│   ├── style_analyzer.py     # 公司风格分析
│   ├── generator.py         # 简历/求职信生成
│   ├── careeer_advisor.py    # AI 职业定位
│   ├── tracker.py            # 投递追踪
│   ├── ai_searcher.py       # AI 搜索词生成
│   └── discovery/           # 职位发现（overseas.py / company_finder.py）
├── docs/                     # 设计文档（中文）
│   ├── PRD.md / DESIGN_SPEC.md / BOUNDARY_RULES.md / INTERACTION_STATES.md
├── analytics/                # 复盘分析模块：收集投递结果→分析→对照改简历（详见 analytics/README.md）
└── run_boss_collector.bat   # Windows 一键启动采集器
```

> 📌 仓库中 `legacy/` 目录（原 `chrome_extension/`、`browser_script/`、`collector_server.py.archived`）为**历史方案**（已弃用，CDP 方案取代），保留仅供参考。

---

## 📉 复盘分析模块（`analytics/`）

> 把「投出去的结果」变成「下一轮更准的投递」。收集你在 BOSS / 脉脉 的投递结果（不合适 / 已读不回 / 面试 / offer），分析为什么没回音，对照岗位改简历，并用简历版本 A/B 量化「改简历到底有没有用」。

**两条主线**
- **目标 A · 前瞻（进攻）**：新岗位来了 → 五维评分（对照原简历）→ 对照 JD 改简历 → 导出 LaTeX / ATS 校验。
- **目标 B · 复盘（防守）**：已投结果回流 → 评分 → 交叉分析 + A/B 回复率 → 沉淀下一版该怎么改。

**特点**：零依赖、免 API key 即可跑通（LLM 直连 / 导出提示词贴 WorkBuddy 双通道）；原简历支持 `.doc / .docx / .pdf / .txt` 上传解析。详见 [analytics/README.md](./analytics/README.md) 与 [analytics/docs/](./analytics/docs/)。

---

## 🚀 快速开始

### 1. 环境要求

- Python **3.10+**
- 已安装 **Google Chrome**（国内平台采集依赖系统 Chrome）
- 一个 LLM API Key（DeepSeek / OpenAI，或用本地 Ollama）

### 2. 安装依赖

```bash
git clone https://github.com/octpus1230216-alt/job_hunter.git
cd job-hunter
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium                        # 仅海外采集需要
```

### 3. 配置

```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml，填入你的 LLM API Key 与求职偏好
```

### 4. 启动（两个终端）

**终端 1 — 启动采集器（国内平台需要）**
```bash
python boss_collector_cdp.py
# 脚本会自动拉起 Chrome（持久化登录态在 ~/.chrome_profile/boss）
# 服务运行在 http://localhost:9999
```
> Windows 用户也可直接双击 `run_boss_collector.bat`。

**终端 2 — 启动 Web 界面**
```bash
streamlit run app.py
# 打开 http://localhost:8501
```

### 5. 使用流程

1. **⚙️ 配置**：上传主简历，填写 API Key
2. **🔍 发现职位**：海外自动搜索，或国内走 CDP 采集 Boss直聘 / 猎聘
3. **📊 审核挑选**：筛选你想投的岗位
4. **✨ 生成简历**：一键生成定制版中英双语简历
5. **📈 投递追踪**：标记投递状态，回来更新进度

---

## ⚙️ 配置说明（config.yaml）

| 区块 | 关键字段 | 说明 |
|------|----------|------|
| `llm` | `provider` | `deepseek` / `openai` / `ollama` |
| `llm.deepseek` | `api_key` / `model` | DeepSeek 密钥与模型（如 `deepseek-chat`） |
| `personal` | `name` / `email` / `location` | 你的基本信息（仅本地使用） |
| `preferences` | `target_roles` / `locations` / `salary_min` / `salary_max` | 求职偏好与薪资锚点 |
| `discovery.overseas` | `countries` / `search_terms` / `proxy` | 海外搜索范围，可选代理 |
| `discovery.domestic` | `auto_parse` | 国内采集自动解析 |
| `output` | `bilingual` / `resume_format` | 是否双语、输出格式（HTML） |

> 🔒 `config.yaml`、`data/`、`resume/`、`output/`、`.backups/` 均已被 `.gitignore` 忽略，**不会进入版本库**，请放心填写本地信息。

---

## 📄 许可证

本项目基于 **MIT License** 开源 —— 详见 [LICENSE](./LICENSE)。

> 注：MIT 仅覆盖代码本身。你用本工具生成的简历、采集的职位数据等，其权属与合规责任由使用者自行承担。

---

## 🙏 参考与致谢

- [JobSpy](https://github.com/BericCrous/jobspy) — 海外职位抓取
- [Resume-Matcher](https://github.com/srbhr/Resume-Matcher) — 简历匹配思路
- `get_jobs` Discussion #250 / `geekgeekrun` — CDP 反检测时间差方案参考

---

<p align="center">数据全本地 · AI 辅助 · 半自动求职</p>

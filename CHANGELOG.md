# 修改记录 (Changelog)

本文件汇总 job_hunter 各阶段的修改，最新改动见顶部。

## Phase D–H（本 PR：推荐 + 精投增强 + 导航重组 + 首次引导 + 移动端预留）

### D. 岗位推荐 + 发现重构
- 新增 `modules/recommender.py`：基于世界名企种子库（`modules/seed_companies.json`）生成每日推荐；jobspy / LLM 接入均为可选；行业多样性上限（每行业 ≤3）；按日期播种的随机性（同一天结果稳定、跨天有变化）。
- 新增 `pages/10_🌟_推荐岗位.py`：每日 15 条推荐，含「去精投 / 加入岗位池」、本地即时刷新（需简历 + API）、历史归档查看。
- 新增 `recommender_run.py` 与 `.github/workflows/recommend.yml`：GitHub Actions 每日 08:00（北京时间）自动刷新推荐并回写 `data/recommendations/`。
- 拆分 `pages/04_🔍_发现职位.py` 为三视图：AI 匹配搜索 / 自定义岗位搜索（手动粘贴 JD）/ 🌟 每日推荐岗位（跳转独立页）。

### E. 精投增强
- `pages/02_🎯_精投.py` 新增「同时生成求职信」开关（默认开），可关闭以节省 token。
- 新增 `modules/docx_export.py`：导出 `.docx` 简历与求职信（python-docx，干净排版，不模仿原简历版式）。

### F. 导航与页面重组
- `app.py` 改用 `st.navigation(position="hidden")` + 自定义 `st.page_link` 侧边栏，最终顺序：使用说明 → 配置 → 推荐岗位 → 精投 → 海投 → 追踪 → 校准；发现 / 审核 / 生成降级为「海投·组件页」折叠入口。
- 移除独立「生成简历」页（保留为可复用函数）；更新使用说明欢迎区与海投枢纽页。

### G. 首次运行引导
- 新增 `modules/profile_store.py`：ProfileStore 抽象（Protocol + LocalProfileStore + CloudProfileStore 占位），首次运行在配置页选择存储位置（本地文件夹，云端接口预留）。
- `modules/resume_parser.py` 默认写入 `data/profile`，与配置页 / 自动加载统一路径。

### H. 移动端预留
- 新增 `modules/services.py` 服务层门面，封装 LLM / 简历 / 决策 / 生成 / 投递 / 推荐 / Profile 存储，为后端与移动端做准备。
- 新增 `README.md`：导航表、快速开始、架构、服务层、评分内部化、每日推荐（本地 + Actions）、依赖说明。

## Phase C（PR #12）页面重排
- 新增「精投 / 海投」页，按任务流重排侧边栏。

## Phase B（PR #10 / #11）评分内部化
- 移除全部用户可见数字匹配分，统一改为「AI 决策通道」（过筛概率 + 建议 + 理由）。
- 校准页新增 `internal.calibration_mode` 内部开关，数字诊断默认仅内部开启。

## 热修 PR #13 / #14
- PR #13：修复发现页 Boss 关键词按钮 key 重复导致的 `StreamlitDuplicateElementKey`。
- PR #14：修复校准页 `ModuleNotFoundError: No module named 'modules.store'` 导入路径。

## Phase A（PR #9）健壮性加固
- 简历解析失败回退纯文本、简历与解析结果持久化（`data/profile/`）、LLM 多厂商（含 custom / OpenAI 兼容）。

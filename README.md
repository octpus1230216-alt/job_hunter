# 半自动找工作工具（job_hunter）

一个**半自动**的求职辅助工具：帮你发现岗位、用 AI 做投递决策、按公司风格生成定制简历与求职信，但最终投递由你手动完成（避免封号风险）。

> 所有数据默认存储在**本地**，简历不上传任何第三方。

---

## 导航（按任务流组织）

| 页面 | 作用 |
|------|------|
| 📖 使用说明 | 欢迎 / 快速开始 / 运行服务 / FAQ |
| ⚙️ 配置 | 上传简历、配置 AI、求职偏好、语言；首次运行选择个人信息存放位置 |
| 🌟 推荐岗位 | 每天 08:00 自动推荐 15 个世界名企在招方向（可刷新 / 看历史） |
| 🎯 精投 | 贴一个目标 JD → AI 找不匹配 → 生成定制简历+求职信 → 标记已投 |
| 🌊 海投 | 岗位池批量跑 AI 决策通道 → 勾选认可 → 一次性标记已投 |
| 🔍 发现职位 | 海外平台搜索 / 手动粘贴 JD（海投的岗位池，二级组件页） |
| 📊 审核挑选 | 逐条过审（海投的组件页） |
| ✨ 生成简历 | 批量生成简历/求职信（海投的组件页） |
| 📈 投递追踪 | 记录投递状态，回灌校准库 |
| 🎯 校准 | 内部页（需 `internal.calibration_mode=true`），用真实结果校准 |

> 「发现职位 / 审核挑选 / 生成简历」是「海投」的二级组件页，不在主侧边栏显示，可从「🌊 海投」页进入。

---

## 快速开始

```bash
pip install -r requirements.txt
streamlit run app.py
# 打开 http://localhost:8501
```

1. **⚙️ 配置**：上传简历（PDF/DOCX/TXT）→ 选 AI 提供商（推荐 DeepSeek）→ 填 Key → 设偏好。
2. **🌟 推荐岗位** 或 **🔍 发现职位**：取一批岗位。
3. **🎯 精投**（深耕单家）或 **🌊 海投**（广撒网）。
4. 去平台投递，回 **📈 投递追踪** 标记进度。

---

## 架构

```
app.py                      # 框架：st.navigation(隐藏) + 自定义侧边栏
pages/                      # 各任务页（均由 app.py 的导航驱动）
modules/
  llm.py                    # 多厂商 LLM 客户端（deepseek/openai/ollama/custom）
  resume_parser.py          # 简历解析（缓存到 data/profile）
  matcher.py                # AI 决策通道（建议投 + 过筛概率 + 理由）
  style_analyzer.py         # 公司风格分析
  generator.py              # 定制简历 + 求职信 + 速查卡（支持 .docx 导出）
  tracker.py                # 投递追踪（JSON 主存储 + 回灌 analytics SQLite）
  recommender.py            # 每日岗位推荐引擎
  profile_store.py          # 个人信息存储抽象（本地 / 云端预留）
  docx_export.py            # 简历/求职信导出 Word
  services.py               # 服务层门面（页面只依赖它，便于后端化/移动端化）
analytics/                  # 校准与统计（SQLite）
.github/workflows/
  recommend.yml             # 每日 08:00(北京) 生成并提交 latest.json
```

### 服务层与移动端预留（意见 H）

页面统一通过 `modules.services` 调用能力，不直接 import 底层模块。
这道边界让后续把逻辑搬到独立后端、提供移动端 API 时，页面改动最小。
「移动端友好」本期做到：**导航可解耦、存储可切换（ProfileStore）、AI 决策与生成都是无状态函数**；
真正的移动 App 是下一步，接口契约已就位。

### 评分内部化（意见 B）

普通用户**不看到任何数字匹配分**，只看到 AI 决策结论（过筛概率 + 建议 + 理由）。
数字分仅保留在内部「🎯 校准」页，用于基于真实投递结果做模型校准。

---

## 每日推荐（意见 D-8）

- **本地**：`python recommender_run.py` 直接生成 `data/recommendations/latest.json`。
- **云端**：GitHub Actions 每天 08:00（北京时间）自动跑 `recommender_run.py` 并提交 `latest.json`，
  App 的「🌟 推荐岗位」页直接读取。需在仓库 **Settings → Secrets** 配置 `DEEPSEEK_API_KEY`（可选，缺失也能生成）。
- 选取原则：世界知名企业 + 最新挂出（jobspy，可选）+ 与简历部分相关 + 行业不限 + 地区可选（读 `preferences.locations`）。

---

## 依赖

```bash
pip install streamlit pyyaml python-docx   # 核心：python-docx 用于 Word 导出
pip install jobspy                         # 可选：抓取最新岗位（缺失不影响运行）
```
> `requirements.txt` 已包含上述依赖；jobspy 为可选，安装失败不影响其它功能。

---

## 桌面安装包（Windows）

把整套应用冻结成**单机可执行程序**：双击启动器即在本地起一个 Streamlit 服务并自动打开浏览器，所有个人数据（简历 / 画像 / 投递记录）默认只存在本机安装目录，不出本机。

### 两种获取方式

1. **GitHub Actions 自动产出（推荐，零本地环境）**
   - 仓库 **Actions → Build Desktop Installer → Run workflow**（手动触发）；
   - 或给仓库打 `v*` 标签（如 `v1.0.0`），自动构建并作为 Release 附件发布。
   - 产物：`job_hunter-setup.exe`（在 Artifacts / Releases 下载）。

2. **本地一键构建**（需本机有 Python 3.11 + [NSIS](https://nsis.sourceforge.io/Download)）
   ```bat
   packaging\build.bat
   ```
   产物同样在 `dist\job_hunter-setup.exe`。

### 原理与边界

- `desktop/launcher.py`：冻结后的入口，负责拷贝默认配置、找空闲端口、以 headless 方式 `streamlit run app.py`、打开浏览器、并提供"关闭即退出"的小窗口。
- `packaging/desktop.spec`：PyInstaller 打包配置。整套应用（`app.py` / `pages/` / `modules/` / `analytics/` / `.streamlit/`）作为**数据文件**随包分发、运行时从同目录加载，因此冻结时无需解析可选重型依赖。
- **不包含** `jobspy` / `playwright` / `tls_client` / `ollama`（它们均为函数内懒加载的可选功能，缺失时仅对应的高级抓取 / 本地模型不可用，核心功能不受影响）。
- 安装目录默认 `%LOCALAPPDATA%\jobhunter`，用户数据在其中的 `data\`。卸载会连同 `data\` 一起删除，**重装前请先备份该目录**。

### 隐私说明

- 安装包**不含任何密钥**：随包分发的是 `config.example.yaml`（无 key），首次运行自动生成 `config.yaml`；你的 DeepSeek Key 请在「⚙️ 配置」页填写（或自行编辑 `config.yaml`）。
- 本地数据全程不出本机；仅当启用 AI 功能（推荐 / 求职信）时，简历文本会发往 DeepSeek。

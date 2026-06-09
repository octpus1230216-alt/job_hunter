# 设计规范 — 半自动找工作工具

## 1. 信息架构

### 1.1 页面结构
```
首页 (app.py)
├── ⚙️ 配置 (01)
│   ├── 简历上传与解析
│   ├── API 设置 (DeepSeek/OpenAI/Ollama)
│   ├── 求职偏好
│   └── 语言设置
├── 🔍 发现职位 (02)
│   ├── 后台任务面板
│   ├── 每日精选入口
│   ├── Step 1: AI 职业定位
│   ├── Step 2: 搜索标签页
│   │   ├── 🌍 海外平台搜索
│   │   ├── 🏠 国内平台直达搜索
│   │   ├── 🤖 AI 全网搜索
│   │   └── 📋 手动粘贴 JD
│   └── Step 3: 审核挑选
├── 📊 审核挑选 (03) — 已合并至发现页，保留为快捷入口
├── ✨ 生成简历 (04)
│   ├── 岗位列表
│   ├── 生成按钮（单个/批量）
│   ├── 结果预览
│   │   ├── 简历预览
│   │   ├── 求职信预览
│   │   └── 投递速查卡
│   └── 下载按钮
├── 📈 投递追踪 (05)
│   ├── 统计概览
│   ├── 管道看板
│   └── 投递记录管理
└── 📖 使用说明 (06)
    ├── 快速开始
    ├── 功能详解
    ├── 运行服务
    ├── 常见问题
    └── 修改记录
```

### 1.2 导航规范
- 使用 Streamlit 多页面原生导航（侧边栏自动生成）
- 页面文件名格式：`{序号}_{图标}_{中文名}.py`
- 不隐藏原生导航栏
- 侧边栏底部显示运行状态指示器（简历状态、AI状态、待审核数）

---

## 2. 视觉设计

### 2.1 配色
| 用途 | 颜色 | HEX |
|------|------|-----|
| 主色 | 蓝色 | #1890ff |
| 成功/核心行业 | 蓝色系 | #E6F1FB / #378ADD |
| 可迁移 | 绿色系 | #E1F5EE / #1D9E75 |
| 探索 | 紫色系 | #EEEDFE / #7F77DD |
| 生成/温暖 | 珊瑚色 | #FAECE7 / #D85A30 |
| 警告 | 橙色 | #EF9F27 |
| 错误/危险 | 红色 | #E24B4A |
| 中性 | 灰色系 | #F1EFE8 → #2C2C2A |

### 2.2 图标系统
| 概念 | 图标 |
|------|------|
| 核心行业 | 🔵 |
| 可迁移行业 | 🟢 |
| 探索方向 | 🟡 |
| 弱项提醒-高 | 🔴 |
| 弱项提醒-中 | 🟡 |
| 弱项提醒-低 | 🟢 |
| 运行中 | 🔄 |
| 已完成 | ✅ |
| 已取消 | ⏹ |
| 错误 | ❌ |
| 待处理 | ⏳ |

### 2.3 组件规范
- **指标卡片**：`st.metric()`，浅色背景，圆角 12px
- **操作按钮**：主操作 `type="primary"`，次要操作默认样式，宽度 `use_container_width=True`
- **状态提示**：`st.status()` 显示多步骤进度，`st.spinner()` 显示简短等待
- **折叠面板**：`st.expander()` 用于可选详情的展示
- **选项卡**：`st.tabs()` 用于同层级功能切换
- **表格**：`st.dataframe()` 用于列表数据

---

## 3. 交互设计

### 3.1 核心工作流
```
配置简历 → AI职业定位 → 选择搜索渠道 → 发现职位 → 审核挑选 → 生成简历 → 投递追踪
```

### 3.2 状态流转
- **简历状态**：未上传 → 已上传未解析 → 已解析
- **AI状态**：未配置 → 已配置未测试 → 已就绪
- **任务状态**：pending → running → completed/cancelled/error
- **投递状态**：已收藏 → 已投递 → 简历筛选 → 一面 → 二面 → 三面 → 终面 → Offer → 已接受/已拒绝

### 3.3 关键交互规则
1. **操作前置条件**：没有简历 → 定位/搜索/生成不可用，提示先去配置页
2. **长操作处理**：API 调用超30秒的操作使用 `st.status()` 显示分步进度
3. **搜索即匹配**：搜索结果直接带匹配度，不再单独走匹配流程
4. **下载按钮持久化**：生成结果存 session_state，下载按钮在按钮回调外部渲染
5. **结果去重**：基于 `job_url` 去重，避免重复导入
6. **空状态提示**：每个列表/区域在无数据时显示引导性提示

---

## 4. 数据设计

### 4.1 存储结构
```
data/
├── resume_parsed.json          # 简历解析结果
├── career_report_*.json        # AI职业定位报告
├── jobs/
│   └── overseas_jobs_*.json    # 海外搜索结果
├── companies/
│   └── companies_*.json        # 公司发现结果
├── applications/
│   └── applications.json       # 投递记录
├── search_tasks/               # 后台搜索任务
│   ├── *_task.json             # 任务定义
│   ├── *_progress.json         # 任务进度
│   ├── *_results.json          # 任务结果
│   └── *_cancel.json           # 取消标记
├── domestic_jobs/              # 浏览器采集数据
│   └── current_session.json    # 当前会话
└── daily_digests/              # 每日精选
    └── digest_2026-06-09.json  # 按日期存储
```

### 4.2 简历数据结构
```json
{
  "name": "string",
  "email": "string",
  "phone": "string",
  "location": "string",
  "linkedin": "string",
  "github": "string",
  "summary": "string",
  "skills": {
    "languages": ["string"],
    "frameworks": ["string"],
    "tools": ["string"],
    "soft_skills": ["string"],
    "languages_spoken": ["string"]
  },
  "experience": [{
    "company": "string",
    "title": "string",
    "start_date": "string",
    "end_date": "string",
    "location": "string",
    "bullets": ["string"]
  }],
  "projects": [{
    "name": "string",
    "description": "string",
    "tech_stack": ["string"],
    "highlights": ["string"]
  }],
  "education": [{
    "school": "string",
    "degree": "string",
    "major": "string"
  }],
  "total_years_experience": "string"
}
```

### 4.3 职位数据结构
```json
{
  "company": "string",
  "title": "string",
  "location": "string",
  "description": "string",
  "job_url": "string",
  "salary": "string",
  "source_platform": "indeed|linkedin|ai_search|boss_auto|manual",
  "source_country": "string",
  "discovered_at": "ISO8601",
  "_match": {
    "overall_score": 0,
    "strengths": ["string"],
    "weaknesses": ["string"],
    "recommendation": "string"
  },
  "_industry_tag": "核心行业|可迁移|探索"
}
```

---

## 5. 技术架构

### 5.1 技术栈
| 层级 | 技术 | 说明 |
|------|------|------|
| 前端框架 | Streamlit | Python Web 框架，多页面 |
| 后端语言 | Python 3.13 | 全栈 Python |
| AI 后端 | DeepSeek / OpenAI / Ollama | 三选一，支持切换 |
| 海外搜索 | python-jobspy | Indeed/LinkedIn 集成 |
| 浏览器采集 | Tampermonkey + Flask | 国内平台数据收集 |
| 数据存储 | JSON / YAML | 本地文件存储 |
| 版本控制 | Git | 本地仓库 |

### 5.2 模块架构
```
modules/
├── llm.py              # LLM 抽象层
├── resume_parser.py    # 简历解析
├── career_advisor.py   # AI 职业定位
├── matcher.py          # 智能匹配
├── style_analyzer.py   # 公司风格分析
├── generator.py        # 简历生成
├── tracker.py          # 投递追踪
├── ai_searcher.py      # AI 全网搜索
└── discovery/
    ├── overseas.py     # 海外搜索
    └── company_finder.py  # 公司发现
```

### 5.3 独立进程
| 进程 | 用途 | 通信方式 |
|------|------|---------|
| collector_server.py | 浏览器采集接收器 | HTTP (localhost:8765) |
| Chrome 扩展 | Boss直聘/猎聘自动翻页批量抓取 | HTTP → collector_server |
| search_worker.py | 后台搜索 | 文件系统 (JSON) |
| daily_digest.py | 每日精选 | 文件系统 (JSON) |

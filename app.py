"""
半自动找工作工具 — 主入口
Streamlit 多页面应用

启动方式：
    cd job-hunter
    streamlit run app.py
"""

import streamlit as st

st.set_page_config(
    page_title="半自动找工作工具",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 隐藏 Streamlit 默认UI元素
hide_streamlit_style = """
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {display: none;}
    [data-testid="stSidebarNav"] {display: none;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ============================================================
# 初始化 session state
# ============================================================
if "resume_parsed" not in st.session_state:
    st.session_state.resume_parsed = None
if "llm_client" not in st.session_state:
    st.session_state.llm_client = None
if "jobs_found" not in st.session_state:
    st.session_state.jobs_found = []
if "match_results" not in st.session_state:
    st.session_state.match_results = []
if "selected_jobs" not in st.session_state:
    st.session_state.selected_jobs = []
if "config" not in st.session_state:
    import yaml
    from pathlib import Path
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        st.session_state.config = yaml.safe_load(f)


# ============================================================
# 缓存 LLM 客户端（避免重复初始化，提升稳定性）
# ============================================================
@st.cache_resource
def get_llm_client():
    """缓存LLM客户端，避免每次rerun都重建连接"""
    try:
        from modules.llm import LLMClient
        return LLMClient()
    except Exception:
        return None


# ============================================================
# 侧边栏 — 中文导航
# ============================================================
with st.sidebar:
    st.title("🎯 半自动找工作工具")
    st.markdown("---")

    # 导航链接
    st.subheader("📋 工作流程")

    pages = {
        "🏠 首页": "app",
        "⚙️ 配置": "01_config",
        "🔍 发现职位": "02_discovery",
        "📊 审核挑选": "03_review",
        "✨ 生成简历": "04_generator",
        "📈 投递追踪": "05_tracker",
        "📖 使用说明": "06_manual",
    }

    # 简单文字导航（Streamlit多页面自动处理）
    st.markdown("""
    **操作步骤：**
    1. ⚙️ **配置** — 上传简历、设置API
    2. 🔍 **发现职位** — 搜索职位、发现公司
    3. 📊 **审核挑选** — 匹配筛选、挑选岗位
    4. ✨ **生成简历** — 定制简历和求职信
    5. 📈 **投递追踪** — 投递进度管理

    📖 **使用说明** — 详细文档和常见问题
    """)

    st.markdown("---")

    # 状态指示
    st.subheader("📌 当前状态")

    if st.session_state.get("resume_parsed"):
        st.success("✅ 简历已加载")
    else:
        st.warning("⚠️ 请先上传简历")

    # 尝试初始化LLM
    llm = get_llm_client()
    if llm is not None:
        st.session_state.llm_client = llm
        st.success("✅ AI已就绪")
    else:
        st.warning("⚠️ 请先配置API")

    if st.session_state.get("jobs_found"):
        count = len(st.session_state.jobs_found)
        st.info(f"📌 {count} 个待审核岗位")
    else:
        st.info("📌 暂无待审核岗位")

    st.markdown("---")
    st.caption("数据全部存储在本地，不上传任何服务器")


# ============================================================
# 欢迎页
# ============================================================
st.title("🎯 半自动找工作工具")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(label="工作流程", value="5 步")
with col2:
    st.metric(label="数据存储", value="全本地")
with col3:
    st.metric(label="AI后端", value="3 种")
with col4:
    st.metric(label="语言支持", value="中英双语")

st.markdown("---")

st.markdown("""
### 👋 欢迎使用

这是一个**半自动**的求职辅助工具，帮你高效完成找工作流程中最耗时的部分。

**核心功能：**

| 功能 | 说明 |
|------|------|
| 🔍 **职位发现** | 从LinkedIn、Indeed等海外平台自动搜索，AI发现更多公司 |
| 🧠 **智能匹配** | AI分析你的简历和每个JD的匹配度，多维度评分 |
| ✅ **人工审核** | 你来最终决定投哪些，工具不会自动投递 |
| 🎨 **定制简历** | 根据目标公司风格，自动生成定制中英文简历和求职信 |
| 📈 **追踪进度** | 记录投递状态，管道看板一目了然 |

### 🚀 快速开始

1. 进入左侧 **⚙️ 配置** 页面，上传主简历，设置API Key
2. 进入 **🔍 发现职位** 页面，开始搜索或粘贴JD
3. 在 **📊 审核挑选** 页面筛选你想投的岗位
4. 在 **✨ 生成简历** 页面一键生成定制版中英文简历
5. 拿着简历去平台投递，回来在 **📈 投递追踪** 页面标记进度

> 💡 **所有数据都存在你本地电脑上**，简历不会上传到任何第三方。
> 
> 📖 遇到问题？查看左侧的 **使用说明** 页面。
""")

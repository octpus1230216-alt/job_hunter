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

# 全局样式（只隐藏 Streamlit 默认的菜单和页脚，
# 保留侧边栏导航）
hide_streamlit_style = """
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {display: none;}
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
# 缓存的 LLM 客户端（唯一的定义，其他页面通过 session_state 访问）
# ============================================================
@st.cache_resource
def get_or_init_llm():
    """缓存 LLM 客户端，避免每次 rerun 都重建连接"""
    try:
        from modules.llm import LLMClient
        return LLMClient()
    except Exception:
        return None


# ============================================================
# 侧边栏 — 状态指示
# ============================================================
with st.sidebar:
    st.markdown("---")
    st.subheader("📌 运行状态")

    if st.session_state.get("resume_parsed"):
        st.success("✅ 简历已加载")
    else:
        st.warning("⚠️ 请先上传简历")

    # 自动初始化 LLM
    if st.session_state.get("llm_client") is None:
        llm = get_or_init_llm()
        if llm is not None:
            st.session_state.llm_client = llm

    if st.session_state.get("llm_client"):
        st.success("✅ AI 已就绪")
    else:
        st.warning("⚠️ 请先配置 API")

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

1. 点击左侧 **⚙️ 配置**，上传主简历，设置 API Key
2. 点击 **🔍 发现职位**，搜索或粘贴 JD
3. 在 **📊 审核挑选** 筛选你想投的岗位
4. 在 **✨ 生成简历** 一键生成定制版中英文简历
5. 拿着简历去平台投递，回来在 **📈 投递追踪** 标记进度

> 💡 **所有数据都存在你本地电脑上**，简历不会上传到任何第三方。
> 📖 遇到问题？查看左侧的 **📖 使用说明** 页面。
""")

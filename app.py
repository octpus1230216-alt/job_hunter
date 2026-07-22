"""
半自动找工作工具 — 主入口（框架）
Streamlit 多页面应用，使用 st.navigation 控制导航（意见 F：按任务流重组）。

导航策略：
- 主流程页（使用说明 / 配置 / 推荐岗位 / 精投 / 海投 / 投递追踪 / 校准）显示在自定义侧边栏
- 「发现职位 / 审核挑选 / 生成简历」作为「海投」的二级组件页，不在主侧边栏显示，
  通过海投页的入口或这里折叠区的 page_link 进入（意见 F-7）
- 所有页面都注册到 st.navigation（position=hidden），保证 st.switch_page / st.page_link 可用
"""

import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="半自动找工作工具",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 全局样式：隐藏默认菜单/页脚，保留自定义侧边栏
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
    import json
    st.session_state.resume_parsed = None
    # 优先从用户选择的个人信息目录加载（意见 G-6）
    try:
        from modules.profile_store import get_profile_store
        _parsed = get_profile_store().load_parsed()
        if _parsed:
            st.session_state.resume_parsed = _parsed
    except Exception:
        pass
    # 兼容旧路径 data/resume_parsed.json
    if st.session_state.resume_parsed is None:
        _old = Path(__file__).parent / "data" / "resume_parsed.json"
        if _old.exists():
            try:
                with open(_old, "r", encoding="utf-8") as f:
                    st.session_state.resume_parsed = json.load(f)
            except Exception:
                pass

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
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        _cfg = yaml.safe_load(f) or {}
    _cfg.setdefault("internal", {})
    _cfg["internal"].setdefault("calibration_mode", False)
    st.session_state.config = _cfg


# ============================================================
# 缓存的 LLM 客户端
# ============================================================
@st.cache_resource
def get_or_init_llm():
    try:
        from modules.llm import LLMClient
        return LLMClient()
    except Exception:
        return None


# ============================================================
# 自定义侧边栏导航（主流程 + 海投组件）
# ============================================================
with st.sidebar:
    st.markdown("## 🎯 半自动找工作")

    # 主流程
    st.page_link("pages/08_📖_使用说明.py", label="📖 使用说明", use_container_width=True)
    st.page_link("pages/01_⚙️_配置.py", label="⚙️ 配置", use_container_width=True)
    st.page_link("pages/10_🌟_推荐岗位.py", label="🌟 推荐岗位", use_container_width=True)
    st.page_link("pages/02_🎯_精投.py", label="🎯 精投", use_container_width=True)
    st.page_link("pages/03_🌊_海投.py", label="🌊 海投", use_container_width=True)
    st.page_link("pages/07_📈_投递追踪.py", label="📈 投递追踪", use_container_width=True)
    st.page_link("pages/09_🎯_校准.py", label="🎯 校准（内部）", use_container_width=True)

    # 海投的二级组件页（不在主流程显示，意见 F-7）
    with st.expander("🔧 海投 · 组件页"):
        st.caption("以下为「海投」流程的组件，从「🌊 海投」页进入更顺。")
        st.page_link("pages/04_🔍_发现职位.py", label="🔍 发现职位", use_container_width=True)
        st.page_link("pages/05_📊_审核挑选.py", label="📊 审核挑选", use_container_width=True)
        st.page_link("pages/06_✨_生成简历.py", label="✨ 生成简历", use_container_width=True)

    st.divider()

    # 运行状态
    st.subheader("📌 运行状态")
    if st.session_state.get("resume_parsed"):
        st.success("✅ 简历已加载")
    else:
        st.warning("⚠️ 请先上传简历")
    if st.session_state.get("llm_client") is None:
        _llm = get_or_init_llm()
        if _llm is not None:
            st.session_state.llm_client = _llm
    if st.session_state.get("llm_client"):
        st.success("✅ AI 已就绪")
    else:
        st.warning("⚠️ 请先配置 API")
    if st.session_state.get("all_jobs"):
        st.info(f"📌 {len(st.session_state.all_jobs)} 个待审核岗位")
    else:
        st.info("📌 暂无待审核岗位")
    st.divider()
    st.caption("数据全部存储在本地，不上传任何服务器")


# ============================================================
# 注册全部页面（position=hidden），由自定义侧边栏驱动导航
# ============================================================
pg = st.navigation([
    "pages/08_📖_使用说明.py",
    "pages/01_⚙️_配置.py",
    "pages/10_🌟_推荐岗位.py",
    "pages/02_🎯_精投.py",
    "pages/03_🌊_海投.py",
    "pages/07_📈_投递追踪.py",
    "pages/09_🎯_校准.py",
    # 海投组件页（注册但不显示在侧边栏主流程）
    "pages/04_🔍_发现职位.py",
    "pages/05_📊_审核挑选.py",
    "pages/06_✨_生成简历.py",
], position="hidden")

pg.run()

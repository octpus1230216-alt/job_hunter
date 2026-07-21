"""
配置页面 — 上传简历、设置API、偏好配置、语言设置
"""

import copy
import streamlit as st
import yaml
from pathlib import Path


def save_config(config: dict):
    """保存配置到文件并同步到 session state"""
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
    st.session_state.config = config


from modules.auth import require_auth
require_auth()

st.title("⚙️ 配置")

tab1, tab2, tab3, tab4 = st.tabs(["📄 简历", "🤖 API 设置", "🎯 求职偏好", "🌐 语言设置"])

# ============================================================
# Tab 1: 简历上传
# ============================================================
with tab1:
    st.subheader("上传主简历")
    st.caption("上传你的主简历（PDF/DOCX/TXT），AI会自动解析并用于后续匹配和定制")

    # 固定个人信息文件夹：简历与解析结果持久化到 data/profile/，刷新后自动加载（缺失也不影响网站启动）
    profile_dir = Path(__file__).parent.parent / "data" / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    _parsed_cache = profile_dir / "resume_parsed.json"
    if not st.session_state.get("resume_parsed") and _parsed_cache.exists():
        try:
            import json
            st.session_state.resume_parsed = json.loads(_parsed_cache.read_text(encoding="utf-8"))
            _rf = list(profile_dir.glob("resume.*"))
            st.session_state.resume_path = str(_rf[0]) if _rf else ""
            st.info("已自动加载本地简历（data/profile/），如需更换可重新上传")
        except Exception:
            pass

    uploaded_file = st.file_uploader(
        "支持 PDF / DOCX / TXT 格式",
        type=["pdf", "docx", "txt"],
    )

    if uploaded_file:
        resume_path = profile_dir / uploaded_file.name

        with open(resume_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        st.success(f"文件已保存: {resume_path.name}（位于 data/profile/，下次自动加载）")

        col1, col2 = st.columns(2)
        with col1:
            parse_clicked = st.button("🔍 智能解析简历", use_container_width=True,
                                       help="用AI提取结构化信息（技能/经验/学历等）")
        with col2:
            quick_parse = st.button("📋 仅提取文本", use_container_width=True,
                                     help="不做AI分析，仅提取纯文本，速度快")

        if parse_clicked or quick_parse:
            use_llm = parse_clicked

            with st.status("正在处理简历...", expanded=True) as status:
                try:
                    from modules.resume_parser import ResumeParser

                    st.write("📖 正在读取文件...")
                    parser = ResumeParser()

                    llm = None
                    if use_llm:
                        st.write("🤖 正在连接AI...")
                        llm = st.session_state.get("llm_client")
                        if llm is None:
                            from modules.llm import LLMClient
                            try:
                                llm = LLMClient()
                                st.session_state.llm_client = llm
                            except Exception:
                                status.update(label="AI未配置，改用纯文本提取", state="running")
                                use_llm = False

                    st.write("🔍 正在解析...")
                    result = parser.parse(str(resume_path), llm)
                    st.session_state.resume_parsed = result
                    st.session_state.resume_path = str(resume_path)
                    # 解析结果已自动缓存到 data/profile/resume_parsed.json（由 ResumeParser 写入），下次打开自动加载
                    status.update(label="解析完成！", state="complete")
                    st.success("简历解析成功！")
                    st.rerun()

                except Exception as e:
                    status.update(label="解析失败", state="error")
                    st.error(f"解析失败: {str(e)[:200]}")
                    if use_llm:
                        st.info("💡 提示：AI解析失败时，试试「仅提取文本」按钮，速度快且更稳定")

    if st.session_state.get("resume_parsed"):
        resume = st.session_state.resume_parsed
        st.markdown("---")
        st.subheader("📋 简历预览")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**姓名:** {resume.get('name', 'N/A')}")
            st.markdown(f"**邮箱:** {resume.get('email', 'N/A')}")
            st.markdown(f"**地点:** {resume.get('location', 'N/A')}")
        with col2:
            st.markdown(f"**LinkedIn:** {resume.get('linkedin', 'N/A')}")
            st.markdown(f"**GitHub:** {resume.get('github', 'N/A')}")
            st.markdown(f"**总经验:** {resume.get('total_years_experience', 'N/A')} 年")

        with st.expander("查看技能"):
            skills = resume.get("skills", {})
            for cat, items in skills.items():
                if items:
                    st.markdown(f"**{cat}:** {', '.join(items)}")

        with st.expander("查看工作经历"):
            for exp in resume.get("experience", []):
                st.markdown(f"**{exp.get('title')}** @ {exp.get('company')}")
                st.markdown(f"_{exp.get('start_date')} - {exp.get('end_date')}_")
                for bullet in exp.get("bullets", []):
                    st.markdown(f"- {bullet}")
                st.markdown("---")

# ============================================================
# Tab 2: API 设置
# ============================================================
with tab2:
    st.subheader("AI API 配置")
    st.caption("选择一个AI后端。推荐DeepSeek（国产、便宜、效果好）")

    config = st.session_state.get("config", {})

    provider = st.selectbox(
        "选择 AI 提供商",
        ["deepseek", "openai", "ollama", "custom"],
        format_func=lambda x: {"deepseek": "DeepSeek（推荐）", "openai": "OpenAI", "ollama": "Ollama（本地免费）", "custom": "自定义（OpenAI 兼容）"}[x],
    )

    if provider == "deepseek":
        api_key = st.text_input(
            "DeepSeek API Key",
            type="password",
            value=config.get("llm", {}).get("deepseek", {}).get("api_key", ""),
            help="在 https://platform.deepseek.com 获取"
        )
        model = st.text_input("模型名称", value="deepseek-chat")
        base_url = st.text_input("接口地址", value="https://api.deepseek.com")

        if st.button("💾 保存并测试 DeepSeek", use_container_width=True):
            if not api_key:
                st.error("请输入 API Key")
            else:
                config.setdefault("llm", {})
                config["llm"]["provider"] = "deepseek"
                config["llm"]["deepseek"] = {"api_key": api_key, "model": model, "base_url": base_url}
                save_config(config)
                # 清除缓存并重新初始化
                st.cache_resource.clear()
                try:
                    from modules.llm import LLMClient
                    llm = LLMClient()
                    st.session_state.llm_client = llm
                    resp = llm.chat("你是一个助手。", "回复'连接成功'")
                    st.success(f"✅ 连接成功: {resp[:80]}")
                except Exception as e:
                    st.warning(f"配置已保存，但测试连接失败: {str(e)[:150]}")

    elif provider == "openai":
        api_key = st.text_input(
            "OpenAI API Key",
            type="password",
            value=config.get("llm", {}).get("openai", {}).get("api_key", ""),
        )
        model = st.text_input("模型名称", value="gpt-4o")
        base_url = st.text_input("接口地址", value="https://api.openai.com/v1")

        if st.button("💾 保存并测试 OpenAI", use_container_width=True):
            if not api_key:
                st.error("请输入 API Key")
            else:
                config.setdefault("llm", {})
                config["llm"]["provider"] = "openai"
                config["llm"]["openai"] = {"api_key": api_key, "model": model, "base_url": base_url}
                save_config(config)
                st.cache_resource.clear()
                try:
                    from modules.llm import LLMClient
                    llm = LLMClient()
                    st.session_state.llm_client = llm
                    resp = llm.chat("你是一个助手。", "回复'连接成功'")
                    st.success(f"✅ 连接成功: {resp[:80]}")
                except Exception as e:
                    st.warning(f"配置已保存，但测试连接失败: {str(e)[:150]}")

    elif provider == "ollama":
        model = st.text_input("Ollama 模型", value="qwen2.5:14b")
        base_url = st.text_input("Ollama 服务地址", value="http://localhost:11434")
        st.info("确保已安装 Ollama: https://ollama.com")
        st.caption(f"下载模型: `ollama pull {model}`")

        if st.button("💾 保存并测试 Ollama", use_container_width=True):
            config.setdefault("llm", {})
            config["llm"]["provider"] = "ollama"
            config["llm"]["ollama"] = {"model": model, "base_url": base_url}
            save_config(config)
            st.cache_resource.clear()
            try:
                from modules.llm import LLMClient
                llm = LLMClient()
                st.session_state.llm_client = llm
                resp = llm.chat("你是一个助手。", "回复'连接成功'")
                st.success(f"✅ 连接成功: {resp[:80]}")
            except Exception as e:
                st.warning(f"配置已保存，但测试连接失败: {str(e)[:150]}")

    elif provider == "custom":
        st.caption("任何兼容 OpenAI /v1/chat/completions 的端点：通义千问、智谱 GLM、Kimi、Claude 代理等")
        api_key = st.text_input(
            "API Key",
            type="password",
            value=config.get("llm", {}).get("custom", {}).get("api_key", ""),
        )
        base_url = st.text_input("接口地址 (OpenAI 兼容)", value=config.get("llm", {}).get("custom", {}).get("base_url", "https://api.openai.com/v1"))
        model = st.text_input("模型名称", value=config.get("llm", {}).get("custom", {}).get("model", "gpt-4o"))

        if st.button("💾 保存并测试自定义", use_container_width=True):
            if not api_key:
                st.error("请输入 API Key")
            else:
                config.setdefault("llm", {})
                config["llm"]["provider"] = "custom"
                config["llm"]["custom"] = {"api_key": api_key, "model": model, "base_url": base_url}
                save_config(config)
                st.cache_resource.clear()
                try:
                    from modules.llm import LLMClient
                    llm = LLMClient()
                    st.session_state.llm_client = llm
                    resp = llm.chat("你是一个助手。", "回复'连接成功'")
                    st.success(f"✅ 连接成功: {resp[:80]}")
                except Exception as e:
                    st.warning(f"配置已保存，但测试连接失败: {str(e)[:150]}")

# ============================================================
# Tab 3: 求职偏好
# ============================================================
with tab3:
    st.subheader("求职偏好设置")

    # 从 session state 深拷贝 config 用于编辑，避免原地修改
    config = copy.deepcopy(st.session_state.get("config", {}))
    prefs = config.get("preferences", {})
    reqs = config.get("company_requirements", {})

    target_roles = st.text_input(
        "目标职位（逗号分隔）",
        value=", ".join(prefs.get("target_roles", [])),
        help="例如：软件工程师, 后端开发, 全栈工程师"
    )

    industries = st.text_input(
        "意向行业（逗号分隔）",
        value=", ".join(prefs.get("industries", [])),
        help="例如：互联网, 人工智能, 金融科技"
    )

    locations = st.text_input(
        "工作地点（逗号分隔）",
        value=", ".join(prefs.get("locations", [])),
        help="例如：远程, 北京, 上海, US, Singapore"
    )

    col1, col2 = st.columns(2)
    with col1:
        salary_min = st.number_input("最低薪资（年/¥）", value=prefs.get("salary_min", 0), step=50000)
    with col2:
        salary_max = st.number_input("最高薪资（年/¥）", value=prefs.get("salary_max", 0), step=50000)

    st.markdown("---")
    st.subheader("公司要求")

    blacklist = st.text_area(
        "公司黑名单（一行一个）",
        value="\n".join(reqs.get("blacklist", [])),
        height=100,
        help="绝对不会去的公司"
    )

    whitelist = st.text_area(
        "公司白名单（一行一个）",
        value="\n".join(reqs.get("whitelist", [])),
        height=100,
        help="优先考虑的公司"
    )

    col3, col4 = st.columns(2)
    with col3:
        accept_startups = st.checkbox("接受创业公司", value=reqs.get("accept_startups", True))
    with col4:
        accept_outsourcing = st.checkbox("接受外包/派遣", value=reqs.get("accept_outsourcing", False))

    if st.button("💾 保存偏好设置", use_container_width=True, type="primary"):
        # 只在按钮点击时才更新 config
        prefs["target_roles"] = [r.strip() for r in target_roles.split(",") if r.strip()]
        prefs["industries"] = [i.strip() for i in industries.split(",") if i.strip()]
        prefs["locations"] = [l.strip() for l in locations.split(",") if l.strip()]
        prefs["salary_min"] = salary_min
        prefs["salary_max"] = salary_max
        reqs["blacklist"] = [b.strip() for b in blacklist.split("\n") if b.strip()]
        reqs["whitelist"] = [w.strip() for w in whitelist.split("\n") if w.strip()]
        reqs["accept_startups"] = accept_startups
        reqs["accept_outsourcing"] = accept_outsourcing
        config["preferences"] = prefs
        config["company_requirements"] = reqs
        save_config(config)
        st.success("偏好设置已保存！")

# ============================================================
# Tab 4: 语言设置
# ============================================================
with tab4:
    st.subheader("语言偏好")
    st.caption("设置简历和求职信的默认语言")

    output_config = st.session_state.get("config", {}).get("output", {})
    # 读取旧值用于显示
    bilingual_val = output_config.get("bilingual", True)
    default_lang_val = output_config.get("default_language", "zh")

    bilingual = st.checkbox(
        "生成中英双语版本",
        value=bilingual_val,
        help="勾选后，每次生成简历和求职信都会同时生成中文和英文两个版本"
    )

    default_lang = st.radio(
        "默认主语言",
        ["中文", "英文"],
        index=0 if default_lang_val == "zh" else 1,
        horizontal=True,
        help="当只生成一个版本时使用的语言"
    )

    if st.button("💾 保存语言设置", use_container_width=True):
        config = copy.deepcopy(st.session_state.get("config", {}))
        config["output"] = {
            "bilingual": bilingual,
            "default_language": "zh" if default_lang == "中文" else "en",
            "resume_format": output_config.get("resume_format", "html"),
        }
        save_config(config)
        st.success("语言设置已保存！")

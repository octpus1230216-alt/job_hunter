"""
发现页面 — 职位搜索 + 公司发现 + JD粘贴
"""

import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime


st.title("🔍 发现职位")

tab1, tab2, tab3 = st.tabs(["🌍 海外平台搜索", "🏢 公司发现与扩展", "📋 手动粘贴JD"])

# ============================================================
# Tab 1: 海外平台搜索 (JobSpy)
# ============================================================
with tab1:
    st.subheader("🔗 搜索海外招聘平台")
    st.caption("支持: LinkedIn, Indeed, Glassdoor, Google Jobs, ZipRecruiter")

    config = st.session_state.get("config", {})
    discovery_config = config.get("discovery", {}).get("overseas", {})

    col1, col2 = st.columns(2)
    with col1:
        search_terms = st.text_area(
            "搜索关键词（一行一个）",
            value="\n".join(discovery_config.get("search_terms", ["software engineer"])),
            height=120,
            help="使用英文关键词效果更好"
        )
    with col2:
        countries = st.multiselect(
            "目标国家",
            ["US", "GB", "DE", "SG", "JP", "CA", "AU", "NL", "SE", "CH"],
            default=discovery_config.get("countries", ["US"]),
        )
        hours_old = st.slider("发布时间范围（小时）", 24, 720, discovery_config.get("hours_old", 168), 24)
        max_results = st.number_input("每平台最多结果", 20, 500, discovery_config.get("max_results", 200), 20)

    platforms_available = {
        "indeed": "Indeed（反爬最宽松）",
        "linkedin": "LinkedIn（需要代理）",
        "glassdoor": "Glassdoor",
        "google": "Google Jobs",
        "ziprecruiter": "ZipRecruiter",
    }

    platforms = st.multiselect(
        "选择平台",
        list(platforms_available.keys()),
        default=["indeed"],
        format_func=lambda x: platforms_available[x],
    )

    proxy = st.text_input("代理地址（LinkedIn推荐配置）", placeholder="http://user:pass@ip:port")

    if st.button("🚀 开始搜索", use_container_width=True, type="primary"):
        if not st.session_state.get("llm_client"):
            st.error("请先在配置页面设置API")
        else:
            with st.spinner("正在搜索..."):
                try:
                    from modules.discovery.overseas import OverseasJobDiscovery
                    terms = [t.strip() for t in search_terms.split("\n") if t.strip()]

                    discovery = OverseasJobDiscovery(
                        config={
                            "search_terms": terms,
                            "countries": countries,
                            "hours_old": hours_old,
                            "max_results": max_results,
                            "proxy": proxy,
                        }
                    )

                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    def progress(msg):
                        status_text.text(msg)

                    status_text.text("正在初始化...")
                    progress_bar.progress(0.1)

                    df = discovery.search_all(
                        search_terms=terms,
                        countries=countries,
                        hours_old=hours_old,
                        platforms=platforms,
                        progress_callback=progress,
                    )

                    if df is not None and not df.empty:
                        saved = discovery.save_results(df)
                        st.session_state.jobs_df = df
                        st.session_state.jobs_found = df.to_dict("records")
                        progress_bar.progress(1.0)
                        status_text.text(f"搜索完成！找到 {len(df)} 个职位")
                        st.success(f"找到 {len(df)} 个职位，已保存")
                        st.dataframe(df[["title", "company", "location", "source_platform"]].head(20))
                    else:
                        progress_bar.progress(1.0)
                        status_text.text("未找到职位")
                        st.warning("未找到匹配的职位，尝试更换关键词或平台")

                except ImportError as e:
                    st.error(f"缺少依赖: {e}。请先运行: pip install python-jobspy")
                except Exception as e:
                    st.error(f"搜索失败: {e}")

    # 显示已有结果
    if st.session_state.get("jobs_found"):
        st.markdown("---")
        st.subheader(f"📊 已发现 {len(st.session_state.jobs_found)} 个职位")
        df = pd.DataFrame(st.session_state.jobs_found)
        if "source_platform" in df.columns:
            st.bar_chart(df["source_platform"].value_counts())

# ============================================================
# Tab 2: 公司发现与扩展
# ============================================================
with tab2:
    st.subheader("🏢 AI公司发现")
    st.caption("从已知公司出发，通过AI扩展发现更多值得投递的公司")

    config = st.session_state.get("config", {})
    prefs = config.get("preferences", {})
    discovery_config = config.get("discovery", {}).get("company_discovery", {})

    col1, col2 = st.columns(2)
    with col1:
        depth = st.selectbox(
            "搜索深度",
            ["basic", "medium", "deep"],
            index=["basic", "medium", "deep"].index(discovery_config.get("depth", "medium")),
            format_func=lambda x: {"basic": "基础（仅榜单）", "medium": "中等（榜单+相似公司，推荐）", "deep": "深入（榜单+相似+行业全扫）"} [x],
        )
    with col2:
        existing_companies = st.text_area(
            "已知公司（一行一个，可选）",
            placeholder="Google\nMicrosoft\nApple",
            height=120,
            help="可以用从海外搜索中提取的公司，也可以手写"
        )

    st.markdown("---")
    st.markdown("**发现策略**：")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.info("**第1层: 职位提取**\n从搜索结果的JD中自动提取公司名")
    with col_b:
        st.info("**第2层: AI扩展**\nLLM根据行业和已有公司推荐同类公司")
    with col_c:
        st.info("**第3层: 榜单搜索**\n搜索行业榜单、最佳雇主、高增长公司")

    if st.button("🔎 开始公司发现", use_container_width=True, type="primary"):
        if not st.session_state.get("llm_client"):
            st.error("请先在配置页面设置API")
        else:
            with st.spinner("AI正在发现和扩展公司列表..."):
                try:
                    from modules.discovery.company_finder import CompanyFinder

                    llm = st.session_state.llm_client

                    # 提取已有公司
                    existing = [c.strip() for c in existing_companies.split("\n") if c.strip()]
                    if st.session_state.get("jobs_df") is not None:
                        cf_temp = CompanyFinder({"company_discovery": discovery_config}, llm)
                        job_companies = cf_temp.extract_from_jobs(st.session_state.jobs_df)
                        existing = list(set(existing + job_companies))

                    finder = CompanyFinder({"company_discovery": {"depth": depth}}, llm)

                    result = finder.discover_all(
                        existing_jobs_df=st.session_state.get("jobs_df"),
                        industries=prefs.get("industries", []),
                        locations=prefs.get("locations", []),
                        existing_companies=existing,
                    )

                    st.session_state.discovered_companies = result
                    st.success(f"发现 {result['total_found']} 家公司！")

                    col_x, col_y, col_z = st.columns(3)
                    col_x.metric("从职位提取", result["by_source"]["extracted"])
                    col_y.metric("AI扩展", result["by_source"]["llm_expanded"])
                    col_z.metric("网络搜索", result["by_source"]["web_search"])

                except Exception as e:
                    st.error(f"公司发现失败: {e}")

    # 显示已发现公司
    if st.session_state.get("discovered_companies"):
        companies = st.session_state.discovered_companies.get("companies", [])
        if companies:
            st.markdown("---")
            st.subheader(f"已发现 {len(companies)} 家公司")

            df_companies = pd.DataFrame(companies)
            st.dataframe(df_companies, use_container_width=True)

# ============================================================
# Tab 3: 手动粘贴JD
# ============================================================
with tab3:
    st.subheader("📋 手动粘贴 JD")
    st.caption("把你从任何平台找到的岗位JD粘贴到这里，AI会自动解析并匹配")

    col1, col2 = st.columns([3, 2])
    with col1:
        jd_text = st.text_area(
            "粘贴 JD 内容",
            height=300,
            placeholder="直接把岗位描述的全文粘贴在这里...\n\n包括：公司名、职位名、职责、要求等",
            help="支持任意格式，AI会自动提取关键信息"
        )
    with col2:
        company_name = st.text_input("公司名（如果JD中没有）", placeholder="可选，留空则AI自动提取")
        job_title = st.text_input("职位名（如果JD中没有）", placeholder="可选，留空则AI自动提取")
        source = st.text_input("来源", placeholder="例如：Boss直聘、猎聘、朋友推荐")

    if st.button("🔍 解析并匹配", use_container_width=True, type="primary", disabled=not jd_text.strip()):
        if not st.session_state.get("llm_client"):
            st.error("请先在配置页面设置API")
        elif not st.session_state.get("resume_parsed"):
            st.error("请先在配置页面上传简历")
        else:
            with st.spinner("AI正在解析JD并计算匹配度..."):
                try:
                    llm = st.session_state.llm_client

                    # 解析JD
                    parse_prompt = f"""解析以下职位描述，提取关键信息。返回JSON：
{{
  "company": "公司名",
  "title": "职位名",
  "location": "工作地点",
  "description": "职位描述摘要（保留关键信息，约500字）",
  "required_skills": ["必需技能"],
  "preferred_skills": ["加分技能"],
  "responsibilities": ["主要职责"],
  "salary_range": "薪资范围（如果有）"
}}"""

                    if company_name:
                        parse_prompt += f"\n\n已知公司名: {company_name}"
                    if job_title:
                        parse_prompt += f"\n已知职位: {job_title}"

                    jd_parsed = llm.chat_json(parse_prompt, jd_text)
                    jd_parsed["source"] = source or "手动粘贴"
                    jd_parsed["job_url"] = ""
                    jd_parsed["discovered_at"] = datetime.now().isoformat()

                    # 匹配
                    from modules.matcher import JobMatcher
                    matcher = JobMatcher(llm)
                    match_result = matcher.match_single(
                        st.session_state.resume_parsed,
                        jd_parsed,
                        config.get("preferences", {}),
                    )

                    # 保存到session
                    if "manual_jobs" not in st.session_state:
                        st.session_state.manual_jobs = []
                    st.session_state.manual_jobs.append({
                        "job": jd_parsed,
                        "match": match_result,
                    })

                    # 显示结果
                    st.success(f"解析完成！匹配度: {match_result.get('overall_score', 0)}/100")

                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.markdown("### JD解析结果")
                        st.markdown(f"**公司:** {jd_parsed.get('company', 'N/A')}")
                        st.markdown(f"**职位:** {jd_parsed.get('title', 'N/A')}")
                        st.markdown(f"**地点:** {jd_parsed.get('location', 'N/A')}")
                        if jd_parsed.get("salary_range"):
                            st.markdown(f"**薪资:** {jd_parsed['salary_range']}")
                        st.markdown(f"**必需技能:** {', '.join(jd_parsed.get('required_skills', []))}")

                    with col_b:
                        st.markdown("### 匹配分析")
                        score = match_result.get("overall_score", 0)
                        if score >= 80:
                            st.success(f"总分: {score} — 强匹配！")
                        elif score >= 60:
                            st.info(f"总分: {score} — 中等匹配")
                        else:
                            st.warning(f"总分: {score} — 较弱匹配")

                        st.markdown(f"**优势:** {', '.join(match_result.get('strengths', []))}")
                        st.markdown(f"**不足:** {', '.join(match_result.get('weaknesses', []))}")
                        st.markdown(f"**建议:** {match_result.get('recommendation', '')}")

                except Exception as e:
                    st.error(f"解析失败: {e}")

    # 显示手动粘贴的历史
    if st.session_state.get("manual_jobs"):
        st.markdown("---")
        st.subheader(f"📋 已粘贴 {len(st.session_state.manual_jobs)} 个岗位")

        for i, item in enumerate(st.session_state.manual_jobs):
            with st.expander(f"#{i+1} {item['job'].get('company', '?')} - {item['job'].get('title', '?')} "
                             f"(匹配度: {item['match'].get('overall_score', 0)})"):
                st.json(item)

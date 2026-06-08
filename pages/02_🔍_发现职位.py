"""
发现职位 — AI 职业定位 → 多渠道搜索 → 审核挑选（一体化）
"""

import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime

st.title("🔍 发现职位")

if not st.session_state.get("resume_parsed"):
    st.info("👋 请先在 ⚙️ 配置页面上传简历，然后回到这里开始职业定位")
    st.stop()

if not st.session_state.get("llm_client"):
    st.warning("⚠️ 请先在 ⚙️ 配置页面设置 API Key")
    st.stop()

# ============================================================
# State 初始化
# ============================================================
if "career_report" not in st.session_state:
    # 尝试加载已有报告
    from modules.career_advisor import CareerAdvisor
    advisor = CareerAdvisor(st.session_state.llm_client)
    cached = advisor.load_latest_report()
    st.session_state.career_report = cached if cached else None

if "all_jobs" not in st.session_state:
    st.session_state.all_jobs = []

# ============================================================
# Step 1: AI 职业定位
# ============================================================
st.markdown("---")
st.subheader("🎯 Step 1: AI 职业定位")

if st.session_state.career_report and not st.session_state.career_report.get("error"):
    report = st.session_state.career_report
    st.success(f"✅ 已有定位报告（生成于 {report.get('generated_at', '?')[:19]}）")

    with st.expander("查看 / 编辑定位报告", expanded=False):
        _render_report_editor(report)

    if st.button("🔄 重新生成定位报告", use_container_width=True):
        with st.status("AI 正在分析你的简历...", expanded=True) as status:
            try:
                from modules.career_advisor import CareerAdvisor
                advisor = CareerAdvisor(st.session_state.llm_client)
                config = st.session_state.get("config", {})
                prefs = config.get("preferences", {})

                st.write("🔬 拆解能力结构...")
                st.write("🔄 分析可迁移方向...")
                st.write("🔍 生成双语搜索关键词...")

                report = advisor.analyze(
                    st.session_state.resume_parsed,
                    preferences=prefs,
                    salary_stance="no_decrease",
                )
                advisor.save_report(report)
                st.session_state.career_report = report
                st.session_state.all_jobs = []  # 清空旧结果
                status.update(label="定位报告生成完成！", state="complete")
                st.rerun()
            except Exception as e:
                status.update(label="生成失败", state="error")
                st.error(f"生成失败: {str(e)[:200]}")

else:
    st.info("还没有职业定位报告。点击下方按钮，AI 会分析你的简历并给出职业建议。")

    if st.button("🚀 开始 AI 职业定位", use_container_width=True, type="primary"):
        with st.status("AI 正在深入分析你的简历...", expanded=True) as status:
            try:
                from modules.career_advisor import CareerAdvisor
                advisor = CareerAdvisor(st.session_state.llm_client)
                config = st.session_state.get("config", {})
                prefs = config.get("preferences", {})

                st.write("🔬 拆解能力结构...")
                st.write("🔄 分析可迁移方向...")
                st.write("🔍 生成双语搜索关键词...")
                st.write("💰 估计市场薪资...")

                report = advisor.analyze(
                    st.session_state.resume_parsed,
                    preferences=prefs,
                    salary_stance="no_decrease",
                )
                advisor.save_report(report)
                st.session_state.career_report = report
                status.update(label="定位报告生成完成！", state="complete")
                st.success("AI 职业定位完成！向下滚动查看搜索选项。")
            except Exception as e:
                status.update(label="生成失败", state="error")
                st.error(f"AI 分析失败: {str(e)[:200]}")
                st.info("请检查 API 配置是否正确，或稍后重试")

# ============================================================
# Step 2: 多渠道搜索
# ============================================================
if not st.session_state.career_report or st.session_state.career_report.get("error"):
    st.stop()

report = st.session_state.career_report

st.markdown("---")
st.subheader("🔎 Step 2: 搜索职位")

tab1, tab2, tab3 = st.tabs(["🌍 海外平台自动搜索", "🏠 国内平台直达搜索", "📋 手动粘贴 JD"])

# ---- Tab 1: 海外平台 ----
with tab1:
    st.markdown("**使用 JobSpy 自动搜索 LinkedIn / Indeed 等海外平台**")

    keywords_en = report.get("search_keywords", {}).get("en", {})
    default_keywords = keywords_en.get("core", []) + keywords_en.get("transferable", [])

    col1, col2 = st.columns([2, 1])
    with col1:
        search_terms = st.text_area(
            "英文搜索关键词（每行一个，基于AI定位生成）",
            value="\n".join(default_keywords[:10]) if default_keywords else "software engineer",
            height=150,
            help="可以直接使用AI生成的关键词，也可以自行修改"
        )
    with col2:
        countries = st.multiselect("目标国家", ["US", "GB", "DE", "SG", "JP", "CA", "AU", "NL"],
                                    default=["US"])
        hours_old = st.slider("发布时间（小时）", 24, 720, 168, 24)
        platforms = st.multiselect("平台", ["indeed", "linkedin", "glassdoor", "google"],
                                    default=["indeed"],
                                    format_func=lambda x: {"indeed": "Indeed", "linkedin": "LinkedIn",
                                        "glassdoor": "Glassdoor", "google": "Google Jobs"}[x])

    if st.button("🚀 开始海外搜索", use_container_width=True, type="primary", key="btn_overseas"):
        terms = [t.strip() for t in search_terms.split("\n") if t.strip()]
        if not terms:
            st.error("请输入至少一个搜索关键词")
        else:
            with st.status("正在搜索海外平台...", expanded=True) as status:
                try:
                    from jobspy import scrape_jobs

                    all_results = []
                    total_terms = len(terms) * len(countries) * len(platforms)
                    count = 0

                    for term in terms[:3]:  # 限制搜索数量避免过慢
                        for country in countries[:3]:
                            for platform in platforms[:2]:
                                count += 1
                                st.write(f"🔍 ({count}/{min(total_terms, 18)}) {platform}: {term} in {country}")

                                try:
                                    kwargs = {
                                        "site_name": platform,
                                        "search_term": term,
                                        "results_wanted": 50,
                                        "hours_old": hours_old,
                                        "country_indeed": country,
                                    }
                                    if platform == "google":
                                        kwargs["google_search_term"] = f"{term} jobs"

                                    df = scrape_jobs(**kwargs)
                                    if df is not None and not df.empty:
                                        df["source_platform"] = platform
                                        df["source_country"] = country
                                        all_results.append(df)
                                except Exception as e:
                                    st.write(f"  ⚠️ 跳过: {str(e)[:80]}")

                    if all_results:
                        combined = pd.concat(all_results, ignore_index=True)
                        combined = combined.drop_duplicates(subset=["job_url"], keep="first")
                        st.session_state.jobs_df = combined

                        # 立即匹配
                        st.write("🧠 正在计算匹配度...")
                        new_jobs = _match_jobs(combined, st.session_state.resume_parsed,
                                              st.session_state.llm_client,
                                              report)

                        # 合并到 all_jobs
                        st.session_state.all_jobs = new_jobs + [
                            j for j in st.session_state.all_jobs
                            if j.get("source_platform") not in platforms
                        ]
                        status.update(label=f"搜索完成！找到 {len(new_jobs)} 个职位", state="complete")
                        st.success(f"共找到 {len(new_jobs)} 个职位")
                    else:
                        status.update(label="未找到结果", state="complete")
                        st.warning("未找到匹配的职位，尝试更换关键词或平台")

                except ImportError:
                    status.update(label="缺少依赖", state="error")
                    st.error("缺少 JobSpy 依赖。请运行: pip install python-jobspy tls_client markdownify regex")
                except Exception as e:
                    status.update(label="搜索失败", state="error")
                    st.error(f"搜索失败: {str(e)[:200]}")

# ---- Tab 2: 国内平台直达搜索 ----
with tab2:
    st.markdown("**AI 会生成直达搜索链接，点击即可跳转到招聘平台**")
    st.caption("浏览器脚本（浏览即收集）将在下一批更新中加入")

    keywords_zh = report.get("search_keywords", {}).get("zh", {})
    core_kw = keywords_zh.get("core", [])
    trans_kw = keywords_zh.get("transferable", [])

    if core_kw or trans_kw:
        st.markdown("### 🔗 直达搜索链接")

        if core_kw:
            st.markdown("**核心方向：**")
            for kw in core_kw:
                col_a, col_b = st.columns(2)
                with col_a:
                    url = f"https://www.zhipin.com/web/geek/job?query={kw}"
                    st.markdown(f"[🔍 Boss直聘 — {kw}]({url})")
                with col_b:
                    url2 = f"https://www.liepin.com/zhaopin/?key={kw}"
                    st.markdown(f"[🔍 猎聘 — {kw}]({url2})")

        if trans_kw:
            st.markdown("**可迁移方向：**")
            for kw in trans_kw:
                col_a, col_b = st.columns(2)
                with col_a:
                    url = f"https://www.zhipin.com/web/geek/job?query={kw}"
                    st.markdown(f"[🔍 Boss直聘 — {kw}]({url})")
                with col_b:
                    url2 = f"https://www.liepin.com/zhaopin/?key={kw}"
                    st.markdown(f"[🔍 猎聘 — {kw}]({url2})")

        st.info(
            "找到感兴趣的职位后，复制 JD 内容，粘贴到右侧「📋 手动粘贴 JD」标签页，"
            "AI 会自动计算匹配度并生成定制简历。"
        )
    else:
        st.info("AI 定位报告中没有搜索关键词，请先生成定位报告")

# ---- Tab 3: 手动粘贴 JD ----
with tab3:
    st.markdown("**粘贴任意平台的 JD，AI 自动解析 + 匹配 + 标注行业类型**")

    with st.form("paste_jd"):
        jd_text = st.text_area("粘贴 JD 内容", height=250, placeholder="把岗位描述全文粘贴在这里...")
        company_override = st.text_input("公司名（留空则AI自动提取）", placeholder="可选")
        title_override = st.text_input("职位名（留空则AI自动提取）", placeholder="可选")

        submitted = st.form_submit_button("🔍 解析并匹配", use_container_width=True, type="primary")

        if submitted and jd_text.strip():
            with st.status("正在分析...", expanded=True) as status:
                try:
                    llm = st.session_state.llm_client

                    # 解析 JD
                    parse_prompt = """解析以下职位描述为 JSON：
{
  "company": "公司名",
  "title": "职位名",
  "location": "地点",
  "description": "JD摘要（500字）",
  "required_skills": ["必需技能"],
  "preferred_skills": ["加分技能"]
}"""

                    jd_parsed = llm.chat_json(parse_prompt, jd_text)
                    if company_override:
                        jd_parsed["company"] = company_override
                    if title_override:
                        jd_parsed["title"] = title_override
                    jd_parsed["source"] = "手动粘贴"
                    jd_parsed["source_platform"] = "manual"
                    jd_parsed["discovered_at"] = datetime.now().isoformat()

                    # 匹配
                    st.write("🧠 计算匹配度...")
                    from modules.matcher import JobMatcher
                    matcher = JobMatcher(llm)
                    match = matcher.match_single(
                        st.session_state.resume_parsed, jd_parsed,
                        st.session_state.get("config", {}).get("preferences", {}),
                    )

                    # 判断行业类型
                    industry_tag = _classify_industry(jd_parsed, report)

                    job_entry = {**jd_parsed, "_match": match, "_industry_tag": industry_tag}

                    # 去重后加入
                    existing_urls = {j.get("job_url", "") for j in st.session_state.all_jobs}
                    if jd_parsed.get("job_url", "") not in existing_urls or not jd_parsed.get("job_url"):
                        st.session_state.all_jobs.insert(0, job_entry)

                    status.update(label="解析完成", state="complete")
                    st.success(f"匹配度: {match.get('overall_score', 0)}/100 | 标签: {industry_tag}")
                    st.json(match)

                except Exception as e:
                    status.update(label="解析失败", state="error")
                    st.error(f"解析失败: {str(e)[:200]}")

# ============================================================
# Step 3: 审核挑选
# ============================================================
if st.session_state.all_jobs:
    st.markdown("---")
    st.subheader(f"📊 Step 3: 审核挑选（共 {len(st.session_state.all_jobs)} 个）")

    # 筛选
    col1, col2, col3 = st.columns(3)
    with col1:
        industry_filter = st.selectbox("行业标签", ["全部", "🔵 核心行业", "🟢 可迁移", "🟡 探索"])
    with col2:
        channel_filter = st.selectbox("来源渠道", ["全部", "海外平台", "手动粘贴"])
    with col3:
        sort_by = st.selectbox("排序", ["按匹配度", "按时间"])

    # 构建展示列表
    display_jobs = _filter_jobs(st.session_state.all_jobs, industry_filter, channel_filter, sort_by)

    # 按行业标签分组显示
    if "selected_indices" not in st.session_state:
        st.session_state.selected_indices = []

    for i, job in enumerate(display_jobs):
        tag = job.get("_industry_tag", "探索")
        tag_emoji = {"核心行业": "🔵", "可迁移": "🟢", "探索": "🟡"}.get(tag, "🟡")
        match_data = job.get("_match", {})
        score = match_data.get("overall_score", "?")

        with st.expander(
            f"{tag_emoji} [{score}分] {job.get('company', '?')} — {job.get('title', '?')} "
            f"({job.get('location', '')})"
        ):
            col_a, col_b = st.columns([6, 2])
            with col_a:
                desc = job.get("description", "")
                if desc:
                    st.markdown(desc[:500] + ("..." if len(desc) > 500 else ""))
                if job.get("job_url"):
                    st.markdown(f"[🔗 查看原文]({job.get('job_url')})")
                if match_data.get("strengths"):
                    st.markdown(f"**优势:** {', '.join(match_data.get('strengths', []))}")
                if match_data.get("weaknesses"):
                    st.markdown(f"**注意:** {', '.join(match_data.get('weaknesses', []))}")

            with col_b:
                if i in st.session_state.selected_indices:
                    if st.button("↩️ 取消", key=f"unsel_{i}", use_container_width=True):
                        st.session_state.selected_indices.remove(i)
                        st.rerun()
                else:
                    if st.button("✅ 选择投递", key=f"sel_{i}", use_container_width=True):
                        st.session_state.selected_indices.append(i)
                        st.rerun()

    # 已选汇总
    if st.session_state.selected_indices:
        st.markdown("---")
        st.subheader(f"✅ 已选 {len(st.session_state.selected_indices)} 个岗位")

        selected = [display_jobs[i] for i in st.session_state.selected_indices]
        for s in selected:
            st.markdown(f"- **{s.get('company')}** — {s.get('title')}")

        if st.button("🚀 确认选择，去生成简历", use_container_width=True, type="primary"):
            # 构造标准格式传给生成页
            st.session_state.selected_jobs = [
                {"company": s.get("company", ""), "title": s.get("title", ""),
                 "location": s.get("location", ""), "description": s.get("description", ""),
                 "source_platform": s.get("source_platform", ""),
                 "_match_score": s.get("_match", {}).get("overall_score", 0),
                 "job_url": s.get("job_url", "")}
                for s in selected
            ]
            st.success(f"已选择 {len(selected)} 个岗位，请前往「✨ 生成简历」页面")
            st.switch_page("pages/04_✨_生成简历.py")


# ============================================================
# 辅助函数
# ============================================================
def _render_report_editor(report):
    """渲染可编辑的定位报告"""
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 🎯 核心方向")
        for d in report.get("core_directions", []):
            st.markdown(f"**{d.get('role', '')}** — 匹配度 {d.get('match_score', 0)}")
            st.caption(d.get("reason", ""))
            st.caption(f"优势: {', '.join(d.get('key_strengths', []))}")

    with col2:
        st.markdown("### 🔄 可迁移方向")
        for d in report.get("transferable_directions", []):
            st.markdown(f"**{d.get('role', '')}** → {d.get('new_industry', '')}")
            st.caption(f"可迁移度: {d.get('transferability_score', 0)}")
            st.caption(f"可复用: {', '.join(d.get('transferable_skills', []))}")
            st.caption(f"需补充: {', '.join(d.get('skill_gaps', []))}")

    st.markdown("### ⚠️ 弱项提醒")
    for w in report.get("weakness_alerts", []):
        sev = w.get("severity", "low")
        icon = "🔴" if sev == "high" else "🟡" if sev == "medium" else "🟢"
        st.markdown(f"{icon} **{w.get('area', '')}**: {w.get('description', '')}")

    st.markdown("### 💰 薪资锚定")
    salary = report.get("salary_anchor", {})
    if salary:
        st.markdown(f"- 当前估计: {salary.get('current_estimated_range', 'N/A')}")
        st.markdown(f"- 核心方向: {salary.get('core_direction_range', 'N/A')}")
        st.markdown(f"- 可迁移方向: {salary.get('transferable_range', 'N/A')}")

    st.markdown("### 🔍 搜索关键词")
    kw = report.get("search_keywords", {})
    st.markdown(f"**中文:** {', '.join(kw.get('zh', {}).get('core', []) + kw.get('zh', {}).get('transferable', []))}")
    st.markdown(f"**English:** {', '.join(kw.get('en', {}).get('core', []) + kw.get('en', {}).get('transferable', []))}")


def _match_jobs(jobs_df, resume, llm_client, report, max_jobs: int = 30) -> list:
    """对搜索结果进行即时匹配"""
    from modules.matcher import JobMatcher

    matcher = JobMatcher(llm_client)
    results = []

    jobs = jobs_df.head(max_jobs).to_dict("records")
    for job in jobs:
        # 简单预过滤：跳过明显不相关的
        match = matcher.match_single(resume, job)
        tag = _classify_industry(job, report)
        results.append({**job, "_match": match, "_industry_tag": tag})

    # 按匹配度排序
    results.sort(key=lambda x: x.get("_match", {}).get("overall_score", 0), reverse=True)
    return results


def _classify_industry(job: dict, report: dict) -> str:
    """判断岗位属于核心/可迁移/探索"""
    title = job.get("title", "").lower()
    desc = job.get("description", "").lower()[:500]

    # 检查核心方向关键词
    for d in report.get("core_directions", []):
        role = d.get("role", "").lower()
        if role and (role in title or role in desc):
            return "核心行业"

    # 检查可迁移方向关键词
    for d in report.get("transferable_directions", []):
        role = d.get("role", "").lower()
        if role and (role in title or role in desc):
            return "可迁移"

    return "探索"


def _filter_jobs(all_jobs: list, industry_filter: str, channel_filter: str, sort_by: str) -> list:
    """筛选和排序"""
    result = list(all_jobs)

    if industry_filter != "全部":
        tag_map = {"🔵 核心行业": "核心行业", "🟢 可迁移": "可迁移", "🟡 探索": "探索"}
        target_tag = tag_map.get(industry_filter, industry_filter)
        result = [j for j in result if j.get("_industry_tag", "") == target_tag]

    if channel_filter != "全部":
        if channel_filter == "海外平台":
            result = [j for j in result if j.get("source_platform") not in ("manual", None, "")]
        elif channel_filter == "手动粘贴":
            result = [j for j in result if j.get("source_platform") == "manual"]

    if sort_by == "按匹配度":
        result.sort(key=lambda x: x.get("_match", {}).get("overall_score", 0), reverse=True)
    else:
        result.reverse()  # 最新的在前面

    return result

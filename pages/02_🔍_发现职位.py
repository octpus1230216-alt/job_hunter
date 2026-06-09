"""
发现职位 — AI 职业定位 → 多渠道搜索 → 审核挑选（一体化）
"""

import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime



# ============================================================
# 辅助函数（必须在页面主逻辑之前定义）
# ============================================================
def _render_report_editor(report):
    """渲染可编辑的定位报告（双轨版本）"""
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🎯 策略A：从行业找职位")
        for item in report.get("strategy_a", {}).get("items", []):
            st.markdown(f"**{item.get('industry', '')}**")
            st.caption(f"职位方向: {', '.join(item.get('roles', []))}")
            st.caption(f"搜索词: {', '.join(item.get('keywords_zh', []))}")

    with col2:
        st.markdown("### 🔄 策略B：从能力找行业")
        for item in report.get("strategy_b", {}).get("items", []):
            st.markdown(f"**{item.get('skill', '')}**")
            st.caption(f"适用行业: {', '.join(item.get('industries', []))}")
            st.caption(f"搜索词: {', '.join(item.get('keywords_zh', []))}")

    st.markdown("### ⚠️ 弱项提醒")
    for w in report.get("weakness_alerts", []):
        sev = w.get("severity", "low")
        icon = "🔴" if sev == "high" else "🟡" if sev == "medium" else "🟢"
        st.markdown(f"{icon} **{w.get('area', '')}**: {w.get('description', '')}")

    st.markdown("### 💰 薪资锚定")
    salary = report.get("salary_anchor", {})
    if salary:
        st.markdown(f"- 当前估计: {salary.get('current_estimated_range', 'N/A')}")
        st.markdown(f"- 市场范围: {salary.get('market_range', 'N/A')}")

    st.markdown("### 🔍 搜索关键词汇总")
    kw = report.get("search_keywords", {})
    st.markdown(f"**中文:** {', '.join(kw.get('zh', []))}")
    st.markdown(f"**English:** {', '.join(kw.get('en', []))}")


def _classify_industry(job: dict, report: dict) -> str:
    """判断岗位属于核心/可迁移/探索"""
    title = job.get("title", "").lower()
    desc = job.get("description", "").lower()[:500]

    # 检查策略A关键词
    for item in report.get("strategy_a", {}).get("items", []):
        for kw in item.get("keywords_zh", []) + item.get("keywords_en", []):
            if kw.lower() in title or kw.lower() in desc:
                return "核心行业"

    # 检查策略B关键词
    for item in report.get("strategy_b", {}).get("items", []):
        for kw in item.get("keywords_zh", []) + item.get("keywords_en", []):
            if kw.lower() in title or kw.lower() in desc:
                return "可迁移"

    return "探索"


def _match_single_job(job: dict, resume: dict, llm_client) -> dict:
    """单个岗位匹配"""
    from modules.matcher import JobMatcher
    matcher = JobMatcher(llm_client)
    return matcher.match_single(resume, job)


def _match_jobs(jobs_df, resume, llm_client, report, max_jobs: int = 30) -> list:
    """对搜索结果进行即时匹配"""
    from modules.matcher import JobMatcher
    matcher = JobMatcher(llm_client)
    results = []
    jobs = jobs_df.head(max_jobs).to_dict("records")
    for job in jobs:
        match = matcher.match_single(resume, job)
        tag = _classify_industry(job, report)
        results.append({**job, "_match": match, "_industry_tag": tag})
    results.sort(key=lambda x: x.get("_match", {}).get("overall_score", 0), reverse=True)
    return results


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
        result.reverse()
    return result


# ============================================================
# 页面主逻辑
# ============================================================
st.title("🔍 发现职位")

if not st.session_state.get("resume_parsed"):
    st.info("👋 请先在 ⚙️ 配置页面上传简历，然后回到这里开始职业定位")
    st.stop()

if not st.session_state.get("llm_client"):
    st.warning("⚠️ 请先在 ⚙️ 配置页面设置 API Key")
    st.stop()

# ============================================================
# 后台任务状态面板
# ============================================================
_task_dir = Path(__file__).parent.parent / "data" / "search_tasks"
_task_dir.mkdir(parents=True, exist_ok=True)

active_tasks = []
for f in sorted(_task_dir.glob("*_progress.json")):
    try:
        with open(f, "r", encoding="utf-8") as fh:
            task = json.load(fh)
            if task.get("status") in ("running", "pending"):
                active_tasks.append(task)
            elif task.get("status") == "completed":
                # 加载结果
                result_file = _task_dir / f"{task['task_id']}_results.json"
                if result_file.exists():
                    with open(result_file, "r", encoding="utf-8") as rf:
                        results = json.load(rf)
                    task["results"] = results
                active_tasks.append(task)
    except Exception:
        pass

if active_tasks:
    with st.container():
        st.markdown("### 📊 后台任务")
        for task in active_tasks:
            status = task.get("status", "")
            icon = {"running": "🔄", "completed": "✅", "error": "❌", "cancelled": "⏹", "pending": "⏳"}.get(status, "📌")
            col_a, col_b, col_c = st.columns([3, 1, 1])
            with col_a:
                st.markdown(f"{icon} **{task.get('task_id', '?')}** — {task.get('message', '')}")
            with col_b:
                if status == "completed" and task.get("results"):
                    if st.button("📥 导入", key=f"import_{task['task_id']}", use_container_width=True):
                        new_jobs = task["results"]
                        if not isinstance(new_jobs, list):
                            new_jobs = [new_jobs]
                        for nj in new_jobs[:50]:
                            tag = _classify_industry(nj, st.session_state.career_report or {})
                            nj["_industry_tag"] = tag
                            nj["_match"] = {}
                        st.session_state.all_jobs = new_jobs + st.session_state.all_jobs
                        _task_file = _task_dir / f"{task['task_id']}_task.json"
                        if _task_file.exists():
                            _task_file.unlink()
                        st.success("已导入！")
                        st.rerun()
            with col_c:
                if status == "running":
                    if st.button("⏹ 停止", key=f"stop_{task['task_id']}", use_container_width=True):
                        from search_worker import cancel_task
                        cancel_task(task["task_id"])
                        st.success("已取消")
                        st.rerun()
        st.markdown("---")

# ============================================================
# 每日精选
# ============================================================
_digest_dir = Path(__file__).parent.parent / "data" / "daily_digests"
_digest_dir.mkdir(parents=True, exist_ok=True)
_latest_digest = sorted(_digest_dir.glob("digest_*.json"), reverse=True)

if _latest_digest:
    with st.expander("📬 每日精选推荐", expanded=False):
        with open(_latest_digest[0], "r", encoding="utf-8") as f:
            digest = json.load(f)

        st.caption(f"生成日期: {digest.get('date', '?')} | 共发现 {digest.get('total_found', 0)} 个岗位")

        top20 = digest.get("top_20", [])[:5]
        for i, job in enumerate(top20):
            score = job.get("_match_score", "?")
            st.markdown(f"**#{i+1} [{score}分] {job.get('company', '?')}** — {job.get('title', '?')}")

        st.markdown("---")
        st.caption("💡 手动运行 `python daily_digest.py` 生成今日精选")
        st.caption("💡 配合 Windows 任务计划程序实现每日自动运行")

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

tab1, tab2, tab3, tab4 = st.tabs(["🌍 海外平台自动搜索", "🏠 国内平台直达搜索", "🤖 AI 全网搜索", "📋 手动粘贴 JD"])

# ---- Tab 1: 海外平台 ----
with tab1:
    st.markdown("**使用 JobSpy 自动搜索 LinkedIn / Indeed 等海外平台**")

    keywords_en = report.get("search_keywords", {}).get("en", [])
    default_keywords = keywords_en if keywords_en else ["ESG analyst", "climate policy", "sustainability"]

    col1, col2 = st.columns([2, 1])
    with col1:
        search_terms = st.text_area(
            "英文搜索关键词（每行一个，基于AI定位生成）",
            value="\n".join(default_keywords[:10]) if default_keywords else "software engineer",
            height=150,
            help="可以直接使用AI生成的关键词，也可以自行修改"
        )
    # JobSpy 国家映射
    JOBSPY_COUNTRIES = {
        "中国": "china", "美国": "usa/us/united states", "英国": "uk/united kingdom",
        "德国": "germany", "法国": "france", "日本": "japan", "新加坡": "singapore",
        "加拿大": "canada", "澳大利亚": "australia", "印度": "india",
        "荷兰": "netherlands", "瑞士": "switzerland", "韩国": "south korea",
        "香港": "hong kong", "全球": "worldwide",
    }

    with col2:
        countries_display = st.multiselect(
            "目标国家",
            list(JOBSPY_COUNTRIES.keys()),
            default=["美国"],
        )
        hours_old = st.slider("发布时间（小时）", 24, 720, 168, 24)
        platforms = st.multiselect("平台", ["indeed", "linkedin", "glassdoor", "google"],
                                    default=["indeed"],
                                    format_func=lambda x: {"indeed": "Indeed", "linkedin": "LinkedIn",
                                        "glassdoor": "Glassdoor", "google": "Google Jobs"}[x])

    col3, col4 = st.columns(2)
    with col3:
        if st.button("🚀 前台搜索（等待结果）", use_container_width=True, key="btn_overseas"):
            terms = [t.strip() for t in search_terms.split("\n") if t.strip()]
            if not terms:
                st.error("请输入至少一个搜索关键词")
            else:
                with st.status("正在搜索海外平台...", expanded=True) as status:
                    try:
                        from jobspy import scrape_jobs

                        all_results = []
                        total_terms = len(terms) * len(countries_display) * len(platforms)
                        count = 0

                        for term in terms[:3]:
                            for disp_name in countries_display[:3]:
                                country = JOBSPY_COUNTRIES.get(disp_name, disp_name)
                                for platform in platforms[:2]:
                                    count += 1
                                    st.write(f"🔍 ({count}/{min(total_terms, 18)}) {platform}: {term} in {disp_name}")

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

                            st.write("🧠 正在计算匹配度...")
                            new_jobs = _match_jobs(combined, st.session_state.resume_parsed,
                                                  st.session_state.llm_client,
                                                  report)

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

    with col4:
        if st.button("🔄 后台搜索（切页不中断）", use_container_width=True, key="btn_bg_overseas",
                     help="搜索在后台运行，即使切换到其他页面也不会中断"):
            terms = [t.strip() for t in search_terms.split("\n") if t.strip()]
            if not terms:
                st.error("请输入至少一个搜索关键词")
            else:
                from search_worker import submit_task
                country_values = [JOBSPY_COUNTRIES.get(c, c) for c in countries_display]
                task_id = submit_task("overseas", {
                    "keywords": terms,
                    "countries": country_values,
                    "platforms": platforms,
                    "hours_old": hours_old,
                })
                st.success(f"后台任务已提交: {task_id}")
                st.info("💡 请在终端运行 `python search_worker.py` 来启动后台工作进程")
                st.info("💡 搜索完成后，刷新页面在顶部「后台任务」面板中导入结果")
                st.rerun()

# ---- Tab 2: 国内平台直达搜索 ----
with tab2:
    st.markdown("**AI 生成直达搜索链接 + 浏览器自动采集**")

    # 采集器状态
    col_s1, col_s2 = st.columns([3, 1])
    with col_s1:
        try:
            import httpx
            resp = httpx.get("http://localhost:8765/", timeout=2)
            if resp.status_code == 200:
                data = resp.json()
                st.success(f"✅ 采集器已运行 — 已收集 {data.get('total_collected', 0)} 个国内岗位")
            else:
                st.info("🔌 采集器未启动，点击下方按钮启动")
        except Exception:
            st.info("🔌 采集器未启动，点击下方按钮启动")

    with col_s2:
        if st.button("▶️ 启动采集器", use_container_width=True, key="start_collector"):
            st.info("请在终端运行: `python collector_server.py`")
            st.caption("然后安装浏览器脚本，浏览 Boss直聘/猎聘 时自动采集")

    # 浏览器脚本安装说明
    with st.expander("📥 安装采集工具（首次使用需要）"):
        st.markdown("""
        **推荐：Chrome 扩展（一键翻页批量抓取）**
        1. 打开 Chrome，地址栏输入 `chrome://extensions/`
        2. 打开右上角「开发者模式」
        3. 点击「加载已解压的扩展程序」
        4. 选择 `job-hunter/chrome_extension/` 目录
        5. 安装完成！工具栏出现扩展图标

        **使用方式：**
        - 在 Boss直聘/猎聘 搜索关键词后，点击扩展图标
        - 点击「🔄 自动翻页扫描」→ 自动翻页采集所有结果页
        - 或点击「📥 采集当前页」只采集当前页

        **备选：Tampermonkey 脚本（手动逐条采集）**
        - Chrome: [Tampermonkey](https://chrome.google.com/webstore/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo)
        - 导入 `browser_script/boss_collector.user.js`
        """)

    # AI 生成的直达搜索链接
    keywords_zh = report.get("search_keywords", {}).get("zh", [])
    core_kw = keywords_zh[:5] if keywords_zh else []
    trans_kw = keywords_zh[5:] if len(keywords_zh) > 5 else []

    if core_kw or trans_kw:
        st.markdown("### 🔗 AI 生成的直达搜索链接")

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

    # 已采集的国内岗位
    try:
        import httpx
        resp = httpx.get("http://localhost:8765/jobs", timeout=2)
        if resp.status_code == 200:
            collected = resp.json().get("jobs", [])
            if collected:
                st.markdown("---")
                st.markdown(f"### 📥 浏览器采集的国内岗位（{len(collected)} 个）")

                for i, cjob in enumerate(collected):
                    with st.expander(f"#{i+1} {cjob.get('company', '?')} — {cjob.get('title', '?')}"):
                        col_a, col_b = st.columns([6, 2])
                        with col_a:
                            if cjob.get("salary"):
                                st.caption(f"💰 {cjob['salary']} | 📍 {cjob.get('location', '')}")
                            if cjob.get("description"):
                                st.markdown(cjob.get("description", "")[:400])

                        with col_b:
                            if st.button("✅ 导入并匹配", key=f"import_dom_{i}", use_container_width=True):
                                with st.spinner("正在匹配..."):
                                    jd_parsed = {
                                        "company": cjob.get("company", ""),
                                        "title": cjob.get("title", ""),
                                        "location": cjob.get("location", ""),
                                        "description": cjob.get("description", ""),
                                        "source_platform": "boss_auto",
                                        "job_url": cjob.get("job_url", ""),
                                    }
                                    from modules.matcher import JobMatcher
                                    matcher = JobMatcher(st.session_state.llm_client)
                                    match = matcher.match_single(
                                        st.session_state.resume_parsed, jd_parsed,
                                        st.session_state.get("config", {}).get("preferences", {}),
                                    )
                                    tag = _classify_industry(jd_parsed, report)
                                    st.session_state.all_jobs.insert(0, {
                                        **jd_parsed, "_match": match, "_industry_tag": tag
                                    })
                                    st.success(f"已导入！匹配度: {match.get('overall_score', 0)}")
                                    st.rerun()
    except Exception:
        pass

# ---- Tab 3: AI 全网搜索 ----
with tab3:
    st.markdown("**AI 使用搜索引擎帮你发现全网公开职位**")
    st.caption("不限于特定平台，覆盖更广，由 AI 二次筛选")

    search_kw = report.get("search_keywords", {})

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**中文关键词**")
        zh_kw = st.text_area(
            "zh_kw",
            label_visibility="collapsed",
            value="\n".join(search_kw.get("zh", [])[:8]) if search_kw.get("zh") else "",
            height=120,
            placeholder="每行一个关键词，如：ESG 分析师、碳市场 研究员",
        )
    with col2:
        st.markdown("**英文关键词**")
        en_kw = st.text_area(
            "en_kw",
            label_visibility="collapsed",
            value="\n".join(search_kw.get("en", [])[:8]) if search_kw.get("en") else "",
            height=120,
            placeholder="One keyword per line, e.g. ESG analyst, climate policy",
        )

    max_per = st.slider("每个关键词最多结果数", 5, 30, 15, 5)

    if st.button("🚀 开始 AI 全网搜索", use_container_width=True, type="primary", key="btn_ai_search"):
        zh_list = [k.strip() for k in zh_kw.split("\n") if k.strip()]
        en_list = [k.strip() for k in en_kw.split("\n") if k.strip()]

        if not zh_list and not en_list:
            st.error("请输入至少一个关键词")
        else:
            with st.status("AI 正在搜索全网职位...", expanded=True) as status:
                try:
                    from modules.ai_searcher import AISearcher
                    searcher = AISearcher(st.session_state.llm_client)

                    all_found = []

                    if zh_list:
                        st.write(f"🌏 搜索中文关键词: {', '.join(zh_list[:5])}")
                        found = searcher.search(zh_list, max_per)
                        all_found.extend(found)
                        st.write(f"  找到 {len(found)} 条")

                    if en_list:
                        st.write(f"🌍 搜索英文关键词: {', '.join(en_list[:5])}")
                        found = searcher.search(en_list, max_per)
                        all_found.extend(found)
                        st.write(f"  找到 {len(found)} 条")

                    if all_found:
                        # 匹配
                        st.write("🧠 正在计算匹配度...")
                        matched = []
                        for job in all_found[:30]:
                            match = _match_single_job(job, st.session_state.resume_parsed,
                                                      st.session_state.llm_client)
                            tag = _classify_industry(job, report)
                            matched.append({**job, "_match": match, "_industry_tag": tag})

                        matched.sort(key=lambda x: x.get("_match", {}).get("overall_score", 0), reverse=True)
                        st.session_state.all_jobs = matched + st.session_state.all_jobs

                        status.update(label=f"搜索完成！找到 {len(all_found)} 个职位", state="complete")
                        st.success(f"共找到 {len(all_found)} 个职位，已加入审核列表")
                    else:
                        status.update(label="未找到结果", state="complete")
                        st.warning("未找到结果，尝试更换关键词")

                except Exception as e:
                    status.update(label="搜索失败", state="error")
                    st.error(f"搜索失败: {str(e)[:200]}")

# ---- Tab 4: 手动粘贴 JD ----
with tab4:
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

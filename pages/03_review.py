"""
审核页面 — 查看匹配结果，挑选要投递的岗位
"""

import streamlit as st
import pandas as pd
from pathlib import Path

st.title("📊 审核与挑选")

# 收集所有待审核的岗位
all_jobs = []

# 从海外搜索导入
if st.session_state.get("jobs_found"):
    for j in st.session_state.jobs_found:
        if isinstance(j, dict):
            all_jobs.append(j)

# 从手动粘贴导入
if st.session_state.get("manual_jobs"):
    for item in st.session_state.manual_jobs:
        job = item["job"]
        job["_match_score"] = item["match"].get("overall_score", 0)
        all_jobs.append(job)

if not all_jobs:
    st.info("还没有发现岗位。请先去「发现」页面搜索职位或粘贴JD。")

    st.markdown("""
    ### 快速操作

    1. 去 **发现 → 海外平台搜索**，搜索LinkedIn/Indeed等平台
    2. 去 **发现 → 公司发现**，让AI推荐值得投递的公司
    3. 去 **发现 → 手动粘贴JD**，粘贴你从Boss直聘等平台找到的岗位
    """)
else:
    st.subheader(f"共 {len(all_jobs)} 个待审核岗位")

    # 筛选选项
    col1, col2, col3 = st.columns(3)
    with col1:
        filter_company = st.text_input("🔍 按公司筛选", placeholder="输入公司名")
    with col2:
        sort_by = st.selectbox("排序方式", ["匹配度", "时间", "公司名"])
    with col3:
        min_score = st.slider("最低匹配度", 0, 100, 0, 5)

    # 构建 DataFrame
    rows = []
    for j in all_jobs:
        rows.append({
            "公司": j.get("company", "?"),
            "职位": j.get("title", "?"),
            "地点": j.get("location", ""),
            "平台": j.get("source_platform", j.get("source", "")),
            "匹配度": j.get("_match_score", j.get("overall_score", 0)),
        })

    df = pd.DataFrame(rows)

    # 排序
    if sort_by == "匹配度":
        df = df.sort_values("匹配度", ascending=False)
    elif sort_by == "公司名":
        df = df.sort_values("公司")
    else:
        pass  # 保持原序

    # 筛选
    if filter_company:
        df = df[df["公司"].str.contains(filter_company, case=False, na=False)]
    if min_score > 0:
        df = df[df["匹配度"] >= min_score]

    st.dataframe(df, use_container_width=True, height=400)

    # 批量操作
    st.markdown("---")
    st.subheader("逐个审核")

    # 初始化选中列表
    if "selected_indices" not in st.session_state:
        st.session_state.selected_indices = set()

    for i, job in enumerate(all_jobs):
        company = job.get("company", "?")
        title = job.get("title", "?")
        location = job.get("location", "")
        score = job.get("_match_score", job.get("overall_score", 0))
        desc = job.get("description", "")

        with st.expander(f"#{i+1} [{score}分] {company} — {title} ({location})"):
            col_a, col_b, col_c = st.columns([6, 1, 1])

            with col_a:
                if desc:
                    st.markdown(desc[:800] + ("..." if len(desc) > 800 else ""))
                job_url = job.get("job_url", "")
                if job_url:
                    st.markdown(f"[🔗 查看原链接]({job_url})")

            with col_b:
                if st.button("✅ 选择", key=f"select_{i}", use_container_width=True):
                    st.session_state.selected_indices.add(i)
                    st.rerun()

            with col_c:
                if st.button("❌ 跳过", key=f"skip_{i}", use_container_width=True):
                    st.session_state.selected_indices.discard(i)
                    st.rerun()

    # 已选汇总
    if st.session_state.selected_indices:
        st.markdown("---")
        st.subheader(f"✅ 已选 {len(st.session_state.selected_indices)} 个岗位")

        selected = [all_jobs[i] for i in sorted(st.session_state.selected_indices)]

        for s in selected:
            st.markdown(f"- **{s.get('company')}** — {s.get('title')} ({s.get('location', '')})")

        if st.button("🚀 去生成简历", use_container_width=True, type="primary"):
            st.session_state.selected_jobs = selected
            st.success(f"已选择 {len(selected)} 个岗位，请前往「生成」页面")
            st.switch_page("pages/04_generator.py")

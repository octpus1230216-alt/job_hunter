"""
审核页面 — 查看匹配结果，挑选要投递的岗位
"""

import streamlit as st
import pandas as pd

st.title("📊 审核挑选")

# 收集所有待审核的岗位
all_jobs = []

if st.session_state.get("jobs_found"):
    for j in st.session_state.jobs_found:
        if isinstance(j, dict):
            all_jobs.append(j)

if st.session_state.get("manual_jobs"):
    for item in st.session_state.manual_jobs:
        job = item["job"]
        job["_match_score"] = item["match"].get("overall_score", 0)
        all_jobs.append(job)

if not all_jobs:
    st.info("还没有发现岗位。请先去「🔍 发现职位」页面搜索职位或粘贴JD。")
    st.markdown("""
    ### 快速操作
    1. 去 **🔍 发现职位 → 海外平台搜索**，搜索LinkedIn/Indeed等平台
    2. 去 **🔍 发现职位 → 公司发现**，让AI推荐值得投递的公司
    3. 去 **🔍 发现职位 → 手动粘贴JD**，粘贴从Boss直聘等找到的岗位
    """)
    st.stop()

st.subheader(f"共 {len(all_jobs)} 个待审核岗位")

# 筛选
col1, col2 = st.columns(2)
with col1:
    filter_company = st.text_input("🔍 按公司筛选", placeholder="输入公司名")
with col2:
    sort_by = st.selectbox("排序方式", ["按匹配度", "按时间", "按公司名"])

min_score = st.slider("最低匹配度过滤", 0, 100, 0, 5)

# 构建 DataFrame（海外岗位匹配度显示为"未匹配"）
rows = []
for j in all_jobs:
    score = j.get("_match_score", j.get("overall_score", None))
    rows.append({
        "公司": j.get("company", "?"),
        "职位": j.get("title", "?"),
        "地点": j.get("location", ""),
        "平台": j.get("source_platform", j.get("source", "")),
        "匹配度": score if score is not None else "未匹配",
        "_score": score if score is not None else 0,
    })

df = pd.DataFrame(rows)

if sort_by == "按匹配度":
    df = df.sort_values("_score", ascending=False)
elif sort_by == "按公司名":
    df = df.sort_values("公司")

if filter_company:
    df = df[df["公司"].str.contains(filter_company, case=False, na=False)]
if min_score > 0:
    df = df[df["_score"] >= min_score]

st.dataframe(df[["公司", "职位", "地点", "平台", "匹配度"]], use_container_width=True, height=400)

# ============================================================
# 逐个审核
# ============================================================
st.markdown("---")
st.subheader("逐个审核岗位")

if "selected_indices" not in st.session_state:
    st.session_state.selected_indices = []

for i, job in enumerate(all_jobs):
    company = job.get("company", "?")
    title = job.get("title", "?")
    location = job.get("location", "")
    score = job.get("_match_score", job.get("overall_score", "?"))
    desc = job.get("description", "")
    job_url = job.get("job_url", "")

    is_selected = i in st.session_state.selected_indices

    with st.expander(
        f"{'✅' if is_selected else '⬜'} #{i+1} [{score}分] {company} — {title} ({location})",
    ):
        if desc:
            st.markdown(desc[:800] + ("..." if len(desc) > 800 else ""))
        if job_url:
            st.markdown(f"[🔗 查看原链接]({job_url})")

        col_a, col_b = st.columns(2)
        with col_a:
            if not is_selected:
                if st.button("✅ 选择此岗位", key=f"sel_{i}", use_container_width=True):
                    if i not in st.session_state.selected_indices:
                        st.session_state.selected_indices.append(i)
                    st.rerun()
            else:
                if st.button("↩️ 取消选择", key=f"unsel_{i}", use_container_width=True):
                    st.session_state.selected_indices.remove(i)
                    st.rerun()
        with col_b:
            if not is_selected:
                if st.button("❌ 跳过", key=f"skip_{i}", use_container_width=True):
                    pass  # 不做任何操作，只是关闭 expander

# ============================================================
# 已选汇总
# ============================================================
if st.session_state.selected_indices:
    st.markdown("---")
    st.subheader(f"✅ 已选 {len(st.session_state.selected_indices)} 个岗位")

    selected = [all_jobs[i] for i in st.session_state.selected_indices]
    for s in selected:
        st.markdown(f"- **{s.get('company')}** — {s.get('title')} ({s.get('location', '')})")

    if st.button("🚀 确认选择，去生成简历", use_container_width=True, type="primary"):
        st.session_state.selected_jobs = selected
        st.success(f"已选择 {len(selected)} 个岗位，请前往「✨ 生成简历」页面")
        st.switch_page("pages/04_✨_生成简历.py")

"""
追踪页面 — 投递进度管理
"""

import streamlit as st
import pandas as pd
from pathlib import Path
from modules.tracker import ApplicationTracker

st.title("📈 投递追踪")

tracker = ApplicationTracker()
applications = tracker.load()

# ============================================================
# 统计概览
# ============================================================
stats = tracker.get_stats()

col1, col2, col3, col4 = st.columns(4)
col1.metric("总投递", stats["total"])
col2.metric("进行中", stats["active"])
col3.metric("Offer", stats["by_status"].get("offer", 0))
col4.metric("已完成", stats["by_status"].get("accepted", 0) + stats["by_status"].get("declined", 0))

# 状态流程条
st.markdown("---")
statuses_order = ["saved", "applied", "screening", "interview_1", "interview_2",
                  "interview_3", "interview_final", "offer", "accepted", "rejected"]
status_colors = {
    "saved": "gray", "applied": "blue", "screening": "orange",
    "interview_1": "orange", "interview_2": "orange", "interview_3": "orange",
    "interview_final": "orange", "offer": "green", "accepted": "green",
    "rejected": "red", "withdrawn": "red", "declined": "red",
}

cols = st.columns(len(statuses_order))
for col, status in zip(cols, statuses_order):
    count = stats["by_status"].get(status, 0)
    color = status_colors.get(status, "gray")
    with col:
        st.metric(
            ApplicationTracker.STATUSES.get(status, status),
            count,
            delta=None,
        )

# ============================================================
# 投递记录列表
# ============================================================
st.markdown("---")
st.subheader(f"📋 投递记录 ({len(applications)})")

if applications:
    # 构建表格
    rows = []
    for app in sorted(applications, key=lambda x: x["created_at"], reverse=True):
        rows.append({
            "ID": app["id"],
            "公司": app["company"],
            "职位": app["title"],
            "匹配度": app.get("match_score", "-"),
            "状态": ApplicationTracker.STATUSES.get(app["status"], app["status"]),
            "状态代码": app["status"],
            "更新时间": app["updated_at"][:10],
        })

    df = pd.DataFrame(rows)
    st.dataframe(
        df[["公司", "职位", "匹配度", "状态", "更新时间"]],
        use_container_width=True,
        height=400,
    )

    # 状态更新
    st.markdown("---")
    st.subheader("更新投递状态")

    col1, col2 = st.columns([1, 2])
    with col1:
        app_id = st.selectbox(
            "选择记录",
            [a["id"] for a in applications],
            format_func=lambda x: f"[{x}] {next((a['company'] for a in applications if a['id'] == x), '')}"
        )
    with col2:
        current_status = next((a["status"] for a in applications if a["id"] == app_id), "applied")
        new_status = st.selectbox(
            "更新状态",
            list(ApplicationTracker.STATUSES.keys()),
            format_func=lambda x: ApplicationTracker.STATUSES[x],
            index=list(ApplicationTracker.STATUSES.keys()).index(current_status)
                       if current_status in ApplicationTracker.STATUSES else 0,
        )

    note = st.text_input("备注（可选）", placeholder="例如：面试官反馈、下一步安排")

    if st.button("💾 更新状态", use_container_width=True):
        if app_id:
            tracker.update_status(app_id, new_status, note)
            st.success(f"状态已更新为: {ApplicationTracker.STATUSES[new_status]}")
            st.rerun()

    # 删除记录
    if st.button("🗑️ 删除此记录", use_container_width=True):
        tracker.delete(app_id)
        st.success("记录已删除")
        st.rerun()

else:
    st.info("还没有投递记录。")

    # 快速添加
    st.subheader("快速添加投递")

    with st.form("quick_add"):
        company = st.text_input("公司名")
        title = st.text_input("职位名")
        job_url = st.text_input("JD链接（可选）")
        submitted = st.form_submit_button("添加", use_container_width=True)

        if submitted:
            if company and title:
                tracker.add(company, title, job_url)
                st.success("已添加！")
                st.rerun()
            else:
                st.error("请填写公司名和职位名")

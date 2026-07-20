"""
审核页面 — 查看匹配/决策结果，挑选要投递的岗位。

Phase 0 + Phase 1：
- 从「🔍 发现职位」写入的 st.session_state.all_jobs 读取（修复原 jobs_found/manual_jobs 断点）
- 可一键运行 AI 决策通道（matcher.decide_single）：判断是否建议投递 + 真实过筛概率 + 理由
- 默认按「过筛概率」排序（实验证其比纯匹配度更贴近真实结果，AUC≈0.64）
- 卡片展示公司竞争力档位（顶级厂折扣内置在决策里）
- 选择结果写入 st.session_state.selected_jobs，供「✨ 生成简历」使用
"""

import streamlit as st
import pandas as pd

st.title("📊 审核挑选")

# ============================================================
# 收集待审核岗位（来自发现页的 all_jobs）
# ============================================================
all_jobs = list(st.session_state.get("all_jobs", []) or [])

if not all_jobs:
    st.info("还没有发现岗位。请先去「🔍 发现职位」页面搜索职位或粘贴 JD。")
    st.markdown(
        """
    ### 快速操作
    1. 去 **🔍 发现职位 → 海外平台搜索**，搜索 LinkedIn/Indeed 等平台
    2. 去 **🔍 发现职位 → 国内平台直达搜索**，用 CDP Chrome 采集 Boss直聘
    3. 去 **🔍 发现职位 → 手动粘贴 JD**，粘贴从任意平台找到的岗位
    """
    )
    st.stop()

if not st.session_state.get("resume_parsed"):
    st.warning("⚠️ 未检测到简历，决策通道无法运行。请先在 ⚙️ 配置 上传简历（匹配度仍基于发现页已算结果展示）。")


# ============================================================
# 辅助函数
# ============================================================
def _score_of(job: dict) -> int:
    """发现页已算的匹配度（七维/5维 overall_score）。"""
    m = job.get("_match") or {}
    return int(m.get("overall_score", 0) or 0)


def _decision_of(job: dict) -> dict:
    """决策通道结果 {apply, pass_prob, reason, competition_level}。"""
    return job.get("_decision") or {}


def _sel_key(job: dict) -> str:
    """稳定选择键（公司|职位|链接），避免排序/筛选后位置错位。"""
    return f"{job.get('company', '')}|{job.get('title', '')}|{job.get('job_url', '')}"


def _build_table(jobs: list) -> pd.DataFrame:
    """构造审核概览表。"""
    rows = []
    for j in jobs:
        dec = _decision_of(j)
        pp = dec.get("pass_prob")
        comp = dec.get("competition_level") or (j.get("_match", {}) or {}).get("competition") or ""
        rows.append({
            "公司": j.get("company", "?"),
            "职位": j.get("title", "?"),
            "地点": j.get("location", ""),
            "平台": j.get("source_platform", j.get("source", "")),
            "竞争力": comp,
            "过筛概率": pp if pp is not None else "-",
            "匹配度": _score_of(j),
            "建议": ("✅投" if dec.get("apply") == 1 else "❌不投") if pp is not None else "-",
        })
    return pd.DataFrame(rows)


if "selected_keys" not in st.session_state:
    st.session_state.selected_keys = set()


# ============================================================
# 运行 AI 决策通道
# ============================================================
has_decision = any(job.get("_decision") for job in all_jobs)

st.subheader(f"共 {len(all_jobs)} 个待审核岗位")

run_col, info_col = st.columns([2, 2])
with run_col:
    if st.button("🤖 运行 AI 决策排序（建议投递 + 过筛概率）",
                 use_container_width=True, type="primary"):
        if not st.session_state.get("llm_client"):
            st.error("请先在 ⚙️ 配置 设置 API Key")
        elif not st.session_state.get("resume_parsed"):
            st.error("请先在 ⚙️ 配置 上传简历")
        else:
            from modules.matcher import JobMatcher
            matcher = JobMatcher(st.session_state.llm_client)
            prefs = st.session_state.get("config", {}).get("preferences", {})
            with st.status("AI 正在决策每个岗位...", expanded=True) as status:
                for i, job in enumerate(all_jobs):
                    status.write(f"({i + 1}/{len(all_jobs)}) {job.get('company', '?')} — {job.get('title', '?')}")
                    try:
                        dec = matcher.decide_single(st.session_state.resume_parsed, job, prefs)
                    except Exception as e:  # 单条失败不中断
                        dec = {"apply": 0, "pass_prob": 0,
                               "reason": f"决策失败: {str(e)[:120]}", "competition_level": ""}
                    job["_decision"] = dec
                st.session_state.all_jobs = all_jobs
                status.update(label="决策完成！已按过筛概率排序", state="complete")
                st.rerun()

with info_col:
    st.caption(
        "决策通道 = 让 AI 直接判断「是否建议投递 + 真实过筛概率」，并内置对顶级厂的竞争折扣。"
        "实验显示它比纯匹配度更贴近真实录取（AUC≈0.64）。未运行时按匹配度排序。"
    )

# 决策结果概览
if has_decision:
    n_apply = sum(1 for j in all_jobs if _decision_of(j).get("apply") == 1)
    st.success(f"🤖 已决策：其中 **{n_apply}** 个建议投递（apply=1），{len(all_jobs) - n_apply} 个不建议。")


# ============================================================
# 筛选 + 排序
# ============================================================
f1, f2 = st.columns(2)
with f1:
    filter_company = st.text_input("🔍 按公司/职位筛选", placeholder="输入关键词")
with f2:
    sort_options = ["按过筛概率", "按匹配度", "按公司名", "按时间"]
    sort_by = st.selectbox("排序方式", sort_options, index=0 if has_decision else 1)

min_score = st.slider("最低分过滤（过筛概率或匹配度）", 0, 100, 0, 5)


def _primary(job: dict) -> float:
    """当前排序口径下的主分数，用于滑块过滤。"""
    if sort_by == "按过筛概率":
        p = _decision_of(job).get("pass_prob")
        return float(p) if p is not None else -1.0
    return float(_score_of(job))


# 排序（按时间 = 保持插入顺序，发现页新岗位插在最前）
if sort_by == "按公司名":
    all_jobs.sort(key=lambda j: (j.get("company", "") or "").lower())
elif sort_by == "按过筛概率":
    all_jobs.sort(key=lambda j: _decision_of(j).get("pass_prob", -1), reverse=True)
elif sort_by == "按匹配度":
    all_jobs.sort(key=_score_of, reverse=True)
# 按时间：不动

# 过滤
filtered = [j for j in all_jobs if _primary(j) >= min_score]
if filter_company:
    kw = filter_company.lower()
    filtered = [
        j for j in filtered
        if kw in (j.get("company", "") + " " + j.get("title", "")).lower()
    ]

st.dataframe(
    _build_table(filtered),
    use_container_width=True, height=380, hide_index=True,
) if filtered else st.info("没有符合筛选条件的岗位。")


# ============================================================
# 逐个审核
# ============================================================
st.markdown("---")
st.subheader("逐个审核岗位")

for job in filtered:
    company = job.get("company", "?")
    title = job.get("title", "?")
    location = job.get("location", "")
    industry_tag = job.get("_industry_tag", "")
    dec = _decision_of(job)
    score = _score_of(job)
    pass_prob = dec.get("pass_prob")
    comp = dec.get("competition_level") or (job.get("_match", {}) or {}).get("competition") or ""

    key = _sel_key(job)
    is_selected = key in st.session_state.selected_keys

    # 标题行：竞争力徽章 + 主分数
    mark = "✅" if is_selected else "⬜"
    badge = f" · 竞争力[{comp}]" if comp else ""
    if pass_prob is not None:
        head = (mark + " " + str(company) + " - " + str(title) + " (" + str(location)
                + ")  过筛概率 " + str(pass_prob) + badge)
    else:
        head = (mark + " " + str(company) + " - " + str(title) + " (" + str(location)
                + ")  匹配度 " + str(score) + badge)

    with st.expander(head):
        desc = job.get("description", "")
        if desc:
            st.markdown(desc[:800] + ("..." if len(desc) > 800 else ""))
        if job.get("job_url"):
            st.markdown(f"[🔗 查看原链接]({job.get('job_url')})")

        if pass_prob is not None:
            st.markdown(f"**🤖 决策**：{'建议投递 ✅' if dec.get('apply') == 1 else '不建议 ❌'} ｜ "
                        f"过筛概率 **{pass_prob}** ｜ 理由：{dec.get('reason', '-')}")
        else:
            st.caption(f"匹配度 {score}/100（点上方「运行 AI 决策」可获过筛概率与建议）")

        if industry_tag:
            st.caption(f"行业标签：{industry_tag}")

        c_a, c_b = st.columns(2)
        with c_a:
            if not is_selected:
                if st.button("✅ 选择此岗位", key=f"sel_{key}", use_container_width=True):
                    st.session_state.selected_keys.add(key)
                    st.rerun()
            else:
                if st.button("↩️ 取消选择", key=f"unsel_{key}", use_container_width=True):
                    st.session_state.selected_keys.discard(key)
                    st.rerun()
        with c_b:
            if not is_selected:
                if st.button("❌ 跳过", key=f"skip_{key}", use_container_width=True):
                    pass  # 关闭 expander，无操作


# ============================================================
# 已选汇总
# ============================================================
selected = [j for j in all_jobs if _sel_key(j) in st.session_state.selected_keys]
if selected:
    st.markdown("---")
    st.subheader(f"✅ 已选 {len(selected)} 个岗位")

    for s in selected:
        dec = _decision_of(s)
        pp = dec.get("pass_prob")
        suffix = f" ｜ 过筛概率 {pp}" if pp is not None else ""
        st.markdown(f"- **{s.get('company')}** — {s.get('title')} ({s.get('location', '')}){suffix}")

    if st.button("🚀 确认选择，去生成简历", use_container_width=True, type="primary"):
        st.session_state.selected_jobs = selected
        st.success(f"已选择 {len(selected)} 个岗位，请前往「✨ 生成简历」页面")
        st.switch_page("pages/04_✨_生成简历.py")

"""
海投页面 — 批量投递流（意见#3）。

任务流：选简历 → 自动批量匹配岗位 → 批量过审 → 标记已投。
岗位来源：
- 「🔍 发现职位」已采集到 st.session_state.all_jobs 的岗位（主来源）
- 或在下方批量粘贴 JD（每个岗位之间用 --- 分隔）作为补充
复用模块：
- modules.matcher.JobMatcher.decide_batch   （批量决策通道）
- modules.generator.ResumeGenerator.generate_all （可选：为选中岗位生成简历/求职信）
- modules.tracker.ApplicationTracker.add            （批量写入投递追踪）
数字分已内部化，本页只展示决策通道结论（过筛概率 + 建议）。
"""

import streamlit as st
from pathlib import Path

from modules.auth import require_auth
require_auth()

st.title("🌊 海投（批量投递）")
st.caption("把简历对一批岗位批量跑决策通道，勾选你认可的，一次性标记已投。适合广撒网的岗位。")

# 海投作为「任务枢纽」：发现/推荐 → 审核 → 生成 → 投递（意见 F-7）
st.info("🧭 海投流程：① 采集岗位（推荐岗位 / 发现职位）→ ② 下面批量决策 → ③ 勾选并标记已投。")
c1, c2 = st.columns(2)
with c1:
    st.page_link("pages/10_🌟_推荐岗位.py", label="🌟 推荐岗位（每日 15 条）", icon="🌟")
with c2:
    st.page_link("pages/04_🔍_发现职位.py", label="🔍 发现职位（采集岗位池）", icon="🔍")

# ============================================================
# 前置检查
# ============================================================
if not st.session_state.get("resume_parsed"):
    st.error("⚠️ 还没上传简历。请先去「⚙️ 配置」上传并解析主简历，海投才能运行。")
    st.stop()

resume = st.session_state.resume_parsed
config = st.session_state.get("config", {})
bilingual_default = config.get("output", {}).get("bilingual", True)
prefs = config.get("preferences", {})

# 岗位池：发现页写入的 all_jobs（主来源）
pool = list(st.session_state.get("all_jobs", []) or [])

# ============================================================
# 补充：批量粘贴 JD
# ============================================================
with st.expander("➕ 补充岗位：批量粘贴 JD（每个岗位之间用 --- 分隔）", expanded=False):
    pasted = st.text_area("批量 JD", height=200,
                          placeholder="公司：Acme\n职位：Backend Engineer\nJD 内容…\n---\n公司：Globex\n职位：…")
    if st.button("解析并加入岗位池"):
        if pasted:
            blocks = [b.strip() for b in pasted.split("---") if b.strip()]
            added = 0
            for b in blocks:
                lines = b.splitlines()
                comp = ""; tit = ""; desc_lines = []
                for ln in lines:
                    if ln.startswith("公司") or ln.lower().startswith("company"):
                        comp = ln.split("：", 1)[-1].split(":", 1)[-1].strip()
                    elif ln.startswith("职位") or ln.lower().startswith("title"):
                        tit = ln.split("：", 1)[-1].split(":", 1)[-1].strip()
                    else:
                        desc_lines.append(ln)
                desc = "\n".join(desc_lines).strip()
                if not tit and desc:
                    tit = desc.splitlines()[0][:40] if desc else "未命名岗位"
                pool.append({
                    "company": comp or "未知公司", "title": tit or "未命名岗位",
                    "location": "", "description": desc, "job_url": "",
                    "source_platform": "海投粘贴",
                })
                added += 1
            st.session_state.all_jobs = pool
            if added:
                st.success(f"已加入 {added} 个岗位到岗位池。")
                st.rerun()
        else:
            st.warning("请先粘贴 JD。")


if not pool:
    st.info("岗位池为空。请先去「🔍 发现职位」搜索/粘贴岗位，或上面批量粘贴 JD。")
    st.stop()

st.subheader(f"岗位池：{len(pool)} 个")
st.page_link("pages/04_🔍_发现职位.py", label="去 🔍 发现职位 采集更多岗位", icon="🔍")


# ============================================================
# 批量决策通道
# ============================================================
if st.button("🤖 批量决策（建议投 + 过筛概率）", use_container_width=True, type="primary"):
    if not st.session_state.get("llm_client"):
        st.error("请先在 ⚙️ 配置 设置 API Key")
    else:
        from modules.matcher import JobMatcher
        matcher = JobMatcher(st.session_state.llm_client)
        with st.status("AI 正在批量决策…", expanded=True) as status:
            decisions = matcher.decide_batch(resume, pool, prefs,
                                             progress_callback=lambda m: status.write(m))
            for job, dec in zip(pool, decisions):
                job["_decision"] = dec
            st.session_state.all_jobs = pool
            status.update(label="批量决策完成", state="complete")
        st.rerun()

min_pp = st.slider("最低过筛概率过滤", 0, 100, 0, 5)

filtered = []
for j in pool:
    dec = j.get("_decision") or {}
    pp = dec.get("pass_prob")
    if (pp if pp is not None else -1) >= min_pp:
        filtered.append(j)

st.caption(f"符合过滤：{len(filtered)} / {len(pool)} 个"
           + ("（先点上方「批量决策」可显示过筛概率）" if not any(j.get('_decision') for j in pool) else ""))


# ============================================================
# 逐条勾选过审
# ============================================================
if "haitou_selected" not in st.session_state:
    st.session_state.haitou_selected = set()


def _sel_key(job: dict) -> str:
    return f"{job.get('company', '')}|{job.get('title', '')}|{job.get('job_url', '')}"


for job in filtered:
    dec = job.get("_decision") or {}
    pp = dec.get("pass_prob")
    comp = dec.get("competition_level") or (job.get("_match", {}) or {}).get("competition") or ""
    key = _sel_key(job)
    head = (f"{job.get('company', '?')} — {job.get('title', '?')}"
            + (f" ｜ 过筛概率 {pp}" if pp is not None else "")
            + (f" ｜ 竞争力[{comp}]" if comp else ""))
    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown(head)
        if pp is not None:
            st.caption(f"🤖 {'建议投递 ✅' if dec.get('apply') == 1 else '不建议 ❌'} ｜ {dec.get('reason', '-')}")
    with c2:
        checked = st.checkbox("选", key=f"ht_{key}", value=key in st.session_state.haitou_selected)
        if checked:
            st.session_state.haitou_selected.add(key)
        else:
            st.session_state.haitou_selected.discard(key)

selected_jobs = [j for j in filtered if _sel_key(j) in st.session_state.haitou_selected]

st.markdown(f"**已选 {len(selected_jobs)} 个**")

gen_too = st.toggle("同时为选中岗位生成简历 + 求职信（消耗较多 AI 调用）",
                    value=False)

if st.button("✅ 标记选中为已投", use_container_width=True, type="primary",
             disabled=not selected_jobs):
    try:
        from modules.tracker import ApplicationTracker
        from modules.style_analyzer import StyleAnalyzer
        from modules.generator import ResumeGenerator
        tracker = ApplicationTracker()
        llm = st.session_state.get("llm_client")
        analyzer = StyleAnalyzer(llm) if llm else None
        generator = ResumeGenerator(llm, analyzer) if llm else None

        done = 0
        for job in selected_jobs:
            dec = job.get("_decision") or {}
            pp = dec.get("pass_prob")
            tracker.add(
                job.get("company", ""), job.get("title", ""),
                job_url=job.get("job_url", ""),
                source=job.get("source_platform", job.get("source", "海投")),
                status="applied",
                competition_level=dec.get("competition_level", ""),
                llm_apply=dec.get("apply"),
                llm_pass_prob=pp if isinstance(pp, int) else None,
                llm_reason=dec.get("reason", ""),
            )
            done += 1
            if gen_too and generator:
                with st.status(f"生成 {job.get('company')} 简历…", expanded=False):
                    generator.generate_all(resume, job, bilingual=bilingual_default)
        st.success(f"已标记 {done} 个岗位为「已投递」，记录进入「📈 投递追踪」。")
        st.session_state.haitou_selected = set()
        st.page_link("pages/07_📈_投递追踪.py", label="去 📈 投递追踪 查看", icon="📈")
    except Exception as e:
        st.error(f"写入追踪失败：{str(e)[:160]}")
elif not selected_jobs:
    st.caption("勾选上方岗位后，这里可以一次性标记已投。")

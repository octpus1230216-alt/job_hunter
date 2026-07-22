"""
精投页面 — 针对「单个目标岗位」的精准投递流（意见#2）。

任务流：贴一个 JD + 你的简历 → AI 找不匹配 → 改简历 + 写 Cover Letter → 手动投递 → 标记已投。
复用现有模块：
- modules.matcher.JobMatcher.decide_single   （决策通道：建议投/不投 + 过筛概率 + 理由）
- modules.matcher 的差距分析（内联 chat_json）  （找不匹配点）
- modules.generator.ResumeGenerator.generate_all （定制简历 + Cover Letter + 速查卡）
- modules.tracker.ApplicationTracker.add            （写入投递追踪，回灌校准库）

数字匹配分已内部化（见 Phase B），本页只展示决策通道结论。
"""

import streamlit as st
from pathlib import Path

from modules.auth import require_auth
require_auth()

st.title("🎯 精投（针对单个目标岗位）")
st.caption("贴一个 JD + 你的简历 → AI 找不匹配 → 改简历 + 写 Cover Letter → 标记已投。适合你最想进的那几家公司。")

# ============================================================
# 前置检查
# ============================================================
if not st.session_state.get("resume_parsed"):
    st.error("⚠️ 还没上传简历。请先去「⚙️ 配置」上传并解析主简历，精投才能运行。")
    st.stop()

resume = st.session_state.resume_parsed
config = st.session_state.get("config", {})
bilingual_default = config.get("output", {}).get("bilingual", True)
prefs = config.get("preferences", {})


# ============================================================
# 差距分析（内联，复用 LLM 决策通道能力）
# ============================================================
GAP_SYSTEM_PROMPT = (
    "你是求职匹配诊断助手。对比候选人简历与目标岗位 JD，找出「不匹配/差距点」，"
    "并给出可落地的补齐建议。只基于真实信息，不编造。输出严格 JSON。"
)


def _analyze_gaps(job: dict) -> dict:
    """对比简历与 JD，返回不匹配点列表（不展示任何数字分）。"""
    llm = st.session_state.get("llm_client")
    if llm is None:
        return {"gaps": [], "overall_fit": "未知", "summary": "未配置 AI，无法分析。"}
    from modules.matcher import JobMatcher
    matcher = JobMatcher(llm)
    resume_summary = matcher._summarize_resume(resume)
    job_summary = matcher._summarize_job(job)
    user_prompt = f"""请诊断候选人与目标岗位的差距。

=== 候选人简历摘要 ===
{resume_summary}

=== 目标岗位 JD ===
公司：{job.get('company', '')}
职位：{job.get('title', '')}
JD：
{job_summary}

请输出 JSON：
{{"overall_fit":"高/中/低",
  "summary":"一句话总体判断",
  "gaps":[{{"area":"差距领域（如 技能/经验年限/学历/行业）",
            "detail":"具体差距描述",
            "suggestion":"如何补齐或如何在简历中化解"}}]}}"""
    try:
        return llm.chat_json(GAP_SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        return {"gaps": [], "overall_fit": "未知", "summary": f"分析失败：{str(e)[:120]}"}


# ============================================================
# 步骤 1：输入目标岗位（贴 JD）
# ============================================================
st.subheader("① 输入目标岗位（粘贴 JD）")

with st.form("jingtou_job_form"):
    col1, col2 = st.columns(2)
    with col1:
        company = st.text_input("公司名 *", placeholder="例如：Anthropic", key="jt_company")
    with col2:
        title = st.text_input("职位名 *", placeholder="例如：ML Engineer", key="jt_title")
    location = st.text_input("工作地点", placeholder="例如：San Francisco, CA", key="jt_loc")
    jd_text = st.text_area("职位描述（JD）*", height=260,
                           placeholder="把招聘页的完整 JD 粘贴到这里…", key="jt_jd")
    submitted = st.form_submit_button("➡️ 载入岗位", use_container_width=True, type="primary")
    if submitted:
        if company and title and jd_text:
            st.session_state.jingtou_job = {
                "company": company, "title": title,
                "location": location, "description": jd_text,
                "job_url": "", "source_platform": "精投",
            }
            st.session_state.jingtou_decision = None
            st.session_state.jingtou_gaps = None
            st.success("岗位已载入，下面可以开始 AI 分析。")
            st.rerun()
        else:
            st.error("请填写带 * 的必填项（公司名 / 职位名 / JD）")

job = st.session_state.get("jingtou_job")
if not job:
    st.info("在上方粘贴一个你最想投的岗位 JD，开始精投流程。")
    st.stop()


# ============================================================
# 步骤 2：AI 找不匹配 + 决策通道
# ============================================================
st.subheader("② AI 找不匹配 + 决策")

c_run, c_info = st.columns([2, 2])
with c_run:
    if st.button("🤖 分析不匹配 & 决策是否建议投",
                 use_container_width=True, type="primary"):
        if not st.session_state.get("llm_client"):
            st.error("请先在 ⚙️ 配置 设置 API Key")
        else:
            from modules.matcher import JobMatcher
            matcher = JobMatcher(st.session_state.llm_client)
            with st.status("AI 正在分析…", expanded=True) as status:
                status.write("判断「是否建议投递 + 真实过筛概率」…")
                decision = matcher.decide_single(resume, job, prefs)
                st.session_state.jingtou_decision = decision
                status.write("对比简历与 JD，找出不匹配点…")
                gaps = _analyze_gaps(job)
                st.session_state.jingtou_gaps = gaps
                status.update(label="分析完成", state="complete")
            st.rerun()

with c_info:
    st.caption(
        "决策通道 = 让 AI 直接判断「是否建议投 + 真实过筛概率」，并内置对顶级厂的竞争折扣，"
        "比纯匹配度更贴近真实录取。不匹配分析只给文字建议，不显示数字分。"
    )

decision = st.session_state.get("jingtou_decision")
gaps = st.session_state.get("jingtou_gaps")

if decision:
    pp = decision.get("pass_prob")
    apply_flag = decision.get("apply")
    comp = decision.get("competition_level", "")
    st.markdown(f"**🤖 决策**：{'建议投递 ✅' if apply_flag == 1 else '不建议 ❌'}"
                + (f" ｜ 过筛概率 **{pp}**" if pp is not None else "")
                + (f" ｜ 竞争力[{comp}]" if comp else ""))
    st.markdown(f"**理由**：{decision.get('reason', '-')}")

if gaps:
    fit = gaps.get("overall_fit", "")
    st.markdown(f"**总体匹配**：{fit} ｜ {gaps.get('summary', '')}")
    gl = gaps.get("gaps") or []
    if gl:
        st.markdown("**🔍 不匹配点 / 差距：**")
        for g in gl:
            st.markdown(f"- **{g.get('area', '')}**：{g.get('detail', '')}")
            if g.get("suggestion"):
                st.caption(f"↳ 化解建议：{g.get('suggestion')}")
    else:
        st.success("未检出明显不匹配点。")


# ============================================================
# 步骤 3：生成定制简历 + Cover Letter
# ============================================================
st.markdown("---")
st.subheader("③ 生成定制简历 & 求职信")

bilingual = st.toggle("中英双语", value=bilingual_default,
                      help="开启后同时生成中英文简历与求职信")

if st.button("🎨 生成定制简历 + 求职信", use_container_width=True, type="primary"):
    if not st.session_state.get("llm_client"):
        st.error("请先在 ⚙️ 配置 设置 API Key")
    else:
        from modules.style_analyzer import StyleAnalyzer
        from modules.generator import ResumeGenerator
        llm = st.session_state.llm_client
        analyzer = StyleAnalyzer(llm)
        generator = ResumeGenerator(llm, analyzer)
        with st.status("正在为这个岗位定制…", expanded=True) as status:
            status.write("🎨 分析公司风格…")
            result = generator.generate_all(resume, job, bilingual=bilingual)
            st.session_state.jingtou_result = result
            status.update(label="生成完成！", state="complete")
        st.rerun()

result = st.session_state.get("jingtou_result")
if result:
    style = result.get("style", {})
    customized = result.get("customized_resume", {})
    cl = result.get("cover_letter", {})
    files = result.get("resume_files", {})

    st.markdown(f"**🏷️ 风格**：{style.get('style_category', '?')}（{style.get('tone', '?')}）")

    with st.expander("📄 简历摘要预览"):
        st.markdown(f"**摘要**：{customized.get('summary', '')[:240]}…")
        if customized.get("summary_en"):
            st.markdown(f"**Summary (EN)**：{customized.get('summary_en', '')[:240]}…")

    with st.expander("📝 求职信预览"):
        if cl.get("body"):
            st.markdown(f"**主题**：{cl.get('subject', '')}")
            st.markdown(cl.get("body", "")[:300] + "…")
        if cl.get("body_en"):
            st.markdown(f"**Subject (EN)**：{cl.get('subject_en', '')}")
            st.markdown(cl.get("body_en", "")[:300] + "…")

    st.markdown("### 📁 下载文件")
    dl_cols = st.columns(len(files) + 1)
    ci = 0
    for lang, fpath in files.items():
        lang_label = "中文" if lang == "zh" else "英文" if lang == "en" else lang
        with dl_cols[ci]:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            st.download_button(f"⬇️ 简历({lang_label})", content,
                               file_name=Path(fpath).name, mime="text/html",
                               key=f"jt_dl_{lang}")
        ci += 1
    with dl_cols[ci]:
        cl_file = result.get("cover_letter_file", "")
        if cl_file and Path(cl_file).exists():
            with open(cl_file, "r", encoding="utf-8") as f:
                cl_content = f.read()
            st.download_button("⬇️ 求职信", cl_content,
                               file_name=Path(cl_file).name, key="jt_dl_cl")

    # 投递速查卡
    qc = result.get("quick_card", {})
    if qc and not qc.get("error"):
        with st.expander("📋 投递速查卡（填表/面试直接复制）"):
            if qc.get("one_liner"):
                st.markdown("💬 一句话自我介绍")
                st.code(qc.get("one_liner", ""))
            if qc.get("why_company"):
                st.markdown("🏢 为什么选这家公司")
                st.markdown(qc.get("why_company", ""))
            if qc.get("salary_expectation"):
                st.markdown(f"💰 期望薪资\n{qc.get('salary_expectation', '')}")


# ============================================================
# 步骤 4：标记已投
# ============================================================
st.markdown("---")
st.subheader("④ 标记已投（写入投递追踪）")

st.info("生成完简历/求职信后，去招聘平台手动投递；回来在这里点一下，记录就进「📈 投递追踪」。")

if st.button("✅ 标记已投", use_container_width=True, type="primary"):
    try:
        from modules.tracker import ApplicationTracker
        tracker = ApplicationTracker()
        pp = decision.get("pass_prob") if isinstance(decision, dict) else None
        tracker.add(
            job.get("company", ""), job.get("title", ""),
            job_url=job.get("job_url", ""),
            source=job.get("source_platform", "精投"),
            status="applied",
            competition_level=(decision or {}).get("competition_level", ""),
            llm_apply=(decision or {}).get("apply"),
            llm_pass_prob=pp if isinstance(pp, int) else None,
            llm_reason=(decision or {}).get("reason", ""),
        )
        st.success(f"已记录：{job.get('company')} — {job.get('title')}（已投递）")
        st.page_link("pages/07_📈_投递追踪.py", label="去 📈 投递追踪 查看", icon="📈")
    except Exception as e:
        st.error(f"写入追踪失败：{str(e)[:160]}")

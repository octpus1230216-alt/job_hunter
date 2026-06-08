"""
生成页面 — 定制中英文简历和Cover Letter
"""

import streamlit as st
from pathlib import Path
from datetime import datetime

st.title("✨ 生成定制简历")

if not st.session_state.get("resume_parsed"):
    st.error("请先在配置页面上传并解析简历")
    st.stop()

selected_jobs = st.session_state.get("selected_jobs", [])
config = st.session_state.get("config", {})
bilingual_default = config.get("output", {}).get("bilingual", True)

# 双语开关
bilingual = st.toggle("生成中英双语版本", value=bilingual_default,
                       help="开启后同时生成中文和英文简历及求职信")

if not selected_jobs:
    st.warning("还没有选择岗位。你可以：")
    st.markdown("1. 去「📊 审核挑选」页面挑选已发现的岗位")
    st.markdown("2. 或直接在下方输入岗位信息")

    with st.form("manual_job"):
        st.subheader("手动输入岗位信息")
        company = st.text_input("公司名 *", placeholder="例如：Google")
        title = st.text_input("职位名 *", placeholder="例如：Senior Software Engineer")
        location = st.text_input("工作地点", placeholder="例如：Mountain View, CA")
        jd_text = st.text_area("职位描述 (JD) *", height=250, placeholder="粘贴完整的JD内容...")
        submitted = st.form_submit_button("确认", use_container_width=True, type="primary")

        if submitted:
            if company and title and jd_text:
                selected_jobs.append({
                    "company": company, "title": title,
                    "location": location, "description": jd_text,
                })
                st.session_state.selected_jobs = selected_jobs
                st.success("岗位已添加！")
                st.rerun()
            else:
                st.error("请填写带 * 的必填项")

if not selected_jobs:
    st.stop()

# ============================================================
# 生成面板
# ============================================================
st.subheader(f"已选 {len(selected_jobs)} 个岗位")

for i, job in enumerate(selected_jobs):
    with st.expander(f"#{i+1} {job.get('company', '?')} — {job.get('title', '?')}", expanded=(i == 0)):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**公司:** {job.get('company', '')}")
            st.markdown(f"**职位:** {job.get('title', '')}")
            st.markdown(f"**地点:** {job.get('location', '')}")
        with col2:
            st.markdown(f"**来源:** {job.get('source_platform', job.get('source', '手动输入'))}")
            if job.get("_match_score"):
                st.markdown(f"**匹配度:** {job.get('_match_score')}")
            st.markdown(f"**语言:** {'中英双语' if bilingual else '单语言'}")

        col_a, col_b = st.columns(2)

        with col_a:
            if st.button(f"🎨 生成定制简历 + 求职信", key=f"gen_all_{i}", use_container_width=True):
                if not st.session_state.get("llm_client"):
                    st.error("请先配置API")
                else:
                    with st.status(f"正在为 {job.get('company')} 定制简历...", expanded=True) as status:
                        try:
                            from modules.style_analyzer import StyleAnalyzer
                            from modules.generator import ResumeGenerator

                            llm = st.session_state.llm_client
                            analyzer = StyleAnalyzer(llm)
                            generator = ResumeGenerator(llm, analyzer)

                            st.write("🎨 分析公司风格...")
                            result = generator.generate_all(
                                st.session_state.resume_parsed, job,
                                bilingual=bilingual
                            )

                            st.session_state[f"gen_results_{i}"] = result
                            status.update(label="生成完成！", state="complete")

                            # 显示结果
                            style = result["style"]
                            st.markdown(f"**🏷️ 公司风格:** {style.get('style_category', '?')}")

                            # 简历摘要
                            customized = result["customized_resume"]
                            st.markdown("### 📄 简历预览")
                            st.markdown(f"**摘要:** {customized.get('summary', '')[:200]}...")
                            if customized.get("summary_en"):
                                st.markdown(f"**Summary (EN):** {customized.get('summary_en', '')[:200]}...")

                            # Cover Letter
                            st.markdown("### 📝 求职信预览")
                            cl = result["cover_letter"]
                            if cl.get("subject"):
                                st.markdown(f"**主题:** {cl.get('subject', '')}")
                                st.markdown(cl.get("body", "")[:300] + "...")
                            if cl.get("subject_en"):
                                st.markdown(f"**Subject (EN):** {cl.get('subject_en', '')}")
                                st.markdown(cl.get("body_en", "")[:300] + "...")

                            # 文件信息
                            files = result.get("resume_files", {})
                            st.markdown("### 📁 生成文件")
                            for lang, fpath in files.items():
                                lang_label = "中文" if lang == "zh" else "英文"
                                st.markdown(f"- 简历({lang_label}): `{Path(fpath).name}`")

                                with open(fpath, "r", encoding="utf-8") as f:
                                    content = f.read()
                                st.download_button(
                                    f"⬇️ 下载简历({lang_label})",
                                    content,
                                    file_name=Path(fpath).name,
                                    mime="text/html",
                                    key=f"dl_resume_{i}_{lang}",
                                )

                            cl_path = Path(result["cover_letter_file"])
                            with open(cl_path, "r", encoding="utf-8") as f:
                                cl_content = f.read()
                            st.download_button(
                                "⬇️ 下载求职信",
                                cl_content,
                                file_name=cl_path.name,
                                key=f"dl_cl_{i}",
                            )

                        except Exception as e:
                            status.update(label="生成失败", state="error")
                            st.error(f"生成失败: {str(e)[:200]}")

        with col_b:
            if st.button(f"📝 仅生成求职信", key=f"gen_cl_{i}", use_container_width=True):
                if not st.session_state.get("llm_client"):
                    st.error("请先配置API")
                else:
                    with st.spinner("正在撰写求职信..."):
                        try:
                            from modules.style_analyzer import StyleAnalyzer
                            from modules.generator import ResumeGenerator

                            llm = st.session_state.llm_client
                            analyzer = StyleAnalyzer(llm)
                            generator = ResumeGenerator(llm, analyzer)

                            style_result = analyzer.analyze(job)
                            cl = generator.generate_cover_letter(
                                st.session_state.resume_parsed, job,
                                style_result, bilingual=bilingual
                            )
                            cl_path = generator.save_cover_letter(cl, job)

                            st.success("求职信已生成！")
                            if cl.get("subject"):
                                st.markdown("#### 中文版")
                                st.markdown(cl.get("body", ""))
                            if cl.get("subject_en"):
                                st.markdown("#### English Version")
                                st.markdown(cl.get("body_en", ""))

                            with open(cl_path, "r", encoding="utf-8") as f:
                                cl_content = f.read()
                            st.download_button(
                                "⬇️ 下载求职信",
                                cl_content,
                                file_name=cl_path.name,
                                key=f"dl_cl_only_{i}",
                            )
                        except Exception as e:
                            st.error(f"生成失败: {e}")

# ============================================================
# 批量操作
# ============================================================
st.markdown("---")
st.subheader("批量操作")

if st.button("🚀 一键生成全部", use_container_width=True, type="primary"):
    if not st.session_state.get("llm_client"):
        st.error("请先配置API")
    else:
        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, job in enumerate(selected_jobs):
            status_text.text(f"正在处理 {i+1}/{len(selected_jobs)}: {job.get('company')} — {job.get('title')}")

            try:
                from modules.style_analyzer import StyleAnalyzer
                from modules.generator import ResumeGenerator

                llm = st.session_state.llm_client
                analyzer = StyleAnalyzer(llm)
                generator = ResumeGenerator(llm, analyzer)

                result = generator.generate_all(
                    st.session_state.resume_parsed, job,
                    bilingual=bilingual
                )
                st.session_state[f"gen_results_{i}"] = result
            except Exception as e:
                st.error(f"{job.get('company')} 生成失败: {str(e)[:100]}")

            progress_bar.progress((i + 1) / len(selected_jobs))

        status_text.text("全部生成完成！")
        st.success(f"已为 {len(selected_jobs)} 个岗位生成定制简历和求职信")
        st.balloons()

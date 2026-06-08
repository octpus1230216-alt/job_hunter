"""
简历和 Cover Letter 生成器 — 支持中英双语
"""

import json
import os
from pathlib import Path
from datetime import datetime


class ResumeGenerator:
    """简历和 Cover Letter 生成器"""

    def __init__(self, llm_client, style_analyzer, output_dir: Path = None):
        self.llm = llm_client
        self.style_analyzer = style_analyzer
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / "output"
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_resume(self, resume: dict, job: dict,
                        style_result: dict = None, bilingual: bool = True) -> dict:
        """为特定岗位定制简历（支持双语）"""
        from modules.llm import RESUME_CUSTOMIZATION_PROMPT

        if style_result is None:
            style_result = self.style_analyzer.analyze(job)

        style_category = style_result.get("style_category", "corporate")
        style_detail = style_result.get("style_detail", {})

        job_desc = job.get("description", "")[:3000]
        style_desc = json.dumps(style_detail, ensure_ascii=False)

        lang_instruction = ""
        if bilingual:
            lang_instruction = "\n请同时生成中文和英文两个版本（用 _en 后缀字段）。\n如果是国内公司，主版本用中文；如果是海外公司，主版本用英文。"

        user_prompt = f"""请为目标岗位定制简历内容。{lang_instruction}

=== 主简历（请基于此定制，不要编造经历）===
{json.dumps(resume, ensure_ascii=False, indent=2)}

=== 目标岗位 ===
公司：{job.get('company', '')}
职位：{job.get('title', '')}
JD：
{job_desc}

=== 目标公司风格 ===
{style_desc}

请生成定制后的简历内容。"""

        try:
            customized = self.llm.chat_json(RESUME_CUSTOMIZATION_PROMPT, user_prompt)
            customized["style"] = style_result
            customized["bilingual"] = bilingual
            customized["original_resume_hash"] = str(hash(json.dumps(resume)))
            return customized
        except Exception as e:
            return {"error": str(e)}

    def generate_cover_letter(self, resume: dict, job: dict,
                              style_result: dict = None, bilingual: bool = True) -> dict:
        """生成 Cover Letter（支持双语）"""
        from modules.llm import COVER_LETTER_PROMPT

        if style_result is None:
            style_result = self.style_analyzer.analyze(job)

        style_category = style_result.get("style_category", "corporate")
        cl_config = self.style_analyzer.get_cover_letter_config(style_category)

        job_desc = job.get("description", "")[:2000]

        lang_instruction = ""
        if bilingual:
            lang_instruction = "\n请同时生成中文和英文两个版本。中文版本用于国内公司，英文版本用于海外公司。"

        user_prompt = f"""请为目标岗位撰写 Cover Letter。{lang_instruction}

=== 候选人信息 ===
姓名：{resume.get('name', '')}
当前职位：{resume.get('experience', [{}])[0].get('title', '') if resume.get('experience') else ''}
核心技能：{self._extract_key_skills(resume)}

=== 目标岗位 ===
公司：{job.get('company', '')}
职位：{job.get('title', '')}
JD摘要：
{job_desc}

=== 风格指导 ===
语气：{cl_config['tone']}
切入角度：{cl_config['angle']}
关键词汇：{', '.join(cl_config['key_phrases'])}"""

        try:
            result = self.llm.chat_json(COVER_LETTER_PROMPT, user_prompt)
            result["company"] = job.get("company", "")
            result["job_title"] = job.get("title", "")
            result["style"] = style_category
            return result
        except Exception as e:
            return {"error": str(e)}

    def render_html_resume(self, customized: dict, template_name: str = "corporate",
                           lang: str = "zh") -> str:
        """渲染简历为HTML（指定语言）"""
        return self._build_html_resume(customized, template_name, lang)

    def save_as_html(self, customized: dict, job: dict,
                     template_name: str = None, lang: str = "zh") -> Path:
        """保存单个语言版本的HTML简历"""
        style_category = customized.get("style", {}).get("style_category", "corporate")
        if template_name is None:
            template_name = style_category

        html = self.render_html_resume(customized, template_name, lang)

        company = job.get("company", "company").replace(" ", "_")
        role = job.get("title", "role").replace(" ", "_")
        date_str = datetime.now().strftime("%Y%m%d")
        lang_suffix = "_en" if lang == "en" else ""
        filename = f"resume_{company}_{role}{lang_suffix}_{date_str}.html"
        filepath = self.output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        return filepath

    def save_cover_letter(self, cover_letter: dict, job: dict, lang: str = None) -> Path:
        """保存 Cover Letter 为 Markdown 文件"""
        company = job.get("company", "company").replace(" ", "_")
        role = job.get("title", "role").replace(" ", "_")
        date_str = datetime.now().strftime("%Y%m%d")

        if lang is None:
            # 保存完整版本（双语）
            filename = f"coverletter_{company}_{role}_{date_str}.md"
            filepath = self.output_dir / filename

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# Cover Letter / 求职信\n\n")
                f.write(f"**To / 致:** {company} - {role}\n")
                f.write(f"**Style:** {cover_letter.get('style', 'N/A')}\n\n")

                # 中文版
                if cover_letter.get("body"):
                    f.write(f"## 中文版\n\n")
                    f.write(f"**主题:** {cover_letter.get('subject', '')}\n\n")
                    f.write(f"{cover_letter.get('body', '')}\n\n")

                # 英文版
                if cover_letter.get("body_en"):
                    f.write(f"## English Version\n\n")
                    f.write(f"**Subject:** {cover_letter.get('subject_en', '')}\n\n")
                    f.write(f"{cover_letter.get('body_en', '')}\n\n")

                f.write(f"---\n*Tone: {cover_letter.get('tone_description', '')}*")
        else:
            # 单独语言版本
            lang_suffix = "_en" if lang == "en" else ""
            filename = f"coverletter_{company}_{role}{lang_suffix}_{date_str}.md"
            filepath = self.output_dir / filename

            body = cover_letter.get("body_en" if lang == "en" else "body", "")
            subject = cover_letter.get("subject_en" if lang == "en" else "subject", "")

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# Cover Letter\n\n")
                f.write(f"**To:** {company} - {role}\n\n")
                f.write(f"**Subject:** {subject}\n\n---\n\n")
                f.write(body)

        return filepath

    def generate_all(self, resume: dict, job: dict, bilingual: bool = True) -> dict:
        """一键生成：风格分析 -> 定制简历 -> Cover Letter（双语）"""
        style_result = self.style_analyzer.analyze(job)
        customized = self.generate_resume(resume, job, style_result, bilingual)
        cover_letter = self.generate_cover_letter(resume, job, style_result, bilingual)

        # 保存文件
        if bilingual:
            resume_path_cn = self.save_as_html(customized, job, lang="zh")
            resume_path_en = self.save_as_html(customized, job, lang="en")
            resume_files = {"zh": str(resume_path_cn), "en": str(resume_path_en)}
        else:
            resume_path = self.save_as_html(customized, job)
            resume_files = {"default": str(resume_path)}

        cl_path = self.save_cover_letter(cover_letter, job)

        return {
            "style": style_result,
            "customized_resume": customized,
            "cover_letter": cover_letter,
            "resume_files": resume_files,
            "cover_letter_file": str(cl_path),
        }

    def _extract_key_skills(self, resume: dict) -> str:
        skills = resume.get("skills", {})
        all_skills = []
        for category, skill_list in skills.items():
            if skill_list:
                all_skills.extend(skill_list)
        return ", ".join(all_skills[:15])

    def _build_html_resume(self, customized: dict, template_name: str, lang: str = "zh") -> str:
        """构建HTML简历（支持语言版本）"""
        is_en = (lang == "en")

        style_configs = {
            "tech_china": {"primary_color": "#1890ff", "font": "'PingFang SC', 'Microsoft YaHei', sans-serif"},
            "startup": {"primary_color": "#4CAF50", "font": "'Inter', 'Segoe UI', sans-serif"},
            "corporate": {"primary_color": "#1a365d", "font": "'Georgia', 'Times New Roman', serif"},
            "consulting": {"primary_color": "#2d3748", "font": "'Helvetica Neue', 'Arial', sans-serif"},
        }
        style = style_configs.get(template_name, style_configs["corporate"])

        # 根据语言选择字段
        def get_field(customized, key, key_en=None):
            if is_en and key_en:
                val = customized.get(key_en, "")
                return val if val else customized.get(key, "")
            return customized.get(key, "")

        # 经验
        experience_html = ""
        for exp in customized.get("experience", []):
            bullets = exp.get("bullets_en" if is_en else "bullets", exp.get("bullets", []))
            bullets_html = "\n".join([f"<li>{b}</li>" for b in bullets])
            title = exp.get("title_en" if is_en else "title", exp.get("title", ""))
            company = exp.get("company", "")
            duration = exp.get("duration", "")
            experience_html += f"""
            <div class="experience-item">
                <div class="exp-header">
                    <span class="exp-title">{title}</span>
                    <span class="exp-company">{company}</span>
                </div>
                <div class="exp-duration">{duration}</div>
                <ul>{bullets_html}</ul>
            </div>"""

        # 项目
        projects_html = ""
        for proj in customized.get("projects", []):
            highlights = proj.get("highlights_en" if is_en else "highlights", proj.get("highlights", []))
            highlights_html = "\n".join([f"<li>{h}</li>" for h in highlights])
            name = proj.get("name_en" if is_en else "name", proj.get("name", ""))
            desc = proj.get("description_en" if is_en else "description", proj.get("description", ""))
            projects_html += f"""
            <div class="project-item">
                <div class="project-name">{name}</div>
                <div class="project-desc">{desc}</div>
                <ul>{highlights_html}</ul>
            </div>"""

        # 技能
        skills = customized.get("skills_en" if is_en else "skills", customized.get("skills", []))
        skills_html = ", ".join(skills) if skills else ""

        # 教育
        education_html = ""
        for edu in customized.get("education", []):
            school = edu.get("school", "")
            degree = edu.get("degree", "")
            major = edu.get("major", "")
            education_html += f"""
            <div class="edu-item">
                <span class="edu-school">{school}</span>
                <span class="edu-degree">{degree} in {major}</span>
            </div>"""

        # 标签文字
        labels = {
            "zh": {"skills": "技能", "experience": "工作经验", "projects": "项目经历",
                   "education": "教育背景", "notes": "定制说明"},
            "en": {"skills": "Skills", "experience": "Experience", "projects": "Projects",
                   "education": "Education", "notes": "Customization Notes"},
        }
        lbl = labels.get(lang, labels["zh"])

        summary = customized.get("summary_en" if is_en else "summary", customized.get("summary", ""))
        name_obj = customized.get('experience', [{}])
        candidate_name = name_obj[0].get('company', 'Name') if name_obj else 'Name'

        return f"""<!DOCTYPE html>
<html lang="{'en' if is_en else 'zh-CN'}">
<head>
    <meta charset="UTF-8">
    <title>{'Resume' if is_en else '简历'} - {candidate_name}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: {style['font']};
            font-size: 13px; line-height: 1.6; color: #333;
            max-width: 800px; margin: 0 auto; padding: 40px; background: #fff;
        }}
        .header {{ border-bottom: 3px solid {style['primary_color']}; padding-bottom: 20px; margin-bottom: 24px; }}
        .name {{ font-size: 28px; font-weight: 600; color: {style['primary_color']}; }}
        .contact {{ font-size: 13px; color: #666; margin-top: 8px; }}
        .summary {{ background: #f8f9fa; padding: 16px; border-left: 4px solid {style['primary_color']}; margin-bottom: 24px; border-radius: 4px; }}
        .section {{ margin-bottom: 20px; }}
        .section-title {{ font-size: 16px; font-weight: 600; color: {style['primary_color']}; border-bottom: 1px solid #ddd; padding-bottom: 6px; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 1px; }}
        .experience-item, .project-item {{ margin-bottom: 16px; }}
        .exp-header, .project-name {{ display: flex; justify-content: space-between; font-weight: 500; }}
        .exp-duration, .project-desc {{ font-size: 12px; color: #888; margin-top: 2px; }}
        ul {{ padding-left: 20px; }} li {{ margin-bottom: 4px; }}
        .skills {{ display: flex; flex-wrap: wrap; gap: 8px; }}
        .skill-tag {{ background: #f0f0f0; padding: 4px 12px; border-radius: 12px; font-size: 12px; }}
        .edu-item {{ display: flex; justify-content: space-between; margin-bottom: 4px; }}
        .notes {{ margin-top: 30px; padding: 12px; background: #fffbe6; border: 1px solid #ffe58f; border-radius: 4px; font-size: 11px; color: #999; }}
        @media print {{ body {{ padding: 0; }} .notes {{ display: none; }} }}
    </style>
</head>
<body>
    <div class="header">
        <div class="name">{candidate_name}</div>
        <div class="contact">{customized.get('email', '') or ''}</div>
    </div>
    <div class="summary">{summary}</div>
    <div class="section">
        <div class="section-title">{lbl['skills']}</div>
        <div class="skills">{''.join([f'<span class="skill-tag">{s}</span>' for s in skills]) if isinstance(skills, list) else skills_html}</div>
    </div>
    <div class="section">
        <div class="section-title">{lbl['experience']}</div>
        {experience_html}
    </div>
    <div class="section">
        <div class="section-title">{lbl['projects']}</div>
        {projects_html}
    </div>
    <div class="section">
        <div class="section-title">{lbl['education']}</div>
        {education_html}
    </div>
    <div class="notes">{lbl['notes']}: {customized.get('customization_notes', '')}</div>
</body>
</html>"""

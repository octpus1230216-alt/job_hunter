"""
智能匹配引擎 — 简历 vs JD 的语义匹配
"""

import json
from pathlib import Path
from datetime import datetime


class JobMatcher:
    """简历与职位匹配器"""

    def __init__(self, llm_client, data_dir: Path = None):
        self.llm = llm_client
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def match_single(self, resume: dict, job: dict, preferences: dict = None) -> dict:
        """
        单个简历-JD匹配
        返回匹配分析结果
        """
        from modules.llm import MATCHING_SYSTEM_PROMPT

        # 构建简历摘要
        resume_summary = self._summarize_resume(resume)
        job_summary = self._summarize_job(job)

        user_prompt = f"""请分析以下候选人与岗位的匹配度：

=== 候选人简历摘要 ===
{resume_summary}

=== 目标岗位信息 ===
公司：{job.get('company', '未知')}
职位：{job.get('title', '未知')}
地点：{job.get('location', '未知')}
职位描述：
{job_summary}

=== 候选人偏好 ===
{preferences or '无特殊偏好'}

请给出详细的匹配分析。"""

        try:
            result = self.llm.chat_json(MATCHING_SYSTEM_PROMPT, user_prompt)
            result.update({
                "job_title": job.get("title", ""),
                "company": job.get("company", ""),
                "job_url": job.get("job_url", ""),
                "matched_at": datetime.now().isoformat()
            })
            return result
        except Exception as e:
            return {
                "error": str(e),
                "job_title": job.get("title", ""),
                "company": job.get("company", ""),
                "overall_score": 0,
            }

    def match_batch(self, resume: dict, jobs: list, preferences: dict = None,
                    progress_callback=None, min_score: int = 0) -> list:
        """
        批量匹配：简历 vs 多个JD
        返回按匹配度降序排列的结果
        """
        results = []
        total = len(jobs)

        for i, job in enumerate(jobs):
            if progress_callback:
                progress_callback(f"正在匹配 ({i+1}/{total}): {job.get('title', '')} @ {job.get('company', '')}")

            match_result = self.match_single(resume, job, preferences)

            # 过滤低分
            score = match_result.get("overall_score", 0)
            if score >= min_score:
                results.append(match_result)

        # 按分数降序
        results.sort(key=lambda x: x.get("overall_score", 0), reverse=True)
        return results

    # ---- 决策通道：是否建议投递 + 真实过筛概率 ----
    # 实验表明该通道比纯匹配度打分更接近真实录取结果（AUC≈0.64），
    # 关键在让 LLM 对顶级厂做内生折扣。与 match_single 并列使用。
    DECISION_SYSTEM_PROMPT = (
        "你是求职决策助手。基于候选人简历与岗位 JD，判断是否建议投递并估计真实过筛概率。"
        "重点：公司竞争力层级（顶级厂过筛率通常<10%）比内容匹配度更影响真实结果；"
        "顶级厂即便匹配度高也应显著下调 pass_prob。"
    )

    def decide_single(self, resume: dict, job: dict, preferences: dict = None) -> dict:
        """
        单个简历-JD 决策：是否建议投递 + 真实过筛概率 + 理由。
        返回 {apply, pass_prob, reason, competition_level, ...}
        """
        resume_summary = self._summarize_resume(resume)
        job_summary = self._summarize_job(job)

        user_prompt = f"""请判断以下岗位是否值得投递：

=== 候选人简历摘要 ===
{resume_summary}

=== 目标岗位信息 ===
公司：{job.get('company', '未知')}
职位：{job.get('title', '未知')}
地点：{job.get('location', '未知')}
职位描述：
{job_summary}

=== 候选人偏好 ===
{preferences or '无特殊偏好'}

请输出 JSON：
{{"apply":0或1, "pass_prob":0-100, "reason":"一句话理由", "competition_level":"顶级厂/一线大厂/中厂B轮C轮/初创天使轮/未知"}}"""

        try:
            result = self.llm.chat_json(self.DECISION_SYSTEM_PROMPT, user_prompt)
            result.update({
                "job_title": job.get("title", ""),
                "company": job.get("company", ""),
                "job_url": job.get("job_url", ""),
                "decided_at": datetime.now().isoformat()
            })
            return result
        except Exception as e:
            return {
                "error": str(e),
                "job_title": job.get("title", ""),
                "company": job.get("company", ""),
                "apply": 0,
                "pass_prob": 0,
            }

    def decide_batch(self, resume: dict, jobs: list, preferences: dict = None,
                     progress_callback=None) -> list:
        """
        批量决策：简历 vs 多个JD，返回按 pass_prob 降序排列的结果。
        """
        results = []
        total = len(jobs)
        for i, job in enumerate(jobs):
            if progress_callback:
                progress_callback(f"正在决策 ({i+1}/{total}): {job.get('title', '')} @ {job.get('company', '')}")
            results.append(self.decide_single(resume, job, preferences))
        # 按过筛概率降序
        results.sort(key=lambda x: x.get("pass_prob", 0), reverse=True)
        return results

    def _summarize_resume(self, resume: dict) -> str:
        """简历摘要"""
        parts = []

        if resume.get("summary"):
            parts.append(f"个人总结: {resume['summary']}")

        skills = resume.get("skills", {})
        if skills:
            all_skills = []
            for category, skill_list in skills.items():
                if skill_list:
                    all_skills.extend(skill_list)
            if all_skills:
                parts.append(f"技能: {', '.join(all_skills)}")

        experience = resume.get("experience", [])
        if experience:
            parts.append(f"工作经历 ({len(experience)} 段):")
            for exp in experience[:5]:  # 最近5段
                bullets = " | ".join(exp.get("bullets", [])[:3])
                parts.append(f"  - {exp.get('title')} @ {exp.get('company')}: {bullets}")

        education = resume.get("education", [])
        if education:
            edu_parts = []
            for edu in education[:2]:
                edu_parts.append(f"{edu.get('degree')} in {edu.get('major')} from {edu.get('school')}")
            parts.append(f"学历: {'; '.join(edu_parts)}")

        return "\n".join(parts)

    def _summarize_job(self, job: dict) -> str:
        """JD摘要"""
        # 优先取 description
        desc = job.get("description", "")
        if desc:
            # 限制长度，避免超出token
            return desc[:3000]

        # 如果没有描述，从其他字段拼凑
        parts = []
        if job.get("job_type"):
            parts.append(f"类型: {job['job_type']}")
        if job.get("job_function"):
            parts.append(f"职能: {job['job_function']}")
        if job.get("skills"):
            parts.append(f"技能要求: {', '.join(job['skills'])}")
        return "\n".join(parts)

    def save_results(self, results: list, filename: str = None):
        """保存匹配结果"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"match_results_{timestamp}"

        filepath = self.data_dir / f"{filename}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        return filepath

    def load_latest_results(self) -> list:
        """加载最近匹配结果"""
        json_files = sorted(self.data_dir.glob("match_results_*.json"), reverse=True)
        if json_files:
            with open(json_files[0], "r", encoding="utf-8") as f:
                return json.load(f)
        return []
